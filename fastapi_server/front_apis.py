from typing import Dict, List, Optional
import os
import os.path as osp
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
    pipeline_id: str
    prompt_set_id: Optional[str] = Field(default=None)
    tool_keys: List[str] = Field(default_factory=list)
    prompt_dict: Dict[str, str] = Field(default_factory=dict)

class GraphConfigUpsertResponse(BaseModel):
    pipeline_id: str
    prompt_set_id: str
    tool_keys: List[str]
    prompt_keys: List[str]

class PipelineCreateRequest(BaseModel):
    graph_id: str = Field(
        description="Graph key from GRAPH_BUILD_FNCS, e.g. routing or react"
    )
    pipeline_id: str
    prompt_set_id: str
    tool_keys: List[str] = Field(default_factory=list)
    port: int
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


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {
        "message": "Front APIs",
        "endpoints": [
            "/v1/graph-configs (POST)",
            "/v1/graph-configs/{pipeline_id}/{prompt_set_id} (DELETE)",
            "/v1/pipelines/graphs (GET)",
            "/v1/pipelines (POST)",
        ],
    }


@app.post("/v1/graph-configs", response_model=GraphConfigUpsertResponse)
async def upsert_graph_config(body: GraphConfigUpsertRequest):
    try:
        resolved_prompt_set_id = _db.set_config(
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
        pipeline_id=body.pipeline_id,
        prompt_set_id=resolved_prompt_set_id,
        tool_keys=body.tool_keys,
        prompt_keys=list(body.prompt_dict.keys()),
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
            pipelin_id=body.pipeline_id,
            prompt_set=body.prompt_set_id,
            tool_keys=body.tool_keys,
            port=str(body.port),
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
