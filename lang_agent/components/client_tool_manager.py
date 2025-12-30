from dataclasses import dataclass, field
from typing import Type, Any, Optional
import tyro
import commentjson
import asyncio
import os.path as osp
from loguru import logger

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field, create_model

from lang_agent.config import InstantiateConfig


class DeviceIdInjectedTool(StructuredTool):
    """
    A StructuredTool subclass that injects device_id from RunnableConfig
    at the invoke/ainvoke level, before any argument parsing.
    """
    
    def invoke(
        self,
        input: dict,
        config: Optional[RunnableConfig] = None,
        **kwargs,
    ):  
        # Inject device_id from config into the input dict
        if config and "configurable" in config:
            device_id = config["configurable"].get("device_id")
            logger.info(f"DeviceIdInjectedTool.invoke - device_id from config: {device_id}")
            
            # Add device_id to input if it's valid (not None and not "0")
            if isinstance(input, dict) and device_id is not None and device_id != "0":
                input = {**input, "device_id": device_id}
        
        return super().invoke(input, config, **kwargs)
    
    async def ainvoke(
        self,
        input: dict,
        config: Optional[RunnableConfig] = None,
        **kwargs,
    ):
        logger.info(f"========== DeviceIdInjectedTool.ainvoke CALLED ==========")
        # Inject device_id from config into the input dict
        if config and "configurable" in config:
            device_id = config["configurable"].get("device_id")
            logger.info(f"DeviceIdInjectedTool.ainvoke - device_id from config: {device_id}")
            
            # Add device_id to input if it's valid (not None and not "0")
            if isinstance(input, dict) and device_id is not None and device_id != "0":
                input = {**input, "device_id": device_id}
        
        return await super().ainvoke(input, config, **kwargs)

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ClientToolManagerConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: ClientToolManager)

    mcp_config_f: str = osp.join(osp.dirname(osp.dirname(osp.dirname(__file__))), "configs", "mcp_config.json")
    """path to all mcp configurations; expect json file"""

    def __post_init__(self):
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
                return self._wrap_tools_with_injected_device_id(tools)
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            tools = asyncio.run(self.aget_tools())
            return self._wrap_tools_with_injected_device_id(tools)
    
    def _wrap_tools_with_injected_device_id(self, tools: list) -> list:
        """
        Wrap tools that have 'device_id' parameter to inject it from RunnableConfig.
        This removes the burden from the LLM to pass device_id explicitly.
        """
        wrapped_tools = []
        for tool in tools:
            wrapped_tools.append(wrap_tool_with_injected_device_id(tool))
        return wrapped_tools


def wrap_tool_with_injected_device_id(tool: BaseTool) -> BaseTool:
    """
    Wrap a tool to inject 'device_id' from RunnableConfig instead of requiring LLM to pass it.
    If the tool doesn't have a device_id parameter, returns the tool unchanged.
    
    Uses DeviceIdInjectedTool which overrides invoke/ainvoke to inject device_id
    directly from config before argument parsing.
    """
    # Check if tool has device_id in its schema
    tool_schema = None
    if hasattr(tool, "args_schema") and tool.args_schema is not None:
        if isinstance(tool.args_schema, dict):
            tool_schema = tool.args_schema
        elif hasattr(tool.args_schema, "model_json_schema"):
            tool_schema = tool.args_schema.model_json_schema()
        elif hasattr(tool.args_schema, "schema"):
            tool_schema = tool.args_schema.schema()
    elif hasattr(tool, "args") and tool.args is not None:
        tool_schema = {"properties": tool.args}
    
    if tool_schema is None:
        return tool
    
    properties = tool_schema.get("properties", {})
    if "device_id" not in properties:
        return tool
    
    # Build a new args_schema WITHOUT device_id visible to LLM
    # device_id will be injected at invoke/ainvoke level from config
    new_fields = {}
    required_fields = tool_schema.get("required", [])
    
    for field_name, field_info in properties.items():
        if field_name == "device_id":
            # Skip device_id - it will be injected from config, not shown to LLM
            continue
        else:
            # Preserve other fields
            field_type = _get_python_type_from_schema(field_info)
            is_required = field_name in required_fields
            if is_required:
                new_fields[field_name] = (field_type, Field(description=field_info.get("description", "")))
            else:
                new_fields[field_name] = (
                    Optional[field_type], 
                    Field(default=field_info.get("default"), description=field_info.get("description", ""))
                )
    
    # Create the new Pydantic model (without device_id)
    NewArgsSchema = create_model(f"{tool.name}Args", **new_fields)
    
    # Get original functions
    original_func = tool.func if hasattr(tool, 'func') else None
    original_coroutine = tool.coroutine if hasattr(tool, 'coroutine') else None
    
    # Create the new wrapped tool using DeviceIdInjectedTool
    # which injects device_id at invoke/ainvoke level
    wrapped_tool = DeviceIdInjectedTool(
        name=tool.name,
        description=tool.description,
        args_schema=NewArgsSchema,
        func=original_func,
        coroutine=original_coroutine,
        return_direct=getattr(tool, "return_direct", False),
    )
    
    logger.info(f"Wrapped tool '{tool.name}' - type: {type(wrapped_tool).__name__}, has ainvoke: {hasattr(wrapped_tool, 'ainvoke')}")
    return wrapped_tool


def _get_python_type_from_schema(field_info: dict) -> type:
    """Convert JSON schema type to Python type."""
    json_type = field_info.get("type", "string")
    type_mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return type_mapping.get(json_type, Any)

if __name__ == "__main__":
    # NOTE: Simple test
    config = ClientToolManagerConfig()
    tool_manager = ClientToolManager(config)
    tools = tool_manager.get_tools()
    [print(e.name) for e in tools]