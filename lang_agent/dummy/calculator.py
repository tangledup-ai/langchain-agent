import math
import random
from dataclasses import dataclass, field
from typing import Type, List
import tyro

from lang_agent.config import ToolConfig
from lang_agent.base import LangToolBase

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class CalculatorConfig(ToolConfig):
    _target:Type = field(default_factory=lambda: Calculator)


class Calculator(LangToolBase):
    def __init__(self, config: CalculatorConfig):
        self.config = config

    def calculator(self, python_expression: str) -> dict:
        """For mathamatical calculation, always use this tool to calculate the result of a python expression. You can use 'math' or 'random' directly, without 'import'."""
        result = eval(python_expression, {"math": math, "random": random})
        return {"success": True, "result": result}
    
    def get_tool_fnc(self):
        return [self.calculator]

