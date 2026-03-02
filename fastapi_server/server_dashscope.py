from fastapi import FastAPI, HTTPException, Path, Request, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path as FsPath
import os
import os.path as osp
import sys
import time
import json
import copy
import uvicorn
from loguru import logger
import tyro

# Ensure we can import from project root
sys.path.append(osp.dirname(osp.dirname(osp.abspath(__file__))))

from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.config.core_config import load_tyro_conf

# Initialize default pipeline once (used when no explicit pipeline id is provided)
pipeline_config = tyro.cli(PipelineConfig)
logger.info(f"starting agent with default pipeline: \n{pipeline_config}")
pipeline: Pipeline = pipeline_config.setup()

# API Key Authentication
API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=True)
VALID_API_KEYS = set(filter(None, os.environ.get("FAST_AUTH_KEYS", "").split(",")))
REGISTRY_FILE = os.environ.get(
    "FAST_PIPELINE_REGISTRY_FILE",
    osp.join(osp.dirname(osp.dirname(osp.abspath(__file__))), "configs", "pipeline_registry.json"),
)


class PipelineManager:
    """Lazily load and cache multiple pipelines keyed by a client-facing id."""

    def __init__(self, default_pipeline_id: str, default_config: PipelineConfig, default_pipeline: Pipeline):
        self.default_pipeline_id = default_pipeline_id
        self.default_config = default_config
        self._pipeline_specs: Dict[str, Dict[str, Any]] = {}
        self._api_key_policy: Dict[str, Dict[str, Any]] = {}
        self._pipelines: Dict[str, Pipeline] = {default_pipeline_id: default_pipeline}
        self._pipeline_llm: Dict[str, str] = {default_pipeline_id: default_config.llm_name}
        self._pipeline_specs[default_pipeline_id] = {"enabled": True, "config_file": None}

    def _resolve_registry_path(self, registry_path: str) -> str:
        path = FsPath(registry_path)
        if path.is_absolute():
            return str(path)
        root = FsPath(osp.dirname(osp.dirname(osp.abspath(__file__))))
        return str((root / path).resolve())

    def load_registry(self, registry_path: str) -> None:
        abs_path = self._resolve_registry_path(registry_path)
        if not osp.exists(abs_path):
            logger.warning(f"pipeline registry file not found: {abs_path}. Using default pipeline only.")
            return

        with open(abs_path, "r", encoding="utf-8") as f:
            registry:dict = json.load(f)

        pipelines = registry.get("pipelines", {})
        if not isinstance(pipelines, dict):
            raise ValueError("`pipelines` in pipeline registry must be an object.")

        for pipeline_id, spec in pipelines.items():
            if not isinstance(spec, dict):
                raise ValueError(f"pipeline spec for `{pipeline_id}` must be an object.")
            self._pipeline_specs[pipeline_id] = {
                "enabled": bool(spec.get("enabled", True)),
                "config_file": spec.get("config_file"),
                "overrides": spec.get("overrides", {}),
            }

        api_key_policy = registry.get("api_keys", {})
        if api_key_policy and not isinstance(api_key_policy, dict):
            raise ValueError("`api_keys` in pipeline registry must be an object.")
        self._api_key_policy = api_key_policy
        logger.info(f"loaded pipeline registry: {abs_path}, pipelines={list(self._pipeline_specs.keys())}")

    def _resolve_config_path(self, config_file: str) -> str:
        path = FsPath(config_file)
        if path.is_absolute():
            return str(path)
        root = FsPath(osp.dirname(osp.dirname(osp.abspath(__file__))))
        return str((root / path).resolve())

    def _build_pipeline(self, pipeline_id: str) -> Tuple[Pipeline, str]:
        spec = self._pipeline_specs.get(pipeline_id)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"Unknown pipeline_id: {pipeline_id}")
        if not spec.get("enabled", True):
            raise HTTPException(status_code=403, detail=f"Pipeline disabled: {pipeline_id}")

        config_file = spec.get("config_file")
        overrides = spec.get("overrides", {})
        if not config_file and not overrides:
            # default pipeline
            p = self._pipelines[self.default_pipeline_id]
            llm_name = self._pipeline_llm[self.default_pipeline_id]
            return p, llm_name

        if config_file:
            cfg = load_tyro_conf(self._resolve_config_path(config_file))
        else:
            # Build from default config + shallow overrides so new pipelines can be
            # added via registry without additional yaml files.
            cfg = copy.deepcopy(self.default_config)
            if not isinstance(overrides, dict):
                raise ValueError(f"pipeline `overrides` for `{pipeline_id}` must be an object.")
            for key, value in overrides.items():
                if not hasattr(cfg, key):
                    raise ValueError(f"unknown override field `{key}` for pipeline `{pipeline_id}`")
                setattr(cfg, key, value)

        p = cfg.setup()
        llm_name = getattr(cfg, "llm_name", "unknown-model")
        return p, llm_name

    def _authorize(self, api_key: str, pipeline_id: str) -> None:
        if not self._api_key_policy:
            return

        policy = self._api_key_policy.get(api_key)
        if policy is None:
            return

        allowed = policy.get("allowed_pipeline_ids")
        if allowed and pipeline_id not in allowed:
            raise HTTPException(status_code=403, detail=f"pipeline_id `{pipeline_id}` is not allowed for this API key")

    def resolve_pipeline_id(self, body: Dict[str, Any], app_id: Optional[str], api_key: str) -> str:
        body_input = body.get("input", {})
        pipeline_id = (
            body.get("pipeline_id")
            or (body_input.get("pipeline_id") if isinstance(body_input, dict) else None)
            or app_id
        )

        if not pipeline_id:
            key_policy = self._api_key_policy.get(api_key, {}) if self._api_key_policy else {}
            pipeline_id = key_policy.get("default_pipeline_id", self.default_pipeline_id)

        if pipeline_id not in self._pipeline_specs:
            raise HTTPException(status_code=404, detail=f"Unknown pipeline_id: {pipeline_id}")

        self._authorize(api_key, pipeline_id)
        return pipeline_id

    def get_pipeline(self, pipeline_id: str) -> Tuple[Pipeline, str]:
        cached = self._pipelines.get(pipeline_id)
        if cached is not None:
            return cached, self._pipeline_llm[pipeline_id]

        pipeline_obj, llm_name = self._build_pipeline(pipeline_id)
        self._pipelines[pipeline_id] = pipeline_obj
        self._pipeline_llm[pipeline_id] = llm_name
        logger.info(f"lazy-loaded pipeline_id={pipeline_id} model={llm_name}")
        return pipeline_obj, llm_name


PIPELINE_MANAGER = PipelineManager(
    default_pipeline_id=os.environ.get("FAST_DEFAULT_PIPELINE_ID", "default"),
    default_config=pipeline_config,
    default_pipeline=pipeline,
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

    pipeline_id = PIPELINE_MANAGER.resolve_pipeline_id(body=body, app_id=req_app_id, api_key=api_key)
    selected_pipeline, selected_model = PIPELINE_MANAGER.get_pipeline(pipeline_id)

    # Namespace thread ids to prevent memory collisions across pipelines.
    thread_id = f"{pipeline_id}:{thread_id}"

    response_id = f"appcmpl-{os.urandom(12).hex()}"

    if stream:
        chunk_generator = await selected_pipeline.achat(inp=user_msg, as_stream=True, thread_id=thread_id)
        return StreamingResponse(
            sse_chunks_from_astream(chunk_generator, response_id=response_id, model=selected_model),
            media_type="text/event-stream",
        )

    result_text = await selected_pipeline.achat(inp=user_msg, as_stream=False, thread_id=thread_id)
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
        port=pipeline_config.port,
        reload=True,
    )


