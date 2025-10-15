from dataclasses import dataclass, field, is_dataclass
from typing import Type, List
import tyro
import json
import asyncio
import os.path as osp
from loguru import logger
from fastmcp.tools.tool import FunctionTool

from lang_agent.config import InstantiateConfig, ToolConfig
from lang_agent.base import LangToolBase

## import tool configs
from lang_agent.rag.simple import SimpleRagConfig
from lang_agent.dummy.calculator import CalculatorConfig
from catering_end.lang_tool import CartToolConfig, CartTool

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ToolManagerConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: ToolManager)

    # tool configs here; 
    rag_config: SimpleRagConfig = field(default_factory=SimpleRagConfig)

    cart_config: CartToolConfig = field(default_factory=CartToolConfig)

    calc_config: CalculatorConfig = field(default_factory=CalculatorConfig)


class ToolManager:
    def __init__(self, config:ToolManagerConfig):
        self.config = config

        self.tool_fncs = []    # list of functions that should be turned into tools
        self.populate_modules()
    
    def _get_tool_config(self)->List[ToolConfig]:
        tool_confs = []
        for e in dir(self.config):
            el = getattr(self.config, e)
            if ("calc_config" in e) and is_dataclass(el):
                tool_confs.append(el)
        
        return tool_confs
    
    def _get_tool_fnc(self, tool_obj:LangToolBase)->List:
        fnc_list = []
        for fnc in tool_obj:
            if isinstance(fnc, FunctionTool):
                fnc = fnc.fn
            fnc_list.append(fnc)
        
        return fnc_list


    def populate_modules(self):
        """instantiate all object with tools"""

        self.tool_fncs = []
        tool_configs = self._get_tool_config()
        for tool_conf in tool_configs:
            if tool_conf.use_tool:
                logger.info(f"using tool:{tool_conf._target}")
                self.tool_fncs.extend(self._get_tool_fnc(tool_conf.setup()))
            else:
                logger.info(f"skipping tool:{tool_conf._target}")
    
    
    def get_tool_fncs(self):
        return self.tool_fncs
