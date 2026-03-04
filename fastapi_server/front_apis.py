from typing import Dict, List, Optional, Any
import commentjson
import os
import os.path as osp
import sys
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure we can import from project root.
sys.path.append(osp.dirname(osp.dirname(osp.abspath(__file__))))

from lang_agent.config.db_config_manager import DBConfigManager
from lang_agent.front_api.build_server_utils import (
    GRAPH_BUILD_FNCS,
    update_pipeline_registry,
)

_PROJECT_ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
_MCP_CONFIG_PATH = osp.join(_PROJECT_ROOT, "configs", "mcp_config.json")
_MCP_CONFIG_DEFAULT_CONTENT = "{\n}\n"
_PIPELINE_REGISTRY_PATH = osp.join(_PROJECT_ROOT, "configs", "pipeline_registry.json")


class GraphConfigUpsertRequest(BaseModel):
    graph_id: str
    pipeline_id: str
    prompt_set_id: Optional[str] = Field(default=None)
    tool_keys: List[str] = Field(default_factory=list)
    prompt_dict: Dict[str, str] = Field(default_factory=dict)
    api_key: Optional[str] = Field(default=None)


class GraphConfigUpsertResponse(BaseModel):
    graph_id: str
    pipeline_id: str
    prompt_set_id: str
    tool_keys: List[str]
    prompt_keys: List[str]
    api_key: str


class GraphConfigReadResponse(BaseModel):
    graph_id: Optional[str] = Field(default=None)
    pipeline_id: str
    prompt_set_id: str
    tool_keys: List[str]
    prompt_dict: Dict[str, str]
    api_key: str = Field(default="")


class GraphConfigListItem(BaseModel):
    graph_id: Optional[str] = Field(default=None)
    pipeline_id: str
    prompt_set_id: str
    name: str
    description: str
    is_active: bool
    tool_keys: List[str]
    api_key: str = Field(default="")
    created_at: Optional[str] = Field(default=None)
    updated_at: Optional[str] = Field(default=None)


class GraphConfigListResponse(BaseModel):
    items: List[GraphConfigListItem]
    count: int


class PipelineCreateRequest(BaseModel):
    graph_id: str = Field(
        description="Graph key from GRAPH_BUILD_FNCS, e.g. routing or react"
    )
    pipeline_id: str
    prompt_set_id: str
    tool_keys: List[str] = Field(default_factory=list)
    port: int
    api_key: str
    entry_point: str = Field(default="fastapi_server/server_dashscope.py")
    llm_name: str = Field(default="qwen-plus")
    enabled: bool = Field(default=True)


class PipelineCreateResponse(BaseModel):
    run_id: str
    pid: int
    graph_id: str
    pipeline_id: str
    prompt_set_id: str
    url: str
    port: int
    auth_type: str
    auth_header_name: str
    auth_key_once: str
    auth_key_masked: str
    enabled: bool
    config_file: str
    reload_required: bool
    registry_path: str


class PipelineRunInfo(BaseModel):
    run_id: str
    pid: int
    graph_id: str
    pipeline_id: str
    prompt_set_id: str
    url: str
    port: int
    auth_type: str
    auth_header_name: str
    auth_key_masked: str
    enabled: bool
    config_file: Optional[str] = Field(default=None)


class PipelineListResponse(BaseModel):
    items: List[PipelineRunInfo]
    count: int


class PipelineStopResponse(BaseModel):
    run_id: str
    status: str
    pipeline_id: str
    enabled: bool
    reload_required: bool


class McpConfigReadResponse(BaseModel):
    path: str
    raw_content: str
    tool_keys: List[str]


class McpConfigUpdateRequest(BaseModel):
    raw_content: str


class McpConfigUpdateResponse(BaseModel):
    status: str
    path: str
    tool_keys: List[str]


app = FastAPI(
    title="Front APIs",
    description="Manage graph configs and launch graph pipelines.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_db = DBConfigManager()
_DASHSCOPE_URL = os.environ.get("FAST_DASHSCOPE_URL", "http://127.0.0.1:8588")


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {
        "message": "Front APIs",
        "endpoints": [
            "/v1/graph-configs (POST)",
            "/v1/graph-configs (GET)",
            "/v1/graph-configs/default/{pipeline_id} (GET)",
            "/v1/graphs/{graph_id}/default-config (GET)",
            "/v1/graph-configs/{pipeline_id}/{prompt_set_id} (GET)",
            "/v1/graph-configs/{pipeline_id}/{prompt_set_id} (DELETE)",
            "/v1/pipelines/graphs (GET)",
            "/v1/pipelines (POST) - upsert route registry entry",
            "/v1/pipelines (GET) - list route registry entries",
            "/v1/pipelines/{route_id} (DELETE) - disable route",
            "/v1/tool-configs/mcp (GET)",
            "/v1/tool-configs/mcp (PUT)",
        ],
    }


def _parse_mcp_tool_keys(raw_content: str) -> List[str]:
    parsed = commentjson.loads(raw_content or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("mcp_config must be a JSON object at top level")
    return sorted(str(key) for key in parsed.keys())


def _read_mcp_config_raw() -> str:
    if not osp.exists(_MCP_CONFIG_PATH):
        os.makedirs(osp.dirname(_MCP_CONFIG_PATH), exist_ok=True)
        with open(_MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(_MCP_CONFIG_DEFAULT_CONTENT)
    with open(_MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _read_pipeline_registry() -> Dict[str, Any]:
    if not osp.exists(_PIPELINE_REGISTRY_PATH):
        os.makedirs(osp.dirname(_PIPELINE_REGISTRY_PATH), exist_ok=True)
        with open(_PIPELINE_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump({"pipelines": {}, "api_keys": {}}, f, indent=2)
    with open(_PIPELINE_REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)
    pipelines = registry.get("pipelines")
    if not isinstance(pipelines, dict):
        raise ValueError("`pipelines` in pipeline registry must be an object")
    return registry


def _write_pipeline_registry(registry: Dict[str, Any]) -> None:
    os.makedirs(osp.dirname(_PIPELINE_REGISTRY_PATH), exist_ok=True)
    with open(_PIPELINE_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")


@app.post("/v1/graph-configs", response_model=GraphConfigUpsertResponse)
async def upsert_graph_config(body: GraphConfigUpsertRequest):
    try:
        resolved_prompt_set_id = _db.set_config(
            graph_id=body.graph_id,
            pipeline_id=body.pipeline_id,
            prompt_set_id=body.prompt_set_id,
            tool_list=body.tool_keys,
            prompt_dict=body.prompt_dict,
            api_key=body.api_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return GraphConfigUpsertResponse(
        graph_id=body.graph_id,
        pipeline_id=body.pipeline_id,
        prompt_set_id=resolved_prompt_set_id,
        tool_keys=body.tool_keys,
        prompt_keys=list(body.prompt_dict.keys()),
        api_key=(body.api_key or "").strip(),
    )


@app.get("/v1/graph-configs", response_model=GraphConfigListResponse)
async def list_graph_configs(
    pipeline_id: Optional[str] = None, graph_id: Optional[str] = None
):
    try:
        rows = _db.list_prompt_sets(pipeline_id=pipeline_id, graph_id=graph_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items = [GraphConfigListItem(**row) for row in rows]
    return GraphConfigListResponse(items=items, count=len(items))


@app.get(
    "/v1/graph-configs/default/{pipeline_id}", response_model=GraphConfigReadResponse
)
async def get_default_graph_config(pipeline_id: str):
    try:
        prompt_dict, tool_keys = _db.get_config(
            pipeline_id=pipeline_id, prompt_set_id=None
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not prompt_dict and not tool_keys:
        raise HTTPException(
            status_code=404,
            detail=f"No active prompt set found for pipeline '{pipeline_id}'",
        )

    rows = _db.list_prompt_sets(pipeline_id=pipeline_id)
    active = next((row for row in rows if row["is_active"]), None)
    if active is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active prompt set found for pipeline '{pipeline_id}'",
        )

    return GraphConfigReadResponse(
        graph_id=active.get("graph_id"),
        pipeline_id=pipeline_id,
        prompt_set_id=active["prompt_set_id"],
        tool_keys=tool_keys,
        prompt_dict=prompt_dict,
        api_key=(active.get("api_key") or ""),
    )


@app.get("/v1/graphs/{graph_id}/default-config", response_model=GraphConfigReadResponse)
async def get_graph_default_config_by_graph(graph_id: str):
    return await get_default_graph_config(pipeline_id=graph_id)


@app.get(
    "/v1/graph-configs/{pipeline_id}/{prompt_set_id}",
    response_model=GraphConfigReadResponse,
)
async def get_graph_config(pipeline_id: str, prompt_set_id: str):
    try:
        meta = _db.get_prompt_set(pipeline_id=pipeline_id, prompt_set_id=prompt_set_id)
        if meta is None:
            raise HTTPException(
                status_code=404,
                detail=f"prompt_set_id '{prompt_set_id}' not found for pipeline '{pipeline_id}'",
            )
        prompt_dict, tool_keys = _db.get_config(
            pipeline_id=pipeline_id,
            prompt_set_id=prompt_set_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return GraphConfigReadResponse(
        graph_id=meta.get("graph_id"),
        pipeline_id=pipeline_id,
        prompt_set_id=prompt_set_id,
        tool_keys=tool_keys,
        prompt_dict=prompt_dict,
        api_key=(meta.get("api_key") or ""),
    )


@app.delete("/v1/graph-configs/{pipeline_id}/{prompt_set_id}")
async def delete_graph_config(pipeline_id: str, prompt_set_id: str):
    try:
        _db.remove_config(pipeline_id=pipeline_id, prompt_set_id=prompt_set_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "status": "deleted",
        "pipeline_id": pipeline_id,
        "prompt_set_id": prompt_set_id,
    }


@app.get("/v1/pipelines/graphs")
async def available_graphs():
    return {"available_graphs": sorted(GRAPH_BUILD_FNCS.keys())}


@app.get("/v1/tool-configs/mcp", response_model=McpConfigReadResponse)
async def get_mcp_tool_config():
    try:
        raw_content = _read_mcp_config_raw()
        tool_keys = _parse_mcp_tool_keys(raw_content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return McpConfigReadResponse(
        path=_MCP_CONFIG_PATH,
        raw_content=raw_content,
        tool_keys=tool_keys,
    )


@app.put("/v1/tool-configs/mcp", response_model=McpConfigUpdateResponse)
async def update_mcp_tool_config(body: McpConfigUpdateRequest):
    try:
        tool_keys = _parse_mcp_tool_keys(body.raw_content)
        os.makedirs(osp.dirname(_MCP_CONFIG_PATH), exist_ok=True)
        with open(_MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
            # Keep user formatting/comments as entered while ensuring trailing newline.
            f.write(body.raw_content.rstrip() + "\n")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return McpConfigUpdateResponse(
        status="updated",
        path=_MCP_CONFIG_PATH,
        tool_keys=tool_keys,
    )


@app.get("/v1/pipelines", response_model=PipelineListResponse)
async def list_running_pipelines():
    try:
        registry = _read_pipeline_registry()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items: List[PipelineRunInfo] = []
    pipelines = registry.get("pipelines", {})
    for pipeline_id, spec in sorted(pipelines.items()):
        if not isinstance(spec, dict):
            continue
        enabled = bool(spec.get("enabled", True))
        items.append(
            PipelineRunInfo(
                run_id=pipeline_id,
                pid=-1,
                graph_id=str(spec.get("graph_id") or pipeline_id),
                pipeline_id=pipeline_id,
                prompt_set_id="default",
                url=_DASHSCOPE_URL,
                port=-1,
                auth_type="bearer",
                auth_header_name="Authorization",
                auth_key_masked="",
                enabled=enabled,
                config_file=spec.get("config_file"),
            )
        )
    return PipelineListResponse(items=items, count=len(items))


@app.post("/v1/pipelines", response_model=PipelineCreateResponse)
async def create_pipeline(body: PipelineCreateRequest):
    build_fn = GRAPH_BUILD_FNCS.get(body.graph_id)
    if build_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown graph_id '{body.graph_id}'. Valid options: {sorted(GRAPH_BUILD_FNCS.keys())}",
        )

    pipeline_id = body.pipeline_id.strip()
    if not pipeline_id:
        raise HTTPException(status_code=400, detail="pipeline_id is required")
    config_file = f"configs/pipelines/{pipeline_id}.yml"
    config_abs_dir = osp.join(_PROJECT_ROOT, "configs", "pipelines")
    try:
        build_fn(
            pipeline_id=pipeline_id,
            prompt_set=body.prompt_set_id,
            tool_keys=body.tool_keys,
            api_key=body.api_key,
            llm_name=body.llm_name,
            pipeline_config_dir=config_abs_dir,
        )

        update_pipeline_registry(
            pipeline_id=pipeline_id,
            graph_id=body.graph_id,
            config_file=config_file,
            llm_name=body.llm_name,
            enabled=body.enabled,
            registry_f=_PIPELINE_REGISTRY_PATH,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register pipeline: {e}")

    return PipelineCreateResponse(
        run_id=pipeline_id,
        pid=-1,
        graph_id=body.graph_id,
        pipeline_id=pipeline_id,
        prompt_set_id=body.prompt_set_id,
        url=_DASHSCOPE_URL,
        port=-1,
        auth_type="bearer",
        auth_header_name="Authorization",
        auth_key_once="",
        auth_key_masked="",
        enabled=body.enabled,
        config_file=config_file,
        reload_required=True,
        registry_path=_PIPELINE_REGISTRY_PATH,
    )


@app.delete("/v1/pipelines/{pipeline_id}", response_model=PipelineStopResponse)
async def stop_pipeline(pipeline_id: str):
    try:
        registry = _read_pipeline_registry()
        pipelines = registry.get("pipelines", {})
        spec = pipelines.get(pipeline_id)
        if not isinstance(spec, dict):
            raise HTTPException(
                status_code=404, detail=f"pipeline_id '{pipeline_id}' not found"
            )
        spec["enabled"] = False
        _write_pipeline_registry(registry)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return PipelineStopResponse(
        run_id=pipeline_id,
        status="disabled",
        pipeline_id=pipeline_id,
        enabled=False,
        reload_required=True,
    )
