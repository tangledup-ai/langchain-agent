from typing import Dict, List, Optional
import os
import os.path as osp
import subprocess
import sys
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure we can import from project root.
sys.path.append(osp.dirname(osp.dirname(osp.abspath(__file__))))

from lang_agent.config.db_config_manager import DBConfigManager
from lang_agent.front_api.build_server import GRAPH_BUILD_FNCS

class GraphConfigUpsertRequest(BaseModel):
    graph_id: str
    pipeline_id: str
    prompt_set_id: Optional[str] = Field(default=None)
    tool_keys: List[str] = Field(default_factory=list)
    prompt_dict: Dict[str, str] = Field(default_factory=dict)

class GraphConfigUpsertResponse(BaseModel):
    graph_id: str
    pipeline_id: str
    prompt_set_id: str
    tool_keys: List[str]
    prompt_keys: List[str]

class GraphConfigReadResponse(BaseModel):
    graph_id: Optional[str] = Field(default=None)
    pipeline_id: str
    prompt_set_id: str
    tool_keys: List[str]
    prompt_dict: Dict[str, str]

class GraphConfigListItem(BaseModel):
    graph_id: Optional[str] = Field(default=None)
    pipeline_id: str
    prompt_set_id: str
    name: str
    description: str
    is_active: bool
    tool_keys: List[str]
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

class PipelineCreateResponse(BaseModel):
    run_id: str
    pid: int
    graph_id: str
    pipeline_id: str
    prompt_set_id: str
    url: str
    port: int

class PipelineRunInfo(BaseModel):
    run_id: str
    pid: int
    graph_id: str
    pipeline_id: str
    prompt_set_id: str
    url: str
    port: int

class PipelineListResponse(BaseModel):
    items: List[PipelineRunInfo]
    count: int

class PipelineStopResponse(BaseModel):
    run_id: str
    status: str


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
_running_pipelines: Dict[str, Dict[str, object]] = {}

def _prune_stopped_pipelines() -> None:
    stale_ids: List[str] = []
    for run_id, info in _running_pipelines.items():
        proc = info["proc"]
        if proc.poll() is not None:
            stale_ids.append(run_id)
    for run_id in stale_ids:
        _running_pipelines.pop(run_id, None)


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
            "/v1/pipelines (POST)",
            "/v1/pipelines (GET)",
            "/v1/pipelines/{run_id} (DELETE)",
        ],
    }


@app.post("/v1/graph-configs", response_model=GraphConfigUpsertResponse)
async def upsert_graph_config(body: GraphConfigUpsertRequest):
    try:
        resolved_prompt_set_id = _db.set_config(
            graph_id=body.graph_id,
            pipeline_id=body.pipeline_id,
            prompt_set_id=body.prompt_set_id,
            tool_list=body.tool_keys,
            prompt_dict=body.prompt_dict,
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
    )

@app.get("/v1/graph-configs", response_model=GraphConfigListResponse)
async def list_graph_configs(pipeline_id: Optional[str] = None, graph_id: Optional[str] = None):
    try:
        rows = _db.list_prompt_sets(pipeline_id=pipeline_id, graph_id=graph_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items = [GraphConfigListItem(**row) for row in rows]
    return GraphConfigListResponse(items=items, count=len(items))

@app.get("/v1/graph-configs/default/{pipeline_id}", response_model=GraphConfigReadResponse)
async def get_default_graph_config(pipeline_id: str):
    try:
        prompt_dict, tool_keys = _db.get_config(pipeline_id=pipeline_id, prompt_set_id=None)
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
    )

@app.get("/v1/graphs/{graph_id}/default-config", response_model=GraphConfigReadResponse)
async def get_graph_default_config_by_graph(graph_id: str):
    return await get_default_graph_config(pipeline_id=graph_id)

@app.get("/v1/graph-configs/{pipeline_id}/{prompt_set_id}", response_model=GraphConfigReadResponse)
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

@app.get("/v1/pipelines", response_model=PipelineListResponse)
async def list_running_pipelines():
    _prune_stopped_pipelines()
    items = [
        PipelineRunInfo(
            run_id=run_id,
            pid=info["proc"].pid,
            graph_id=info["graph_id"],
            pipeline_id=info["pipeline_id"],
            prompt_set_id=info["prompt_set_id"],
            url=info["url"],
            port=info["port"],
        )
        for run_id, info in _running_pipelines.items()
    ]
    return PipelineListResponse(items=items, count=len(items))


@app.post("/v1/pipelines", response_model=PipelineCreateResponse)
async def create_pipeline(body: PipelineCreateRequest):
    build_fn = GRAPH_BUILD_FNCS.get(body.graph_id)
    if build_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown graph_id '{body.graph_id}'. Valid options: {sorted(GRAPH_BUILD_FNCS.keys())}",
        )

    try:
        proc, url = build_fn(
            pipeline_id=body.pipeline_id,
            prompt_set=body.prompt_set_id,
            tool_keys=body.tool_keys,
            port=str(body.port),
            api_key=body.api_key,
            entry_pnt=body.entry_point,
            llm_name=body.llm_name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start pipeline: {e}")

    run_id = str(uuid.uuid4())
    _running_pipelines[run_id] = {
        "proc": proc,
        "graph_id": body.graph_id,
        "pipeline_id": body.pipeline_id,
        "prompt_set_id": body.prompt_set_id,
        "url": url,
        "port": body.port,
    }

    return PipelineCreateResponse(
        run_id=run_id,
        pid=proc.pid,
        graph_id=body.graph_id,
        pipeline_id=body.pipeline_id,
        prompt_set_id=body.prompt_set_id,
        url=url,
        port=body.port,
    )

@app.delete("/v1/pipelines/{run_id}", response_model=PipelineStopResponse)
async def stop_pipeline(run_id: str):
    info = _running_pipelines.pop(run_id, None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"run_id '{run_id}' not found")

    proc = info["proc"]
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    return PipelineStopResponse(run_id=run_id, status="stopped")
