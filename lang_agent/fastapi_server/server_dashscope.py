from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
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

from lang_agent.components.runtime_services import runtime_services_lifespan
from lang_agent.pipeline import PipelineConfig
from lang_agent.components.server_pipeline_manager import ServerPipelineManager
from lang_agent.config.constants import PIPELINE_REGISTRY_PATH, API_KEY_HEADER, VALID_API_KEYS

def _build_default_pipeline_config() -> PipelineConfig:
    """
    Build import-time defaults without parsing CLI args.

    This keeps module import safe for reuse by combined apps and tests.
    """
    pipeline_config = PipelineConfig()
    logger.info(f"starting agent with base pipeline config: \n{pipeline_config}")
    return pipeline_config


def _build_pipeline_manager(base_config: PipelineConfig) -> ServerPipelineManager:
    pipeline_manager = ServerPipelineManager(
        default_pipeline_id=os.environ.get("FAST_DEFAULT_PIPELINE_ID", "default"),
        default_config=base_config,
    )
    pipeline_manager.load_registry(PIPELINE_REGISTRY_PATH)
    return pipeline_manager


pipeline_config = _build_default_pipeline_config()
PIPELINE_MANAGER = _build_pipeline_manager(pipeline_config)


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
    pipeline_manager: ServerPipelineManager,
):
    try:
        pipeline_manager.refresh_registry_if_needed()
    except Exception as e:
        logger.error(f"failed to refresh pipeline registry: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh pipeline registry: {e}")

    req_app_id = app_id or body.get("app_id")
    body_input = body.get("input", {}) if isinstance(body.get("input"), dict) else {}
    req_session_id = session_id or body_input.get("session_id")
    messages = _normalize_messages(body)

    stream = body.get("stream")
    if stream is None:
        stream = body.get("parameters", {}).get("stream", True)

    thread_id = body_input.get("session_id") or req_session_id or "3"
    user_msg = _extract_user_message(messages)

    pipeline_id = pipeline_manager.resolve_pipeline_id(
        body=body, app_id=req_app_id, api_key=api_key
    )
    selected_pipeline, selected_model = pipeline_manager.get_pipeline(pipeline_id)

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


def create_dashscope_router(
    pipeline_manager: Optional[ServerPipelineManager] = None,
    include_meta_routes: bool = True,
) -> APIRouter:
    manager = pipeline_manager or PIPELINE_MANAGER
    router = APIRouter()

    @router.post("/v1/apps/{app_id}/sessions/{session_id}/responses")
    @router.post("/api/v1/apps/{app_id}/sessions/{session_id}/responses")
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
                pipeline_manager=manager,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DashScope-compatible endpoint error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Compatibility: some SDKs call /apps/{app_id}/completion without /v1 and
    # without session in path.
    @router.post("/apps/{app_id}/completion")
    @router.post("/v1/apps/{app_id}/completion")
    @router.post("/api/apps/{app_id}/completion")
    @router.post("/api/v1/apps/{app_id}/completion")
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
                pipeline_manager=manager,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DashScope-compatible completion error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    if include_meta_routes:
        @router.get("/")
        async def root():
            return {
                "message": "DashScope Application-compatible API",
                "endpoints": [
                    "/v1/apps/{app_id}/sessions/{session_id}/responses",
                    "/health",
                ],
            }

        @router.get("/health")
        async def health():
            return {"status": "healthy"}

    return router


def create_dashscope_app(
    pipeline_manager: Optional[ServerPipelineManager] = None,
) -> FastAPI:
    dashscope_app = FastAPI(
        title="DashScope-Compatible Application API",
        description="DashScope Application.call compatible endpoint backed by pipeline.chat",
        lifespan=runtime_services_lifespan,
    )
    dashscope_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    dashscope_app.include_router(
        create_dashscope_router(
            pipeline_manager=pipeline_manager,
            include_meta_routes=True,
        )
    )
    return dashscope_app


dashscope_router = create_dashscope_router(include_meta_routes=False)
app = create_dashscope_app()


if __name__ == "__main__":
    # CLI parsing is intentionally only in script mode to keep module import safe.
    cli_pipeline_config = tyro.cli(PipelineConfig)
    logger.info(f"starting agent with CLI pipeline config: \n{cli_pipeline_config}")
    cli_pipeline_manager = _build_pipeline_manager(cli_pipeline_config)
    uvicorn.run(
        create_dashscope_app(pipeline_manager=cli_pipeline_manager),
        host=cli_pipeline_config.host,
        port=cli_pipeline_config.port,
        reload=False,
    )
