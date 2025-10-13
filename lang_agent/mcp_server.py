# https://gofastmcp.com/patterns/decorating-methods
from dataclasses import dataclass, field
from typing import Type, Literal
import tyro
from mcp.server.fastmcp import FastMCP
from loguru import logger

from lang_agent.rag.simple import SimpleRag, SimpleRagConfig
from lang_agent.base import LangToolBase
from lang_agent.config import InstantiateConfig


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class MCPServerConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: MCPServer)

    server_name:str = "langserver"

    host: str = "localhost"
    """host of server"""

    port: int = 50051
    """port"""

    transport:Literal["stdio", "sse", "streamable-http"] = "streamable-http"
    """transport method"""

    # tool configs here
    rag_config: SimpleRagConfig = field(default_factory=SimpleRagConfig)


class MCPServer:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.mcp = FastMCP(self.config.server_name)

    def _register_tool_fnc(self, tool:LangToolBase):
        for fnc in tool.get_tool_fnc():
            self.mcp.tool(fnc)

    def register_mcp_functions(self):

        # NOTE: add config here for new tools; too stupid to do this automatically
        tool_configs = [self.config.rag_config]
        for tool_conf in tool_configs:
            if tool_conf.use_tool:
                logger.info(f"using tool:{tool_conf._target}")
                self._register_tool_fnc(tool_conf.setup())
            else:
                logger.info(f"skipping tool:{tool_conf._target}")
    

    def run(self):
        self.mcp.run(transport=self.config.transport,
                     host=self.config.host,
                     port=self.config.port)
