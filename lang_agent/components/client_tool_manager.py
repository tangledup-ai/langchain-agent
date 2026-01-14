from dataclasses import dataclass, field, is_dataclass
from typing import Type, Any, Optional
import tyro
import commentjson
import asyncio
import json
import os.path as osp
from loguru import logger

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field, create_model

from lang_agent.config import InstantiateConfig


def _json_default_serializer(obj: Any) -> Any:
    """
    Best-effort fallback serializer for objects that json can't handle.
    
    This is mainly to support rich MCP return types such as ImageContent.
    Strategy (in order):
    - If the object has `model_dump()`, use that (Pydantic v2 style).
    - Else if it has `dict()`, use that (Pydantic v1 / dataclass-like).
    - Else if it's a dataclass, convert via `asdict`.
    - Else fall back to `str(obj)`.
    """
    # Pydantic v2 models
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return obj.model_dump()
        except Exception:
            pass

    # Pydantic v1 or similar
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            return obj.dict()
        except Exception:
            pass

    # Dataclasses
    if is_dataclass(obj):
        from dataclasses import asdict

        try:
            return asdict(obj)
        except Exception:
            pass

    # Fallback: string representation (works for exceptions, custom types, etc.)
    return str(obj)


def _format_tool_result(result: Any, tool_call_info: dict | None) -> str | ToolMessage:
    """
    Format the tool result to match the expected output format.
    MCP tools return a tuple (result, error), which needs to be converted
    to a JSON array string for consistency with StructuredTool.invoke() behavior.
    
    If tool_call_info is provided (from a ToolCall), returns a ToolMessage.
    Otherwise, returns the raw content string for direct invocations.
    The JSON serialization is made robust to non-serializable objects
    (e.g. ImageContent) via `_json_default_serializer`.
    """
    content = json.dumps(list(result), default=_json_default_serializer, ensure_ascii=False)
    if tool_call_info and tool_call_info.get("id"):
        return ToolMessage(content=content,
                           name=tool_call_info.get("name"),
                           tool_call_id=tool_call_info["id"])
    return content    


def _is_tool_call(input: Any) -> bool:
    """Check if input is a ToolCall dict (has 'id' and 'args' keys)."""
    return isinstance(input, dict) and "id" in input and "args" in input


def _extract_tool_args(input: Any) -> tuple[dict, dict | None]:
    """
    Extract tool arguments from input.
    
    Returns:
        (tool_args, tool_call_info) where tool_call_info contains id/name if it was a ToolCall
    """
    if _is_tool_call(input):
        # Input is a ToolCall: {"id": "...", "name": "...", "args": {...}}
        tool_call_info = {"id": input.get("id"), "name": input.get("name")}
        return input["args"].copy(), tool_call_info
    else:
        # Input is already the args dict
        return input if isinstance(input, dict) else {}, None


class DeviceIdInjectedTool(StructuredTool):
    """
    A StructuredTool subclass that injects device_id from RunnableConfig
    at the invoke/ainvoke level, before any argument parsing.
    
    NOTE: We bypass the parent's invoke/ainvoke to avoid Pydantic schema validation
    which would strip the device_id field (since it's not in the new args_schema).
    """
    
    def invoke(
        self,
        input: dict,
        config: Optional[RunnableConfig] = None,
        **kwargs,
    ):  
        # Extract actual args from ToolCall if needed
        tool_args, tool_call_info = _extract_tool_args(input)
        
        # Inject device_id from config into the tool args
        if config and "configurable" in config:
            device_id = config["configurable"].get("device_id")
            logger.info(f"DeviceIdInjectedTool.invoke - device_id from config: {device_id}")
            
            # Add device_id to args if it's valid (not None and not "0")
            if device_id is not None and device_id != "0":
                tool_args = {**tool_args, "device_id": device_id}
        
        logger.info(f"DeviceIdInjectedTool.invoke - calling with args: {list(tool_args.keys())}")
        
        # Call the underlying func directly to bypass schema validation
        # which would strip the device_id field not in args_schema
        if self.func is not None:
            result = self.func(**tool_args)
            return _format_tool_result(result, tool_call_info)
        elif self.coroutine is not None:
            # Run async function synchronously
            result = asyncio.run(self.coroutine(**tool_args))
            return _format_tool_result(result, tool_call_info)
        else:
            # Fallback to parent implementation
            return super().invoke(input, config, **kwargs)
    
    async def ainvoke(
        self,
        input: dict,
        config: Optional[RunnableConfig] = None,
        **kwargs,
    ):
        logger.info(f"========== DeviceIdInjectedTool.ainvoke CALLED ==========")
        
        # Extract actual args from ToolCall if needed
        tool_args, tool_call_info = _extract_tool_args(input)
        
        # Inject device_id from config into the tool args
        if config and "configurable" in config:
            device_id = config["configurable"].get("device_id")
            logger.info(f"DeviceIdInjectedTool.ainvoke - device_id from config: {device_id}")
            
            # Add device_id to args if it's valid (not None and not "0")
            if device_id is not None and device_id != "0":
                tool_args = {**tool_args, "device_id": device_id}
        
        logger.info(f"DeviceIdInjectedTool.ainvoke - calling with args: {list(tool_args.keys())}")
        
        # Call the underlying coroutine/func directly to bypass schema validation
        # which would strip the device_id field not in args_schema
        if self.coroutine is not None:
            result = await self.coroutine(**tool_args)
            return _format_tool_result(result, tool_call_info)
        elif self.func is not None:
            # Run sync function in thread pool to avoid blocking
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: self.func(**tool_args))
            return _format_tool_result(result, tool_call_info)
        else:
            # Fallback to parent implementation
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
    
    async def aget_tools(self):
        """
        Get tools from all configured MCP servers.
        Handles connection failures gracefully by logging warnings and continuing.
        """
        all_tools = []
        
        for server_name, server_config in self.mcp_configs.items():
            try:
                # Create a client for this single server
                single_server_config = {server_name: server_config}
                client = MultiServerMCPClient(single_server_config)
                tools = await client.get_tools()
                all_tools.extend(tools)
                logger.info(f"Successfully connected to MCP server '{server_name}', retrieved {len(tools)} tools")
            except Exception as e:
                logger.warning(f"Failed to connect to MCP server '{server_name}' at {server_config.get('url', 'unknown URL')}: {e}")
                continue
        
        return all_tools

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
    
    for tool in tools:
        print(f"Name: {tool.name}")
        print(f"Description: {tool.description}")
        if hasattr(tool, 'args_schema') and tool.args_schema:
            print(f"Args Schema: {tool.args_schema}")
        print("-" * 80)
    
    ## Use the self_camera_capture_and_send tool
    camera_tool = next((t for t in tools if t.name == "self_camera_take_photo"), None)
    if camera_tool:
        print("\n=== Using self_camera_capture_and_send tool ===")
        result = camera_tool.invoke({"question": ""})
        print(f"Result: {result}")
    
    # Use the self_screen_set_brightness tool
    # brightness_tool = next((t for t in tools if t.name == "self_screen_set_brightness"), None)
    # if brightness_tool:
    #     print("\n=== Using self_screen_set_brightness tool ===")
    #     # Check what arguments it expects
    #     if hasattr(brightness_tool, 'args_schema') and brightness_tool.args_schema:
    #         schema = brightness_tool.args_schema.model_json_schema() if hasattr(brightness_tool.args_schema, 'model_json_schema') else None
    #         if schema:
    #             print(f"Expected args: {schema.get('properties', {})}")
    #     # Try setting brightness to 50 (assuming 0-100 scale)
    #     result = brightness_tool.invoke({"brightness": 0})
    #     print(f"Result: {result}")