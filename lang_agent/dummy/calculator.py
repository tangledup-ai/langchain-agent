import math
import random
from dataclasses import dataclass, field
from typing import Type, List
import tyro
import time

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
        # time.sleep(2)
        result = eval(python_expression, {"math": math, "random": random})
        return {"success": True, "result": result}
    
    def get_tool_fnc(self):
        return [self.calculator]


# Global calculator instance
calculator = Calculator(CalculatorConfig())

# FastMCP server setup
from fastmcp import FastMCP

mcp = FastMCP("Calculator Server")


@mcp.tool()
def calculate(python_expression: str) -> dict:
    """For mathematical calculation, always use this tool to calculate the result of a python expression. You can use 'math' or 'random' directly, without 'import'."""
    return calculator.calculator(python_expression)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=9000)
