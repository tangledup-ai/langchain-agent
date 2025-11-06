# https://gofastmcp.com/patterns/decorating-methods
from dataclasses import dataclass, field, is_dataclass
from typing import Type, Literal
import tyro
from fastmcp import FastMCP
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.tools.tool import FunctionTool
from loguru import logger

from lang_agent.rag.simple import SimpleRagConfig
from lang_agent.base import LangToolBase
from lang_agent.config import InstantiateConfig, ToolConfig
from lang_agent.dummy.calculator import Calculator, CalculatorConfig
from lang_agent.tool_manager import ToolManager, ToolManagerConfig

from catering_end.lang_tool import CartToolConfig, CartTool

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class MCPServerConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: MCPServer)

    server_name:str = "langserver"

    host: str = "6.6.6.136"
    """host of server"""

    port: int = 50051
    """port"""

    transport:Literal["stdio", "sse", "streamable-http"] = "streamable-http"
    """transport method"""

    toolmanager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)


class MCPServer:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.mcp = FastMCP(self.config.server_name)

        self.populate_modules()
        self.register_mcp_functions()

    def populate_modules(self):
        self.tool_manager:ToolManager = self.config.toolmanager_config.setup()

    def register_mcp_functions(self):
        
        fncs = self.tool_manager.get_tool_fncs()
        for fnc in fncs:
            self.mcp.tool(fnc)


    def run(self):
        # 获取FastAPI应用实例
        app = self.mcp.http_app()

        # 配置CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self.mcp.run(transport=self.config.transport,
                     host=self.config.host,
                     port=self.config.port)

if __name__ == "__main__":
    conf:MCPServer = MCPServerConfig().setup()
    tool_conf = conf._get_tool_config()
    for e in tool_conf:
        print(e)