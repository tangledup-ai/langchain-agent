from fastapi import FastAPI, HTTPException, Request, Depends, Security, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional, Literal
import os
import sys
import time
import json
import uvicorn
from loguru import logger
import tyro

# Ensure we can import from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.checkpoint.memory import MemorySaver
from lang_agent.pipeline import Pipeline, PipelineConfig

# Initialize Pipeline once (matches existing server_* pattern)
pipeline_config = tyro.cli(PipelineConfig)
logger.info(f"starting agent with pipeline: \n{pipeline_config}")
pipeline: Pipeline = pipeline_config.setup()

# API Key Authentication
API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=False)
VALID_API_KEYS = set(filter(None, os.environ.get("FAST_AUTH_KEYS", "").split(",")))


async def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)):
    """Verify the API key from Authorization header (Bearer token format)."""
    if not api_key:
        # Tests expect 401 (not FastAPI's default 403) when auth header is missing.
        raise HTTPException(status_code=401, detail="Missing API key")
    key = api_key[7:] if api_key.startswith("Bearer ") else api_key
    if VALID_API_KEYS and key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key


def _now_iso() -> str:
    # Avoid extra deps; good enough for API metadata.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_conversation_id() -> str:
    return f"c_{os.urandom(12).hex()}"


def _normalize_thread_id(conversation_id: str) -> str:
    """
    Pipeline.achat supports a "{thread_id}_{device_id}" format.
    Memory is keyed by the base thread_id (before the device_id suffix).
    """
    # Conversation IDs we mint are "c_{hex}" (2 segments). Some clients append a device_id:
    # e.g. "c_test123_device456" -> base thread "c_test123".
    parts = conversation_id.split("_")
    if len(parts) >= 3:
        return conversation_id.rsplit("_", 1)[0]
    return conversation_id


def _try_clear_single_thread_memory(thread_id: str) -> bool:
    """
    Best-effort per-thread memory deletion.
    Returns True if we believe we cleared something, else False.
    """
    g = getattr(pipeline, "graph", None)
    mem = getattr(g, "memory", None)
    if isinstance(mem, MemorySaver):
        try:
            mem.delete_thread(thread_id)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete memory thread {thread_id}: {e}")
            return False
    return False


class ConversationCreateResponse(BaseModel):
    id: str
    created_at: str


class MessageCreateRequest(BaseModel):
    # Keep this permissive so invalid roles get a 400 from endpoint logic (not 422 from validation).
    role: str = Field(default="user")
    content: str
    stream: bool = Field(default=False)


class MessageResponse(BaseModel):
    role: Literal["assistant"] = Field(default="assistant")
    content: str


class ConversationMessageResponse(BaseModel):
    conversation_id: str
    message: MessageResponse


class ChatRequest(BaseModel):
    input: str
    conversation_id: Optional[str] = Field(default=None)
    stream: bool = Field(default=False)


class ChatResponse(BaseModel):
    conversation_id: str
    output: str


app = FastAPI(
    title="REST Agent API",
    description="Resource-oriented REST API backed by Pipeline.achat (no RAG/eval/tools exposure).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def rest_sse_from_astream(chunk_generator, response_id: str, conversation_id: str):
    """
    Stream chunks as SSE events.

    Format:
      - data: {"type":"delta","id":...,"conversation_id":...,"delta":"..."}
      - data: {"type":"done","id":...,"conversation_id":...}
      - data: [DONE]
    """
    async for chunk in chunk_generator:
        if chunk:
            data = {
                "type": "delta",
                "id": response_id,
                "conversation_id": conversation_id,
                "delta": chunk,
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    done = {"type": "done", "id": response_id, "conversation_id": conversation_id}
    yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@app.get("/")
async def root():
    return {
        "message": "REST Agent API",
        "endpoints": [
            "/v1/conversations (POST)",
            "/v1/chat (POST)",
            "/v1/conversations/{conversation_id}/messages (POST)",
            "/v1/conversations/{conversation_id}/memory (DELETE)",
            "/v1/memory (DELETE)",
            "/health (GET)",
        ],
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/v1/conversations", response_model=ConversationCreateResponse)
async def create_conversation(_: str = Depends(verify_api_key)):
    return ConversationCreateResponse(id=_new_conversation_id(), created_at=_now_iso())


@app.post("/v1/chat")
async def chat(body: ChatRequest, _: str = Depends(verify_api_key)):
    conversation_id = body.conversation_id or _new_conversation_id()
    response_id = f"restcmpl-{os.urandom(12).hex()}"

    if body.stream:
        chunk_generator = await pipeline.achat(
            inp=body.input, as_stream=True, thread_id=conversation_id
        )
        return StreamingResponse(
            rest_sse_from_astream(
                chunk_generator, response_id=response_id, conversation_id=conversation_id
            ),
            media_type="text/event-stream",
        )

    result_text = await pipeline.achat(
        inp=body.input, as_stream=False, thread_id=conversation_id
    )
    if not isinstance(result_text, str):
        result_text = str(result_text)
    return JSONResponse(content=ChatResponse(conversation_id=conversation_id, output=result_text).model_dump())


@app.post("/v1/conversations/{conversation_id}/messages")
async def create_message(
    body: MessageCreateRequest,
    conversation_id: str = Path(...),
    _: str = Depends(verify_api_key),
):
    if body.role != "user":
        raise HTTPException(status_code=400, detail="Only role='user' is supported")

    response_id = f"restmsg-{os.urandom(12).hex()}"

    if body.stream:
        chunk_generator = await pipeline.achat(
            inp=body.content, as_stream=True, thread_id=conversation_id
        )
        return StreamingResponse(
            rest_sse_from_astream(
                chunk_generator, response_id=response_id, conversation_id=conversation_id
            ),
            media_type="text/event-stream",
        )

    result_text = await pipeline.achat(
        inp=body.content, as_stream=False, thread_id=conversation_id
    )
    if not isinstance(result_text, str):
        result_text = str(result_text)
    out = ConversationMessageResponse(
        conversation_id=conversation_id, message=MessageResponse(content=result_text)
    )
    return JSONResponse(content=out.model_dump())


@app.delete("/v1/memory")
async def delete_all_memory(_: str = Depends(verify_api_key)):
    """Delete all conversation memory/history."""
    try:
        await pipeline.aclear_memory()
        return JSONResponse(content={"status": "success", "scope": "all"})
    except Exception as e:
        logger.error(f"Memory deletion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/v1/conversations/{conversation_id}/memory")
async def delete_conversation_memory(
    conversation_id: str = Path(...),
    _: str = Depends(verify_api_key),
):
    """
    Best-effort per-conversation memory deletion.

    Note: Pipeline exposes only global clear; per-thread delete is done by directly
    deleting the thread in the underlying MemorySaver if present.
    """
    thread_id = _normalize_thread_id(conversation_id)
    cleared = _try_clear_single_thread_memory(thread_id)
    if cleared:
        return JSONResponse(
            content={"status": "success", "scope": "conversation", "conversation_id": conversation_id}
        )
    return JSONResponse(
        content={
            "status": "unsupported",
            "message": "Per-conversation memory clearing not supported by current graph; use DELETE /v1/memory instead.",
            "conversation_id": conversation_id,
        },
        status_code=501,
    )


if __name__ == "__main__":
    uvicorn.run(
        "server_rest:app",
        host="0.0.0.0",
        port=8589,
        reload=True,
    )


