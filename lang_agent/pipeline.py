from dataclasses import dataclass, field
from typing import Type
import tyro
import asyncio
import websockets
from loguru import logger

from langchain.chat_models import init_chat_model

from lang_agent.config import InstantiateConfig

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
    # strat: BothConfig = field(default_factory=BothConfig)


class Pipeline:
    def __init__(self, config:PipelineConfig):
        self.config = config
    
    def populate_module(self):
        self.llm = init_chat_model(model=self.config.llm_name,
                                   model_provider=self.config.llm_provider,
                                   api_key=self.config.api_key,
                                   base_url=self.config.base_url)
        
        self.agent = self.llm ## NOTE: placeholder for now
    

    async def handle_connection(self, inp:str):
        return "hello"
    

    async def start_server(self):
        async with websockets.serve(
            self.handle_connection,
            host=self.config.host,
            port=self.config.port,
            max_size=None,   # allow large messages
            max_queue=None,  # don't bound outgoing queue
        ):
            # print("WebSocket server listening on ws://0.0.0.0:8765")
            logger.info(f"listening to ws://{self.config.host}:{self.config.port}")
            await asyncio.Future()
    


