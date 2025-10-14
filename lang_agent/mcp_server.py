# https://gofastmcp.com/patterns/decorating-methods
from dataclasses import dataclass, field
from typing import Type, Literal
import tyro
from fastmcp import FastMCP
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.tools.tool import FunctionTool
from loguru import logger

from lang_agent.rag.simple import SimpleRagConfig
from lang_agent.base import LangToolBase
from lang_agent.config import InstantiateConfig


from catering_end.lang_tool import CartToolConfig, CartTool

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class MCPServerConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: MCPServer)

    server_name:str = "langserver"

    host: str = "6.6.6.78"
    """host of server"""

    port: int = 50051
    """port"""

    transport:Literal["stdio", "sse", "streamable-http"] = "streamable-http"
    """transport method"""

    # tool configs here
    rag_config: SimpleRagConfig = field(default_factory=SimpleRagConfig)

    cart_config: CartToolConfig = field(default_factory=CartToolConfig)


class MCPServer:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.mcp = FastMCP(self.config.server_name)
        self.register_mcp_functions()

    def _register_tool_fnc(self, tool:LangToolBase):
        for fnc in tool.get_tool_fnc():
            if isinstance(fnc, FunctionTool):
                fnc = fnc.fn
            self.mcp.tool(fnc)

    def register_mcp_functions(self):

        # NOTE: add config here for new tools; too stupid to do this automatically
        tool_configs = [self.config.rag_config, self.config.cart_config]
        for tool_conf in tool_configs:
            if tool_conf.use_tool:
                logger.info(f"using tool:{tool_conf._target}")
                self._register_tool_fnc(tool_conf.setup())
            else:
                logger.info(f"skipping tool:{tool_conf._target}")
    

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
