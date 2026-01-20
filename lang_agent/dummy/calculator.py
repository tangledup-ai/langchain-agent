import math
import random
import asyncio
from dataclasses import dataclass, field
from typing import Type, List
import tyro
import time

from lang_agent.config import ToolConfig
from lang_agent.base import LangToolBase

# Concurrency control: limit max concurrent calculations
MAX_CONCURRENT_CALCULATIONS = 10
_semaphore: asyncio.Semaphore | None = None


def get_semaphore() -> asyncio.Semaphore:
    """Lazy initialization of semaphore (must be created within an event loop)."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALCULATIONS)
    return _semaphore


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class CalculatorConfig(ToolConfig):
    _target: Type = field(default_factory=lambda: Calculator)


class Calculator(LangToolBase):
    def __init__(self, config: CalculatorConfig):
        self.config = config

    def calculator(self, python_expression: str) -> dict:
        """For mathamatical calculation, always use this tool to calculate the result of a python expression. You can use 'math' or 'random' directly, without 'import'."""
        result = eval(python_expression, {"math": math, "random": random})
        return {"success": True, "result": result}

    async def calculator_async(self, python_expression: str) -> dict:
        """Async version: runs eval in a thread pool to avoid blocking the event loop."""
        async with get_semaphore():
            await asyncio.sleep(5)  # Simulate delay for testing
            result = await asyncio.to_thread(
                eval, python_expression, {"math": math, "random": random}
            )
            return {"success": True, "result": result}

    def get_tool_fnc(self):
        return [self.calculator]


if __name__ == "__main__":
    # Global calculator instance
    calculator = Calculator(CalculatorConfig())

    # FastMCP server setup
    from fastmcp import FastMCP

    mcp = FastMCP("Calculator Server")


    @mcp.tool()
    async def calculate(python_expression: str) -> dict:
        """For mathematical calculation, always use this tool to calculate the result of a python expression. You can use 'math' or 'random' directly, without 'import'."""
        return await calculator.calculator_async(python_expression)
    mcp.run(transport="streamable-http", host="0.0.0.0", port=9000)
