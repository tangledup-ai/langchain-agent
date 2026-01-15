from dataclasses import dataclass, field
from typing import Type
import tyro
import asyncio
import websockets
from websockets.asyncio.server import ServerConnection
from loguru import logger
import os

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
        
from lang_agent.config import InstantiateConfig, KeyConfig
from lang_agent.graphs import AnnotatedGraph, ReactGraphConfig, RoutingConfig
from lang_agent.base import GraphBase


DEFAULT_PROMPT="""you are a helpful helper
            
"""


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class PipelineConfig(KeyConfig):
    _target: Type = field(default_factory=lambda: Pipeline)

    config_f: str = None
    """path to config file"""

    llm_name: str = "qwen-plus"
    """name of llm; use default for qwen-plus"""

    llm_provider:str = "openai"
    """provider of the llm; use default for openai"""

    base_url:str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """base url; could be used to overwrite the baseurl in llm provider"""

    host:str = "0.0.0.0"
    """where am I hosted"""

    port:int = 23
    """what is my port"""

    # graph_config: AnnotatedGraph = field(default_factory=ReactGraphConfig)
    graph_config: AnnotatedGraph = field(default_factory=RoutingConfig)




class Pipeline:
    def __init__(self, config:PipelineConfig):
        self.config = config

        self.populate_module()
    
    def populate_module(self):
        if self.config.llm_name is None:
            logger.info(f"setting llm_provider to default")
            self.config.llm_name = "qwen-turbo"
            self.config.llm_provider = "openai"
        else:
            self.config.graph_config.llm_name = self.config.llm_name
            self.config.graph_config.llm_provider = self.config.llm_provider
            self.config.graph_config.base_url = self.config.base_url if self.config.base_url is not None else self.config.graph_config.base_url
            self.config.graph_config.api_key = self.config.api_key
        
        self.graph:GraphBase = self.config.graph_config.setup()

    def show_graph(self):
        if hasattr(self.graph, "show_graph"):
            logger.info("showing graph")
            self.graph.show_graph()
        else:
            logger.info(f"show graph not supported for {type(self.graph)}")

    def invoke(self, *nargs, **kwargs):
        out = self.graph.invoke(*nargs, **kwargs)

        # If streaming, yield chunks from the generator
        if kwargs.get("as_stream"):
            return self._stream_res(out)

        # Non-streaming path
        if kwargs.get("as_raw"):
            return out

        if isinstance(out, SystemMessage) or isinstance(out, HumanMessage):
            return out.content
        
        if isinstance(out, list):
            return out[-1].content
        
        if isinstance(out, str):
            return out
        
        assert 0, "something is wrong"


    def _stream_res(self, out:list):
        for chunk in out:
            yield chunk

    async def _astream_res(self, out):
        """Async version of _stream_res for async generators."""
        async for chunk in out:
            yield chunk

    def chat(self, inp:str, as_stream:bool=False, as_raw:bool=False, thread_id:str = '3'):
        """
        as_stream (bool): if true, enable the thing to be streamable
        as_raw (bool): return full dialoge of List[SystemMessage, HumanMessage, ToolMessage]
        """
        # NOTE: this prompt will be overwritten by 'configs/route_sys_prompts/chat_prompt.txt' for route graph
        u = DEFAULT_PROMPT

        device_id = "0"
        spl_ls = thread_id.split("_")
        assert len(spl_ls) <= 2, "something wrong!"
        if len(spl_ls) == 2:
            thread_id, device_id = spl_ls

        inp = {"messages":[SystemMessage(u),
                                HumanMessage(inp)]}, {"configurable": {"thread_id": thread_id,
                                                                       "device_id":device_id}}

        out = self.invoke(*inp, as_stream=as_stream, as_raw=as_raw)

        if as_stream:
            # Yield chunks from the generator
            return self._stream_res(out)
        else:
            return out

    async def ainvoke(self, *nargs, **kwargs):
        """Async version of invoke using LangGraph's native async support."""
        out = await self.graph.ainvoke(*nargs, **kwargs)

        # If streaming, return async generator
        if kwargs.get("as_stream"):
            return self._astream_res(out)

        # Non-streaming path
        if kwargs.get("as_raw"):
            return out

        if isinstance(out, SystemMessage) or isinstance(out, HumanMessage):
            return out.content
        
        if isinstance(out, list):
            return out[-1].content
        
        if isinstance(out, str):
            return out
        
        assert 0, "something is wrong"

    async def achat(self, inp:str, as_stream:bool=False, as_raw:bool=False, thread_id:str = '3'):
        """
        Async version of chat using LangGraph's native async support.
        
        as_stream (bool): if true, enable the thing to be streamable
        as_raw (bool): return full dialoge of List[SystemMessage, HumanMessage, ToolMessage]
        """
        # NOTE: this prompt will be overwritten by 'configs/route_sys_prompts/chat_prompt.txt' for route graph
        u = DEFAULT_PROMPT

        device_id = "0"
        spl_ls = thread_id.split("_")
        assert len(spl_ls) <= 2, "something wrong!"
        if len(spl_ls) == 2:
            thread_id, device_id = spl_ls
            print(f"\033[32m====================DEVICE ID: {device_id}=============================\033[0m")

        inp_data = {"messages":[SystemMessage(u),
                                HumanMessage(inp)]}, {"configurable": {"thread_id": thread_id, 
                                                                       "device_id":device_id}}

        if as_stream:
            # Return async generator for streaming
            out = await self.ainvoke(*inp_data, as_stream=True, as_raw=as_raw)
            return self._astream_res(out)
        else:
            return await self.ainvoke(*inp_data, as_stream=False, as_raw=as_raw)