from dataclasses import dataclass, field, is_dataclass
import functools
from typing import Type, List, Callable, Any
import tyro
import inspect
import asyncio
import os.path as osp
from loguru import logger
from fastmcp.tools.tool import FunctionTool

from lang_agent.config import InstantiateConfig, ToolConfig
from lang_agent.base import LangToolBase

from lang_agent.rag.simple import SimpleRagConfig
from lang_agent.dummy.calculator import CalculatorConfig
# from catering_end.lang_tool import CartToolConfig, CartTool

from langchain_core.tools.structured import StructuredTool
from lang_agent.client_tool_manager import ClientToolManager
import jax

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ToolManagerConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: ToolManager)

    # tool configs here; MUST HAVE 'config' in name and must be dataclass
    rag_config: SimpleRagConfig = field(default_factory=SimpleRagConfig)

    # cart_config: CartToolConfig = field(default_factory=CartToolConfig)

    calc_config: CalculatorConfig = field(default_factory=CalculatorConfig)


def async_to_sync(async_func: Callable) -> Callable:
    """
    Decorator that converts an async function to a sync function.
    
    Args:
        async_func: The async function to convert
        
    Returns:
        A synchronous wrapper function
    """
    @functools.wraps(async_func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Handle nested event loops (e.g., in Jupyter)
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(async_func(*args, **kwargs))
            else:
                return loop.run_until_complete(async_func(*args, **kwargs))
        except RuntimeError:
            # No event loop exists, create a new one
            return asyncio.run(async_func(*args, **kwargs))
    
    return sync_wrapper


class ToolManager:
    def __init__(self, config:ToolManagerConfig):
        self.config = config

        self.tool_fncs = []    # list of functions that should be turned into tools
        self.client_tool_manager = []  # 用于获取 MCP 工具
        self.populate_modules()
    
    def _get_tool_config(self)->List[ToolConfig]:
        tool_confs = []
        for e in dir(self.config):
            el = getattr(self.config, e)
            if ("config" in e) and is_dataclass(el):
                tool_confs.append(el)
        
        return tool_confs
    
    def _get_tool_fnc(self, tool_obj:LangToolBase)->List:
        fnc_list = []
        for fnc in tool_obj.get_tool_fnc():
            if isinstance(fnc, FunctionTool):
                fnc = fnc.fn
            fnc_list.append(fnc)
        
        return fnc_list


    def populate_modules(self):
        """instantiate all object with tools"""

        self.tool_fncs = []
        tool_configs = self._get_tool_config()
        for tool_conf in tool_configs:
            tool_name = tool_conf.get_name()[:-6]
            if tool_conf.use_tool:
                logger.info(f"making tool:{tool_name}")
                fnc_list = self._get_tool_fnc(tool_conf.setup())
                self.tool_fncs.extend(fnc_list)
            else:
                logger.info(f"skipping tool:{tool_name}")
        
        try:
            from lang_agent.client_tool_manager import ClientToolManagerConfig
            client_config = ClientToolManagerConfig()
            self.client_tool_manager = ClientToolManager(client_config)
            logger.info("Successfully initialized client_tool_manager for MCP tools")
        except Exception as e:
            logger.warning(f"Failed to initialize client_tool_manager: {e}")
            self.client_tool_manager = []
        self._build_langchain_tools()
    
    
    def get_tool_fncs(self):
        all_tools = []
        all_tools.extend(self.tool_fncs)
        if self.client_tool_manager is not None:
            try:
                mcp_tools = self.client_tool_manager.get_tools()
                all_tools.extend(mcp_tools)
            except Exception as e:
                logger.warning(f"Failed to get MCP tools: {e}")
        return all_tools
    
    def get_tool_dict(self):
        return self.tool_dict


    def fnc_to_structool(self, func):
        if inspect.iscoroutinefunction(func):
            return StructuredTool.from_function(
                    func=async_to_sync(func),
                    coroutine=func)   
        else:
            return StructuredTool.from_function(func=func)
            
    def _build_langchain_tools(self):
        self.langchain_tools = []
        for func in self.get_tool_fncs():
            if isinstance(func, StructuredTool):
                self.langchain_tools.append(func)
            else:
                self.langchain_tools.append(self.fnc_to_structool(func))

        return self.langchain_tools
    
    def get_list_langchain_tools(self)->List[StructuredTool]:
        all_langchain_tools = []
        all_langchain_tools.extend(self.langchain_tools)
        # 如果有 client_tool_manager，添加 MCP 工具（已经是 LangChain 格式）
        if self.client_tool_manager:
            try:
                # 获取 MCP 工具（已经是 StructuredTool 格式）
                mcp_tools = self.client_tool_manager.get_tools()
                all_langchain_tools.extend(mcp_tools)
            except Exception as e:
                logger.warning(f"Failed to get MCP tools: {e}")

        return all_langchain_tools


if __name__ == "__main__":
    man: ToolManager = ToolManagerConfig().setup()
    for lang_tool in man.get_list_langchain_tools():
        print(lang_tool.name)