from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import sys
import time
import json
import uvicorn
from loguru import logger
import tyro

# Ensure we can import from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lang_agent.pipeline import Pipeline, PipelineConfig

# Initialize Pipeline once
pipeline_config = tyro.cli(PipelineConfig)
pipeline:Pipeline = pipeline_config.setup()


class DSMessage(BaseModel):
    role: str
    content: str


class DSApplicationCallRequest(BaseModel):
    api_key: Optional[str] = Field(default=None)
    app_id: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default=None)
    messages: List[DSMessage]
    stream: bool = Field(default=True)
    # Optional overrides for pipeline behavior
    thread_id: Optional[str] = Field(default="3")


app = FastAPI(title="DashScope-Compatible Application API",
              description="DashScope Application.call compatible endpoint backed by pipeline.chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def sse_chunks_from_stream(chunk_generator, response_id: str, model: str = "qwen-flash"):
    """
    Stream chunks from pipeline and format as SSE.
    Accumulates text and sends incremental updates.
    DashScope SDK expects accumulated text in each chunk (not deltas).
    """
    created_time = int(time.time())
    accumulated_text = ""

    for chunk in chunk_generator:
        if chunk:
            accumulated_text += chunk
            data = {
                "request_id": response_id,
                "code": 200,
                "message": "OK",
                "output": {
                    # DashScope SDK expects accumulated text, not empty or delta
                    "text": accumulated_text,
                    "created": created_time,
                    "model": model,
                },
                "is_end": False,
            }
            yield f"data: {json.dumps(data)}\n\n"

    # Final message with complete text
    final = {
        "request_id": response_id,
        "code": 200,
        "message": "OK",
        "output": {
            "text": accumulated_text,
            "created": created_time,
            "model": model,
        },
        "is_end": True,
    }
    yield f"data: {json.dumps(final)}\n\n"


async def sse_chunks_from_astream(chunk_generator, response_id: str, model: str = "qwen-flash"):
    """
    Async version: Stream chunks from pipeline and format as SSE.
    Accumulates text and sends incremental updates.
    DashScope SDK expects accumulated text in each chunk (not deltas).
    """
    created_time = int(time.time())
    accumulated_text = ""

    async for chunk in chunk_generator:
        if chunk:
            accumulated_text += chunk
            data = {
                "request_id": response_id,
                "code": 200,
                "message": "OK",
                "output": {
                    "text": accumulated_text,
                    "created": created_time,
                    "model": model,
                },
                "is_end": False,
            }
            yield f"data: {json.dumps(data)}\n\n"

    # Final message with complete text
    final = {
        "request_id": response_id,
        "code": 200,
        "message": "OK",
        "output": {
            "text": accumulated_text,
            "created": created_time,
            "model": model,
        },
        "is_end": True,
    }
    yield f"data: {json.dumps(final)}\n\n"


@app.post("/v1/apps/{app_id}/sessions/{session_id}/responses")
@app.post("/api/v1/apps/{app_id}/sessions/{session_id}/responses")
async def application_responses(
    request: Request,
    app_id: str = Path(...),
    session_id: str = Path(...),
):
    try:
        body = await request.json()

        # Prefer path params
        req_app_id = app_id or body.get("app_id")
        req_session_id = session_id or body['input'].get("session_id")

        # Normalize messages
        messages = body.get("messages")
        if messages is None and isinstance(body.get("input"), dict):
            messages = body.get("input", {}).get("messages")
        if messages is None and isinstance(body.get("input"), dict):
            prompt = body.get("input", {}).get("prompt")
            if isinstance(prompt, str):
                messages = [{"role": "user", "content": prompt}]

        if not messages:
            raise HTTPException(status_code=400, detail="messages is required")

        # Determine stream flag
        stream = body.get("stream")
        if stream is None:
            stream = body.get("parameters", {}).get("stream", True)

        thread_id = body['input'].get("session_id")

        # Extract latest user message
        user_msg = None
        for m in reversed(messages):
            role = m.get("role") if isinstance(m, dict) else None
            content = m.get("content") if isinstance(m, dict) else None
            if role == "user" and content:
                user_msg = content
                break
        if user_msg is None:
            last = messages[-1]
            user_msg = last.get("content") if isinstance(last, dict) else str(last)

        response_id = f"appcmpl-{os.urandom(12).hex()}"

        if stream:
            # Use async streaming from pipeline
            chunk_generator = await pipeline.achat(inp=user_msg, as_stream=True, thread_id=thread_id)
            return StreamingResponse(
                sse_chunks_from_astream(chunk_generator, response_id=response_id, model=pipeline_config.llm_name),
                media_type="text/event-stream",
            )

        # Non-streaming: get full result using async
        result_text = await pipeline.achat(inp=user_msg, as_stream=False, thread_id=thread_id)
        if not isinstance(result_text, str):
            result_text = str(result_text)

        data = {
            "request_id": response_id,
            "code": 200,
            "message": "OK",
            "app_id": req_app_id,
            "session_id": req_session_id,
            "output": {
                "text": result_text,
                "created": int(time.time()),
                "model": pipeline_config.llm_name,
            },
            "is_end": True,
        }
        return JSONResponse(content=data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"DashScope-compatible endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Compatibility: some SDKs call /apps/{app_id}/completion without /v1 and without session in path
@app.post("/apps/{app_id}/completion")
@app.post("/v1/apps/{app_id}/completion")
@app.post("/api/apps/{app_id}/completion")
@app.post("/api/v1/apps/{app_id}/completion")
async def application_completion(
    request: Request,
    app_id: str = Path(...),
):
    try:
        body = await request.json()

        req_session_id = body['input'].get("session_id")

        # Normalize messages
        messages = body.get("messages")
        if messages is None and isinstance(body.get("input"), dict):
            messages = body.get("input", {}).get("messages")
        if messages is None and isinstance(body.get("input"), dict):
            prompt = body.get("input", {}).get("prompt")
            if isinstance(prompt, str):
                messages = [{"role": "user", "content": prompt}]

        if not messages:
            raise HTTPException(status_code=400, detail="messages is required")

        stream = body.get("stream")
        if stream is None:
            stream = body.get("parameters", {}).get("stream", True)

        thread_id = body['input'].get("session_id")

        user_msg = None
        for m in reversed(messages):
            role = m.get("role") if isinstance(m, dict) else None
            content = m.get("content") if isinstance(m, dict) else None
            if role == "user" and content:
                user_msg = content
                break
        if user_msg is None:
            last = messages[-1]
            user_msg = last.get("content") if isinstance(last, dict) else str(last)

        response_id = f"appcmpl-{os.urandom(12).hex()}"

        if stream:
            # Use async streaming from pipeline
            chunk_generator = await pipeline.achat(inp=user_msg, as_stream=True, thread_id=thread_id)
            return StreamingResponse(
                sse_chunks_from_astream(chunk_generator, response_id=response_id, model=pipeline_config.llm_name),
                media_type="text/event-stream",
            )

        # Non-streaming: get full result using async
        result_text = await pipeline.achat(inp=user_msg, as_stream=False, thread_id=thread_id)
        if not isinstance(result_text, str):
            result_text = str(result_text)

        data = {
            "request_id": response_id,
            "code": 200,
            "message": "OK",
            "app_id": app_id,
            "session_id": req_session_id,
            "output": {
                "text": result_text,
                "created": int(time.time()),
                "model": pipeline_config.llm_name,
            },
            "is_end": True,
        }
        return JSONResponse(content=data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"DashScope-compatible completion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {"message": "DashScope Application-compatible API", "endpoints": [
        "/v1/apps/{app_id}/sessions/{session_id}/responses",
        "/health",
    ]}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "server_dashscope:app",
        host="0.0.0.0",
        port=8588,
        reload=True,
    )


