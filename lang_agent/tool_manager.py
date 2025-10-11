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
class ToolManagerConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: ToolManager)

    config_f: str = None
    """path to all mcp configurations; expect json file"""

    def __post_init__(self):
        if self.config_f is None:
            self.config_f = osp.join(osp.dirname(osp.dirname(__file__)), "config", "mcp_config.json")
            logger.warning(f"config_f was not provided. Using default: {self.config_f}")

class ToolManager:
    def __init__(self, config:ToolManagerConfig):
        self.config = config

        self.populate_module()

    def populate_module(self):
        with open(self.config.config_f, "r") as f:
            self.mcp_configs = json.load(f)

        self.cli = MultiServerMCPClient(self.mcp_configs)
    
    async def aget_tools(self):
        tools = await self.cli.get_tools()
        return tools

    def get_tools(self):
        tools = asyncio.run(self.aget_tools())
        return tools
