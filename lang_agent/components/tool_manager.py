from dataclasses import dataclass, field, is_dataclass
import functools
from typing import Type, List, Callable, Any
import tyro
import inspect
import asyncio
import os.path as osp
from loguru import logger
from fastmcp.tools.tool import Tool
from lang_agent.config import InstantiateConfig, ToolConfig
from lang_agent.base import LangToolBase
from lang_agent.components.client_tool_manager import ClientToolManagerConfig

from lang_agent.rag.simple import SimpleRagConfig
from lang_agent.dummy.calculator import CalculatorConfig
from langchain_core.tools.structured import StructuredTool
from lang_agent.components.client_tool_manager import ClientToolManager
# from asgiref.sync import async_to_sync     # NOTE： THIS SHT DOES NOT WORK

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ToolManagerConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: ToolManager)

    client_tool_manager: ClientToolManagerConfig = field(default_factory=ClientToolManagerConfig)

    # tool configs here; MUST HAVE 'config' in name and must be dataclass
    # rag_config: SimpleRagConfig = field(default_factory=SimpleRagConfig)

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

        logger.info("available tools:")
        for tool in self.get_list_langchain_tools():
            logger.info(tool.name)
    
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
            if isinstance(fnc, Tool):
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
            # client_config = self.config.client_tool_manager
            # self.client_tool_manager = ClientToolManager(client_config)
            # self.client_tool_manager = ClientToolManager(self.config.client_tool_manager)
            self.client_tool_manager:ClientToolManager = self.config.client_tool_manager.setup()
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
            # Wrap async_to_sync result to preserve signature
            sync_wrapper = async_to_sync(func)
            @functools.wraps(func)
            def sync_func(*args, **kwargs):
                return sync_wrapper(*args, **kwargs)
            return StructuredTool.from_function(
                    func=sync_func,
                    coroutine=func)   
        else:
            return StructuredTool.from_function(func=func)
            
    def _build_langchain_tools(self):
        self.langchain_tools = []
        for func in self.get_tool_fncs():
            if isinstance(func, StructuredTool):
                if hasattr(func, 'coroutine') and func.coroutine is not None and (not hasattr(func, 'func') or func.func is None):
                    # Wrap async_to_sync result to preserve signature
                    sync_wrapper = async_to_sync(func.coroutine)
                    @functools.wraps(func.coroutine)
                    def sync_func(*args, _wrapper=sync_wrapper, **kwargs):
                        return _wrapper(*args, **kwargs)
                    # Preserve the original tool's class (e.g., DeviceIdInjectedTool)
                    # by setting func directly instead of creating a new StructuredTool
                    func.func = sync_func
                    self.langchain_tools.append(func)
                else:
                    self.langchain_tools.append(func)
            else:
                self.langchain_tools.append(self.fnc_to_structool(func))
        return self.langchain_tools
    
    def get_list_langchain_tools(self)->List[StructuredTool]:
        return self.langchain_tools


if __name__ == "__main__":
    man: ToolManager = ToolManagerConfig().setup()
    for lang_tool in man.get_list_langchain_tools():
        print(lang_tool.name)