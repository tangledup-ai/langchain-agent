from dataclasses import dataclass, field
from typing import Type, List
import tyro
import asyncio
import websockets
from websockets.asyncio.server import ServerConnection
from loguru import logger
import os

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
        
from lang_agent.config import InstantiateConfig
from lang_agent.tool_manager import ToolManager, ToolManagerConfig

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class PipelineConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: Pipeline)

    config_f: str = None
    """path to config file"""

    llm_name: str = "qwen-turbo"
    """name of llm"""

    llm_provider:str = "openai"
    """provider of the llm"""

    api_key:str = None
    """api key for llm"""

    base_url:str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """base url; could be used to overwrite the baseurl in llm provider"""

    host:str = "0.0.0.0"
    """where am I hosted"""

    port:int = 23
    """what is my port"""

    # NOTE: For reference
    tool_manager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)

    def __post_init__(self):
        if self.api_key == "wrong-key" or self.api_key is None:
            # logger.info("wrong embedding key, using simple retrieval method")
            self.api_key = os.environ.get("ALI_API_KEY")
            if self.api_key is None:
                logger.error(f"no ALI_API_KEY provided for embedding")
            else:
                logger.info("ALI_API_KEY loaded from environ")



class Pipeline:
    def __init__(self, config:PipelineConfig):
        self.config = config

        self.populate_module()
    
    def populate_module(self):
        self.llm = init_chat_model(model=self.config.llm_name,
                                   model_provider=self.config.llm_provider,
                                   api_key=self.config.api_key,
                                   base_url=self.config.base_url)
        
        # NOTE: placeholder for now, add graph later
        self.tool_manager:ToolManager = self.config.tool_manager_config.setup()
        memory = MemorySaver()
        tools = self.tool_manager.get_tools()
        self.agent = create_react_agent(self.llm, tools, checkpointer=memory)
    
    def respond(self, msg:str | List[SystemMessage, HumanMessage]):
        return self.agent.invoke(msg)

    async def handle_connection(self, websocket:ServerConnection):
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    #NOTE: For binary, echo back.
                    await websocket.send(message)
                else:
                    # TODO: handle this better, will have system/user prompt send here
                    response = self.respond(message)
                    await websocket.send(response)
        except websockets.ConnectionClosed:
            pass
    

    async def start_server(self):
        async with websockets.serve(
            self.handle_connection,
            host=self.config.host,
            port=self.config.port,
            max_size=None,   # allow large messages
            max_queue=None,  # don't bound outgoing queue
        ):
            logger.info(f"listening to {self.get_ws_url}")
            await asyncio.Future()
    
    def get_ws_url(self):
        return f"ws://{self.config.host}:{self.config.port}"
    


