from dataclasses import dataclass, field
from typing import Type
import tyro
import json
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
            self.mcp_configs = json.load(f)

        self.cli = MultiServerMCPClient(self.mcp_configs)
    
    async def aget_tools(self):
        tools = await self.cli.get_tools()
        return tools

    def get_tools(self):
        tools = asyncio.run(self.aget_tools())
        return tools

if __name__ == "__main__":
    # NOTE: Simple test
    config = ClientToolManagerConfig()
    tool_manager = ClientToolManager(config)
    tools = tool_manager.get_tools()
    print(tools)