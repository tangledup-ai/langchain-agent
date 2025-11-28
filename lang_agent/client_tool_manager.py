from dataclasses import dataclass, field
from typing import Type
import tyro
import commentjson
import asyncio
import os.path as osp
from loguru import logger

from langchain_mcp_adapters.client import MultiServerMCPClient

from lang_agent.config import InstantiateConfig

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ClientToolManagerConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: ClientToolManager)

    mcp_config_f: str = None
    """path to all mcp configurations; expect json file"""

    def __post_init__(self):
        if self.mcp_config_f is None:
            self.mcp_config_f = osp.join(osp.dirname(osp.dirname(__file__)), "configs", "mcp_config.json")
            logger.warning(f"config_f was not provided. Using default: {self.mcp_config_f}")
            assert osp.exists(self.mcp_config_f), f"Default config_f {self.mcp_config_f} does not exist."

        assert osp.exists(self.mcp_config_f), f"config_f {self.mcp_config_f} does not exist."


class ClientToolManager:
    def __init__(self, config:ClientToolManagerConfig):
        self.config = config

        self.populate_module()

    def populate_module(self):
        with open(self.config.mcp_config_f, "r") as f:
            self.mcp_configs = commentjson.load(f)

        self.cli = MultiServerMCPClient(self.mcp_configs)
    
    async def aget_tools(self):
        tools = await self.cli.get_tools()
        return tools

    def get_tools(self):
        try:
            loop = asyncio.get_running_loop()
            # Event loop is already running, we need to run in a thread
            import concurrent.futures
            
            def run_in_thread():
                # Create a new event loop in this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(self.aget_tools())
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                tools = future.result()
                return tools
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            tools = asyncio.run(self.aget_tools())
            return tools

if __name__ == "__main__":
    # NOTE: Simple test
    config = ClientToolManagerConfig()
    tool_manager = ClientToolManager(config)
    tools = tool_manager.get_tools()
    [print(e.name) for e in tools]