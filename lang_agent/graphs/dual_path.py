from dataclasses import dataclass, field
from typing import Type, TypedDict, Literal, Dict, List
import tyro
from pydantic import BaseModel, Field
from loguru import logger

from langchain.chat_models import init_chat_model

from lang_agent.config import LLMKeyConfig
from lang_agent.base import GraphBase
from lang_agent.components.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.graphs.graph_states import State

from langchain.agents import create_agent
from langchain.messages import SystemMessage, HumanMessage
from langchain.tools import tool

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END


SYS_PROMPT = "you are a helpful helper who will have a fun conversation with the user"

TOOL_SYS_PROMPT = "base on the user's speech, identify their emotions and change the light color to its appropriate colors. If it sounds neutral, do nothing"


@dataclass
class DualConfig(LLMKeyConfig):
    _target: Type = field(default_factory=lambda:Dual)

    tool_manager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)

from langchain.tools import tool

@tool
def turn_lights(col:Literal["red", "green", "yellow", "blue"]):
    """
    Turn on the color of the lights
    """
    print(f"TURNED ON LIGHT: {col}  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")


class Dual(GraphBase):
    def __init__(self, config:DualConfig):
        self.config = config

        self._build_modules()
        self.workflow = self._build_graph()
        self.streamable_tags = ["dual_chat_llm"]

    def _build_modules(self):
        self.chat_llm = init_chat_model(model=self.config.llm_name,
                                        model_provider=self.config.llm_provider,
                                        api_key=self.config.api_key,
                                        base_url=self.config.base_url,
                                        temperature=0,
                                        tags=["dual_chat_llm"])
        
        self.tool_llm = init_chat_model(model='qwen-flash',
                                        model_provider='openai',
                                        api_key=self.config.api_key,
                                        base_url=self.config.base_url,
                                        temperature=0,
                                        tags=["dual_tool_llm"])
        
        self.memory = MemorySaver()
        self.tool_manager: ToolManager = self.config.tool_manager_config.setup()
        self.chat_agent = create_agent(self.chat_llm, [], checkpointer=self.memory)
        # self.tool_agent = create_agent(self.tool_llm, self.tool_manager.get_langchain_tools())
        self.tool_agent = create_agent(self.tool_llm, [turn_lights])

        self.streamable_tags = [["dual_chat_llm"]]
    

    def _chat_call(self, state:State):
        return self._agent_call_template(SYS_PROMPT, self.chat_agent, state)
    
    def _tool_call(self, state:State):
        self._agent_call_template(TOOL_SYS_PROMPT, self.tool_agent, state)
        return {}

    def _join(self, state:State):
        return {}
    
    def _build_graph(self):
        builder = StateGraph(State)

        builder.add_node("chat_call", self._chat_call)
        builder.add_node("tool_call", self._tool_call)
        builder.add_node("join", self._join)


        builder.add_edge(START, "chat_call")
        builder.add_edge(START, "tool_call")
        builder.add_edge("chat_call", "join")
        builder.add_edge("tool_call", "join")
        builder.add_edge("join", END)

        return builder.compile()


if __name__ == "__main__":
    dual:Dual = DualConfig().setup()
    nargs = {"messages": [SystemMessage("you are a helpful bot named jarvis"),
                          HumanMessage("I feel very very sad")]
    }, {"configurable": {"thread_id": "3"}}

    out = dual.invoke(*nargs)
    print(out)