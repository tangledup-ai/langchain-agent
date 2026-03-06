from typing import Dict, List, Optional, Any
import commentjson
import os
import os.path as osp
import sys
import json
import psycopg

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure we can import from project root.
sys.path.append(osp.dirname(osp.dirname(osp.abspath(__file__))))

from lang_agent.config.db_config_manager import DBConfigManager
from lang_agent.config.constants import (
    _PROJECT_ROOT,
    MCP_CONFIG_PATH,
    MCP_CONFIG_DEFAULT_CONTENT,
    PIPELINE_REGISTRY_PATH,
)
from lang_agent.front_api.build_server_utils import (
    GRAPH_BUILD_FNCS,
    update_pipeline_registry,
)
from lang_agent.components.client_tool_manager import (
    ClientToolManager,
    ClientToolManagerConfig,
)


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
    api_key: Optional[str] = Field(default=None)
    llm_name: str = Field(default="qwen-plus")
    enabled: bool = Field(default=True)


class PipelineSpec(BaseModel):
    pipeline_id: str
    graph_id: str
    enabled: bool
    config_file: str
    llm_name: str
    overrides: Dict[str, Any] = Field(default_factory=dict)


class PipelineCreateResponse(BaseModel):
    pipeline_id: str
    prompt_set_id: str
    graph_id: str
    config_file: str
    llm_name: str
    enabled: bool
    reload_required: bool
    registry_path: str


class PipelineListResponse(BaseModel):
    items: List[PipelineSpec]
    count: int


class PipelineStopResponse(BaseModel):
    pipeline_id: str
    status: str
    enabled: bool
    reload_required: bool


class ConversationListItem(BaseModel):
    conversation_id: str
    pipeline_id: str
    message_count: int
    last_updated: Optional[str] = Field(default=None)


class PipelineConversationListResponse(BaseModel):
    pipeline_id: str
    items: List[ConversationListItem]
    count: int


class ConversationMessageItem(BaseModel):
    message_type: str
    content: str
    sequence_number: int
    created_at: str


class PipelineConversationMessagesResponse(BaseModel):
    pipeline_id: str
    conversation_id: str
    items: List[ConversationMessageItem]
    count: int


class RuntimeAuthInfoResponse(BaseModel):
    fast_api_key: str
    source: str


class ApiKeyPolicyItem(BaseModel):
    api_key: str
    default_pipeline_id: Optional[str] = Field(default=None)
    allowed_pipeline_ids: List[str] = Field(default_factory=list)
    app_id: Optional[str] = Field(default=None)


class ApiKeyPolicyListResponse(BaseModel):
    items: List[ApiKeyPolicyItem]
    count: int


class ApiKeyPolicyUpsertRequest(BaseModel):
    default_pipeline_id: Optional[str] = Field(default=None)
    allowed_pipeline_ids: List[str] = Field(default_factory=list)
    app_id: Optional[str] = Field(default=None)


class ApiKeyPolicyDeleteResponse(BaseModel):
    api_key: str
    status: str
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


class McpAvailableToolsResponse(BaseModel):
    available_tools: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    servers: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


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
            "/v1/pipelines (POST) - build config + upsert pipeline registry entry",
            "/v1/pipelines (GET) - list registry pipeline specs",
            "/v1/pipelines/{pipeline_id} (DELETE) - disable pipeline in registry",
            "/v1/runtime-auth (GET) - show runtime FAST API key info",
            "/v1/pipelines/{pipeline_id}/conversations (GET) - list pipeline conversations",
            "/v1/pipelines/{pipeline_id}/conversations/{conversation_id}/messages (GET) - list messages in a conversation",
            "/v1/pipelines/api-keys (GET) - list API key routing policies",
            "/v1/pipelines/api-keys/{api_key} (PUT) - upsert API key routing policy",
            "/v1/pipelines/api-keys/{api_key} (DELETE) - delete API key routing policy",
            "/v1/tool-configs/mcp (GET)",
            "/v1/tool-configs/mcp (PUT)",
            "/v1/tool-configs/mcp/tools (GET)",
        ],
    }


def _parse_mcp_tool_keys(raw_content: str) -> List[str]:
    parsed = commentjson.loads(raw_content or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("mcp_config must be a JSON object at top level")
    return sorted(str(key) for key in parsed.keys())


def _read_mcp_config_raw() -> str:
    if not osp.exists(MCP_CONFIG_PATH):
        os.makedirs(osp.dirname(MCP_CONFIG_PATH), exist_ok=True)
        with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(MCP_CONFIG_DEFAULT_CONTENT)
    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _read_pipeline_registry() -> Dict[str, Any]:
    if not osp.exists(PIPELINE_REGISTRY_PATH):
        os.makedirs(osp.dirname(PIPELINE_REGISTRY_PATH), exist_ok=True)
        with open(PIPELINE_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump({"pipelines": {}, "api_keys": {}}, f, indent=2)
    with open(PIPELINE_REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)
    pipelines = registry.get("pipelines")
    if not isinstance(pipelines, dict):
        raise ValueError("`pipelines` in pipeline registry must be an object")
    api_keys = registry.get("api_keys")
    if api_keys is None:
        registry["api_keys"] = {}
    elif not isinstance(api_keys, dict):
        raise ValueError("`api_keys` in pipeline registry must be an object")
    return registry


def _write_pipeline_registry(registry: Dict[str, Any]) -> None:
    os.makedirs(osp.dirname(PIPELINE_REGISTRY_PATH), exist_ok=True)
    with open(PIPELINE_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")


def _resolve_runtime_fast_api_key() -> RuntimeAuthInfoResponse:
    """Pick a runtime auth key from pipeline registry first, then FAST_AUTH_KEYS env."""
    try:
        registry = _read_pipeline_registry()
        api_keys = registry.get("api_keys", {})
        if isinstance(api_keys, dict):
            for key in api_keys.keys():
                candidate = str(key).strip()
                if candidate:
                    return RuntimeAuthInfoResponse(
                        fast_api_key=candidate, source="pipeline_registry"
                    )
    except Exception:
        # fall back to env parsing below
        pass

    raw_env = os.environ.get("FAST_AUTH_KEYS", "")
    for token in raw_env.split(","):
        candidate = token.strip()
        if candidate:
            return RuntimeAuthInfoResponse(fast_api_key=candidate, source="env")
    return RuntimeAuthInfoResponse(fast_api_key="", source="none")


def _normalize_pipeline_spec(pipeline_id: str, spec: Dict[str, Any]) -> PipelineSpec:
    if not isinstance(spec, dict):
        raise ValueError(f"pipeline spec for '{pipeline_id}' must be an object")
    overrides = spec.get("overrides", {})
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise ValueError(f"`overrides` for pipeline '{pipeline_id}' must be an object")
    llm_name = str(overrides.get("llm_name") or "unknown")
    return PipelineSpec(
        pipeline_id=pipeline_id,
        graph_id=str(spec.get("graph_id") or pipeline_id),
        enabled=bool(spec.get("enabled", True)),
        config_file=str(spec.get("config_file") or ""),
        llm_name=llm_name,
        overrides=overrides,
    )


def _normalize_api_key_policy(api_key: str, policy: Dict[str, Any]) -> ApiKeyPolicyItem:
    if not isinstance(policy, dict):
        raise ValueError(f"api key policy for '{api_key}' must be an object")
    allowed = policy.get("allowed_pipeline_ids") or []
    if not isinstance(allowed, list):
        raise ValueError(
            f"`allowed_pipeline_ids` for api key '{api_key}' must be a list"
        )
    cleaned_allowed = []
    seen = set()
    for pid in allowed:
        pipeline_id = str(pid).strip()
        if not pipeline_id or pipeline_id in seen:
            continue
        seen.add(pipeline_id)
        cleaned_allowed.append(pipeline_id)
    default_pipeline_id = policy.get("default_pipeline_id")
    if default_pipeline_id is not None:
        default_pipeline_id = str(default_pipeline_id).strip() or None
    app_id = policy.get("app_id")
    if app_id is not None:
        app_id = str(app_id).strip() or None
    return ApiKeyPolicyItem(
        api_key=api_key,
        default_pipeline_id=default_pipeline_id,
        allowed_pipeline_ids=cleaned_allowed,
        app_id=app_id,
    )


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
        path=MCP_CONFIG_PATH,
        raw_content=raw_content,
        tool_keys=tool_keys,
    )


@app.put("/v1/tool-configs/mcp", response_model=McpConfigUpdateResponse)
async def update_mcp_tool_config(body: McpConfigUpdateRequest):
    try:
        tool_keys = _parse_mcp_tool_keys(body.raw_content)
        os.makedirs(osp.dirname(MCP_CONFIG_PATH), exist_ok=True)
        with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
            # Keep user formatting/comments as entered while ensuring trailing newline.
            f.write(body.raw_content.rstrip() + "\n")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return McpConfigUpdateResponse(
        status="updated",
        path=MCP_CONFIG_PATH,
        tool_keys=tool_keys,
    )


@app.get("/v1/tool-configs/mcp/tools", response_model=McpAvailableToolsResponse)
async def list_mcp_available_tools():
    try:
        _read_mcp_config_raw()
        manager = ClientToolManager(
            ClientToolManagerConfig(mcp_config_f=MCP_CONFIG_PATH)
        )
        servers = await manager.aget_tools_by_server()
        available_tools = sorted(
            {
                tool_name
                for server_info in servers.values()
                for tool_name in server_info.get("tools", [])
            }
        )
        errors = [
            f"{server_name}: {server_info.get('error')}"
            for server_name, server_info in servers.items()
            if server_info.get("error")
        ]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return McpAvailableToolsResponse(
        available_tools=available_tools,
        errors=errors,
        servers=servers,
    )


@app.get("/v1/pipelines", response_model=PipelineListResponse)
async def list_running_pipelines():
    try:
        registry = _read_pipeline_registry()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items: List[PipelineSpec] = []
    pipelines = registry.get("pipelines", {})
    for pipeline_id, spec in sorted(pipelines.items()):
        items.append(_normalize_pipeline_spec(pipeline_id, spec))
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
    prompt_set_id = body.prompt_set_id.strip()
    if not prompt_set_id:
        raise HTTPException(status_code=400, detail="prompt_set_id is required")

    resolved_api_key = (body.api_key or "").strip()
    if not resolved_api_key:
        meta = _db.get_prompt_set(pipeline_id=pipeline_id, prompt_set_id=prompt_set_id)
        if meta is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"prompt_set_id '{prompt_set_id}' not found for pipeline '{pipeline_id}', "
                    "and request api_key is empty"
                ),
            )
        resolved_api_key = str(meta.get("api_key") or "").strip()
    if not resolved_api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "api_key is required either in request body or in prompt set metadata"
            ),
        )

    config_file = f"configs/pipelines/{pipeline_id}.yaml"
    config_abs_dir = osp.join(_PROJECT_ROOT, "configs", "pipelines")
    try:
        build_fn(
            pipeline_id=pipeline_id,
            prompt_set=prompt_set_id,
            tool_keys=body.tool_keys,
            api_key=resolved_api_key,
            llm_name=body.llm_name,
            pipeline_config_dir=config_abs_dir,
        )

        update_pipeline_registry(
            pipeline_id=pipeline_id,
            graph_id=body.graph_id,
            config_file=config_file,
            llm_name=body.llm_name,
            enabled=body.enabled,
            registry_f=PIPELINE_REGISTRY_PATH,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register pipeline: {e}")

    try:
        registry = _read_pipeline_registry()
        pipeline_spec = registry.get("pipelines", {}).get(pipeline_id)
        if pipeline_spec is None:
            raise ValueError(
                f"pipeline '{pipeline_id}' missing from registry after update"
            )
        normalized = _normalize_pipeline_spec(pipeline_id, pipeline_spec)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read pipeline registry after update: {e}",
        )

    return PipelineCreateResponse(
        pipeline_id=pipeline_id,
        prompt_set_id=prompt_set_id,
        graph_id=normalized.graph_id,
        config_file=normalized.config_file,
        llm_name=normalized.llm_name,
        enabled=normalized.enabled,
        reload_required=False,
        registry_path=PIPELINE_REGISTRY_PATH,
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
        pipeline_id=pipeline_id,
        status="disabled",
        enabled=False,
        reload_required=False,
    )


@app.get("/v1/runtime-auth", response_model=RuntimeAuthInfoResponse)
async def get_runtime_auth_info():
    return _resolve_runtime_fast_api_key()


@app.get(
    "/v1/pipelines/{pipeline_id}/conversations",
    response_model=PipelineConversationListResponse,
)
async def list_pipeline_conversations(pipeline_id: str, limit: int = 100):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")

    conn_str = os.environ.get("CONN_STR")
    if not conn_str:
        raise HTTPException(status_code=500, detail="CONN_STR not set")

    try:
        with psycopg.connect(conn_str) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        conversation_id,
                        pipeline_id,
                        COUNT(*) AS message_count,
                        MAX(created_at) AS last_updated
                    FROM messages
                    WHERE pipeline_id = %s
                    GROUP BY conversation_id, pipeline_id
                    ORDER BY last_updated DESC
                    LIMIT %s
                    """,
                    (pipeline_id, limit),
                )
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items = [
        ConversationListItem(
            conversation_id=str(row["conversation_id"]),
            pipeline_id=str(row["pipeline_id"]),
            message_count=int(row["message_count"]),
            last_updated=(
                row["last_updated"].isoformat() if row.get("last_updated") else None
            ),
        )
        for row in rows
    ]
    return PipelineConversationListResponse(
        pipeline_id=pipeline_id, items=items, count=len(items)
    )


@app.get(
    "/v1/pipelines/{pipeline_id}/conversations/{conversation_id}/messages",
    response_model=PipelineConversationMessagesResponse,
)
async def get_pipeline_conversation_messages(pipeline_id: str, conversation_id: str):
    conn_str = os.environ.get("CONN_STR")
    if not conn_str:
        raise HTTPException(status_code=500, detail="CONN_STR not set")

    try:
        with psycopg.connect(conn_str) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM messages
                    WHERE pipeline_id = %s AND conversation_id = %s
                    LIMIT 1
                    """,
                    (pipeline_id, conversation_id),
                )
                exists = cur.fetchone()
                if exists is None:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            f"conversation_id '{conversation_id}' not found for "
                            f"pipeline '{pipeline_id}'"
                        ),
                    )

                cur.execute(
                    """
                    SELECT
                        message_type,
                        content,
                        sequence_number,
                        created_at
                    FROM messages
                    WHERE pipeline_id = %s AND conversation_id = %s
                    ORDER BY sequence_number ASC
                    """,
                    (pipeline_id, conversation_id),
                )
                rows = cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items = [
        ConversationMessageItem(
            message_type=str(row["message_type"]),
            content=str(row["content"]),
            sequence_number=int(row["sequence_number"]),
            created_at=row["created_at"].isoformat() if row.get("created_at") else "",
        )
        for row in rows
    ]
    return PipelineConversationMessagesResponse(
        pipeline_id=pipeline_id,
        conversation_id=conversation_id,
        items=items,
        count=len(items),
    )


@app.get("/v1/pipelines/api-keys", response_model=ApiKeyPolicyListResponse)
async def list_pipeline_api_keys():
    try:
        registry = _read_pipeline_registry()
        api_keys = registry.get("api_keys", {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items: List[ApiKeyPolicyItem] = []
    for api_key, policy in sorted(api_keys.items()):
        items.append(_normalize_api_key_policy(str(api_key), policy))
    return ApiKeyPolicyListResponse(items=items, count=len(items))


@app.put(
    "/v1/pipelines/api-keys/{api_key}",
    response_model=ApiKeyPolicyItem,
)
async def upsert_pipeline_api_key_policy(api_key: str, body: ApiKeyPolicyUpsertRequest):
    normalized_key = api_key.strip()
    if not normalized_key:
        raise HTTPException(
            status_code=400, detail="api_key path parameter is required"
        )
    try:
        registry = _read_pipeline_registry()
        pipelines = registry.get("pipelines", {})
        if not isinstance(pipelines, dict):
            raise ValueError("`pipelines` in pipeline registry must be an object")
        known_pipeline_ids = set(pipelines.keys())

        allowed = []
        seen = set()
        for pipeline_id in body.allowed_pipeline_ids:
            cleaned = str(pipeline_id).strip()
            if not cleaned or cleaned in seen:
                continue
            if cleaned not in known_pipeline_ids:
                raise ValueError(
                    f"unknown pipeline_id '{cleaned}' in allowed_pipeline_ids"
                )
            seen.add(cleaned)
            allowed.append(cleaned)

        default_pipeline_id = body.default_pipeline_id
        if default_pipeline_id is not None:
            default_pipeline_id = default_pipeline_id.strip() or None
        if default_pipeline_id and default_pipeline_id not in known_pipeline_ids:
            raise ValueError(f"unknown default_pipeline_id '{default_pipeline_id}'")

        app_id = body.app_id.strip() if body.app_id else None
        policy: Dict[str, Any] = {}
        if default_pipeline_id:
            policy["default_pipeline_id"] = default_pipeline_id
        if allowed:
            policy["allowed_pipeline_ids"] = allowed
        if app_id:
            policy["app_id"] = app_id

        registry.setdefault("api_keys", {})[normalized_key] = policy
        _write_pipeline_registry(registry)
        return _normalize_api_key_policy(normalized_key, policy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete(
    "/v1/pipelines/api-keys/{api_key}",
    response_model=ApiKeyPolicyDeleteResponse,
)
async def delete_pipeline_api_key_policy(api_key: str):
    normalized_key = api_key.strip()
    if not normalized_key:
        raise HTTPException(
            status_code=400, detail="api_key path parameter is required"
        )
    try:
        registry = _read_pipeline_registry()
        api_keys = registry.get("api_keys", {})
        if normalized_key not in api_keys:
            raise HTTPException(
                status_code=404, detail=f"api_key '{normalized_key}' not found"
            )
        del api_keys[normalized_key]
        _write_pipeline_registry(registry)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ApiKeyPolicyDeleteResponse(
        api_key=normalized_key,
        status="deleted",
        reload_required=False,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "front_apis:app",
        host="0.0.0.0",
        port=8500,
        reload=True,
    )
