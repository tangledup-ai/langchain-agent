from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal
import os
import sys
import time
import json
import uvicorn
from loguru import logger
import tyro

# Ensure we can import from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lang_agent.pipeline import Pipeline, PipelineConfig

# Initialize Pipeline once
pipeline_config = tyro.cli(PipelineConfig)
pipeline: Pipeline = pipeline_config.setup()


class OpenAIMessage(BaseModel):
    role: str
    content: str


class OpenAIChatCompletionRequest(BaseModel):
    model: str = Field(default="gpt-3.5-turbo")
    messages: List[OpenAIMessage]
    stream: bool = Field(default=False)
    temperature: Optional[float] = Field(default=1.0)
    max_tokens: Optional[int] = Field(default=None)
    # Optional overrides for pipeline behavior
    thread_id: Optional[int] = Field(default=3)


app = FastAPI(
    title="OpenAI-Compatible Chat API",
    description="OpenAI Chat Completions API compatible endpoint backed by pipeline.chat"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def sse_chunks_from_stream(chunk_generator, response_id: str, model: str, created_time: int):
    """
    Stream chunks from pipeline and format as OpenAI SSE.
    """
    for chunk in chunk_generator:
        if chunk:
            data = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": chunk
                        },
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(data)}\n\n"

    # Final message
    final = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }
        ]
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


async def sse_chunks_from_astream(chunk_generator, response_id: str, model: str, created_time: int):
    """
    Async version: Stream chunks from pipeline and format as OpenAI SSE.
    """
    async for chunk in chunk_generator:
        if chunk:
            data = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": chunk
                        },
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(data)}\n\n"

    # Final message
    final = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }
        ]
    }
    yield f"data: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
        
        messages = body.get("messages")
        if not messages:
            raise HTTPException(status_code=400, detail="messages is required")
        
        stream = body.get("stream", False)
        model = body.get("model", "gpt-3.5-turbo")
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
        
        response_id = f"chatcmpl-{os.urandom(12).hex()}"
        created_time = int(time.time())
        
        if stream:
            # Use async streaming from pipeline
            chunk_generator = await pipeline.achat(inp=user_msg, as_stream=True, thread_id=thread_id)
            return StreamingResponse(
                sse_chunks_from_astream(chunk_generator, response_id=response_id, model=model, created_time=created_time),
                media_type="text/event-stream",
            )
        
        # Non-streaming: get full result using async
        result_text = await pipeline.achat(inp=user_msg, as_stream=False, thread_id=thread_id)
        if not isinstance(result_text, str):
            result_text = str(result_text)
        
        data = {
            "id": response_id,
            "object": "chat.completion",
            "created": created_time,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result_text
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        return JSONResponse(content=data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OpenAI-compatible endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {
        "message": "OpenAI-compatible Chat API",
        "endpoints": [
            "/v1/chat/completions",
            "/health"
        ]
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "server_openai:app",
        host="0.0.0.0",
        port=8589,
        reload=True,
    )
