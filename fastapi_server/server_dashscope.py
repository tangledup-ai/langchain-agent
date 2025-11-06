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

# Ensure we can import from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lang_agent.pipeline import Pipeline, PipelineConfig


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
    thread_id: Optional[int] = Field(default=3)


app = FastAPI(title="DashScope-Compatible Application API",
              description="DashScope Application.call compatible endpoint backed by pipeline.chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize Pipeline once
pipeline_config = PipelineConfig()
pipeline_config.llm_name = "qwen-flash"
pipeline_config.llm_provider = "openai"
pipeline_config.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
pipeline = Pipeline(pipeline_config)


def sse_chunks_from_text(full_text: str, response_id: str, model: str = "qwen-flash", chunk_size: int = 10):
    created_time = int(time.time())

    for i in range(0, len(full_text), chunk_size):
        chunk = full_text[i:i + chunk_size]
        if chunk:
            data = {
                "request_id": response_id,
                "code": 200,
                "message": "OK",
                "output": {
                    # Send empty during stream; many SDKs only expose output_text on final
                    "text": "",
                    "created": created_time,
                    "model": model,
                },
                "is_end": False,
            }
            yield f"data: {json.dumps(data)}\n\n"

    final = {
        "request_id": response_id,
        "code": 200,
        "message": "OK",
        "output": {
            "text": full_text,
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
        req_session_id = session_id or body.get("session_id")

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

        thread_id = body.get("thread_id", 3)

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

        # Invoke pipeline (non-stream) then stream-chunk it to the client
        result_text = pipeline.chat(inp=user_msg, as_stream=False, thread_id=thread_id)
        if not isinstance(result_text, str):
            result_text = str(result_text)

        response_id = f"appcmpl-{os.urandom(12).hex()}"

        if stream:
            return StreamingResponse(
                sse_chunks_from_text(result_text, response_id=response_id, model=pipeline_config.llm_name, chunk_size=10),
                media_type="text/event-stream",
            )

        # Non-streaming response structure
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

        req_session_id = body.get("session_id")

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

        thread_id = body.get("thread_id", 3)

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

        result_text = pipeline.chat(inp=user_msg, as_stream=False, thread_id=thread_id)
        if not isinstance(result_text, str):
            result_text = str(result_text)

        response_id = f"appcmpl-{os.urandom(12).hex()}"

        if stream:
            return StreamingResponse(
                sse_chunks_from_text(result_text, response_id=response_id, model=pipeline_config.llm_name, chunk_size=10),
                media_type="text/event-stream",
            )

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


