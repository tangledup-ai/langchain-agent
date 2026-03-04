from fastapi import FastAPI, HTTPException, Path, Request, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Tuple
import os
import os.path as osp
import sys
import time
import json
import uvicorn
from loguru import logger
import tyro

# Ensure we can import from project root
sys.path.append(osp.dirname(osp.dirname(osp.abspath(__file__))))

from lang_agent.pipeline import PipelineConfig
from lang_agent.components.server_pipeline_manager import ServerPipelineManager

# Load base config for route-level overrides (pipelines are lazy-loaded from registry)
pipeline_config = tyro.cli(PipelineConfig)
logger.info(f"starting agent with base pipeline config: \n{pipeline_config}")

# API Key Authentication
API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=True)
VALID_API_KEYS = set(filter(None, os.environ.get("FAST_AUTH_KEYS", "").split(",")))
REGISTRY_FILE = os.environ.get(
    "FAST_PIPELINE_REGISTRY_FILE",
    osp.join(
        osp.dirname(osp.dirname(osp.abspath(__file__))),
        "configs",
        "pipeline_registry.json",
    ),
)


PIPELINE_MANAGER = ServerPipelineManager(
    default_pipeline_id=os.environ.get("FAST_DEFAULT_PIPELINE_ID", "default"),
    default_config=pipeline_config,
)
PIPELINE_MANAGER.load_registry(REGISTRY_FILE)


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    """Verify the API key from Authorization header (Bearer token format)."""
    key = api_key[7:] if api_key.startswith("Bearer ") else api_key
    if VALID_API_KEYS and key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key


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


app = FastAPI(
    title="DashScope-Compatible Application API",
    description="DashScope Application.call compatible endpoint backed by pipeline.chat",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def sse_chunks_from_stream(
    chunk_generator, response_id: str, model: str = "qwen-flash"
):
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


async def sse_chunks_from_astream(
    chunk_generator, response_id: str, model: str = "qwen-flash"
):
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


def _normalize_messages(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    messages = body.get("messages")
    body_input = body.get("input", {})
    if messages is None and isinstance(body_input, dict):
        messages = body_input.get("messages")
    if messages is None and isinstance(body_input, dict):
        prompt = body_input.get("prompt")
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]

    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")
    return messages


def _extract_user_message(messages: List[Dict[str, Any]]) -> str:
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
    return user_msg


async def _process_dashscope_request(
    body: Dict[str, Any],
    app_id: Optional[str],
    session_id: Optional[str],
    api_key: str,
):
    req_app_id = app_id or body.get("app_id")
    body_input = body.get("input", {}) if isinstance(body.get("input"), dict) else {}
    req_session_id = session_id or body_input.get("session_id")
    messages = _normalize_messages(body)

    stream = body.get("stream")
    if stream is None:
        stream = body.get("parameters", {}).get("stream", True)

    thread_id = body_input.get("session_id") or req_session_id or "3"
    user_msg = _extract_user_message(messages)

    pipeline_id = PIPELINE_MANAGER.resolve_pipeline_id(
        body=body, app_id=req_app_id, api_key=api_key
    )
    selected_pipeline, selected_model = PIPELINE_MANAGER.get_pipeline(pipeline_id)

    # Namespace thread ids to prevent memory collisions across pipelines.
    thread_id = f"{pipeline_id}:{thread_id}"

    response_id = f"appcmpl-{os.urandom(12).hex()}"

    if stream:
        chunk_generator = await selected_pipeline.achat(
            inp=user_msg, as_stream=True, thread_id=thread_id
        )
        return StreamingResponse(
            sse_chunks_from_astream(
                chunk_generator, response_id=response_id, model=selected_model
            ),
            media_type="text/event-stream",
        )

    result_text = await selected_pipeline.achat(
        inp=user_msg, as_stream=False, thread_id=thread_id
    )
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
            "model": selected_model,
        },
        "pipeline_id": pipeline_id,
        "is_end": True,
    }
    return JSONResponse(content=data)


@app.post("/v1/apps/{app_id}/sessions/{session_id}/responses")
@app.post("/api/v1/apps/{app_id}/sessions/{session_id}/responses")
async def application_responses(
    request: Request,
    app_id: str = Path(...),
    session_id: str = Path(...),
    api_key: str = Depends(verify_api_key),
):
    try:
        body = await request.json()
        return await _process_dashscope_request(
            body=body,
            app_id=app_id,
            session_id=session_id,
            api_key=api_key,
        )

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
    api_key: str = Depends(verify_api_key),
):
    try:
        body = await request.json()
        return await _process_dashscope_request(
            body=body,
            app_id=app_id,
            session_id=None,
            api_key=api_key,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"DashScope-compatible completion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {
        "message": "DashScope Application-compatible API",
        "endpoints": [
            "/v1/apps/{app_id}/sessions/{session_id}/responses",
            "/health",
        ],
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "server_dashscope:app",
        host="0.0.0.0",
        port=pipeline_config.port,
        reload=True,
    )
