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
from lang_agent.components.runtime_services import runtime_services_lifespan
from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.config.constants import API_KEY_HEADER_NO_ERROR

# Keep both import paths pointing at the same module so tests patching either
# `fastapi_server.server_rest` or `lang_agent.fastapi_server.server_rest`
# affect the same globals.
sys.modules.setdefault("fastapi_server.server_rest", sys.modules[__name__])
sys.modules.setdefault("lang_agent.fastapi_server.server_rest", sys.modules[__name__])


def _build_default_pipeline_config() -> PipelineConfig:
    """
    Build import-time defaults without parsing CLI args.

    This keeps module import safe for tests and combined apps.
    """
    cfg = PipelineConfig()
    logger.info(f"starting agent with default pipeline config: \n{cfg}")
    return cfg


pipeline_config = _build_default_pipeline_config()
pipeline: Pipeline = pipeline_config.setup()

# API Key Authentication

async def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER_NO_ERROR)):
    """Verify the API key from Authorization header (Bearer token format)."""
    if not api_key:
        # Tests expect 401 (not FastAPI's default 403) when auth header is missing.
        raise HTTPException(status_code=401, detail="Missing API key")
    key = api_key[7:] if api_key.startswith("Bearer ") else api_key
    valid_api_keys = set(
        filter(None, os.environ.get("FAST_AUTH_KEYS", "").split(","))
    )
    if valid_api_keys and key not in valid_api_keys:
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
    lifespan=runtime_services_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def rest_sse_from_astream(
    chunk_generator, response_id: str, conversation_id: str
):
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
                chunk_generator,
                response_id=response_id,
                conversation_id=conversation_id,
            ),
            media_type="text/event-stream",
        )

    result_text = await pipeline.achat(
        inp=body.input, as_stream=False, thread_id=conversation_id
    )
    if not isinstance(result_text, str):
        result_text = str(result_text)
    return JSONResponse(
        content=ChatResponse(
            conversation_id=conversation_id, output=result_text
        ).model_dump()
    )


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
                chunk_generator,
                response_id=response_id,
                conversation_id=conversation_id,
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
            content={
                "status": "success",
                "scope": "conversation",
                "conversation_id": conversation_id,
            }
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
    cli_pipeline_config = tyro.cli(PipelineConfig)
    logger.info(f"starting agent with CLI pipeline config: \n{cli_pipeline_config}")
    pipeline = cli_pipeline_config.setup()
    uvicorn.run(
        "server_rest:app",
        host=cli_pipeline_config.host,
        port=cli_pipeline_config.port,
        reload=False,
    )
