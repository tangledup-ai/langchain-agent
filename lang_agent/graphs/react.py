from dataclasses import dataclass, field, is_dataclass
from typing import Type, List, Callable, Any
import tyro
import jax

from lang_agent.config import KeyConfig
from lang_agent.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.base import GraphBase

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

# NOTE: maybe make this into a base_graph_config?
@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ReactGraphConfig(KeyConfig):
    _target: Type = field(default_factory=lambda: ReactGraph)

    llm_name: str = "qwen-turbo"
    """name of llm"""

    llm_provider:str = "openai"
    """provider of the llm"""

    base_url:str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """base url; could be used to overwrite the baseurl in llm provider"""

    tool_manager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)




class ReactGraph(GraphBase):
    def __init__(self, config: ReactGraphConfig):
        self.config = config

        self.populate_modules()

    def populate_modules(self):
        self.llm = init_chat_model(model=self.config.llm_name,
                                   model_provider=self.config.llm_provider,
                                   api_key=self.config.api_key,
                                   base_url=self.config.base_url)
        

        self.tool_manager:ToolManager = self.config.tool_manager_config.setup()
        memory = MemorySaver()
        tools = self.tool_manager.get_langchain_tools()
        self.agent = create_agent(self.llm, tools, checkpointer=memory)
    
    def invoke(self, *nargs, as_stream:bool=False, as_raw:bool=False, **kwargs):
        """
        as_stream (bool): for debug only, gets the agent to print its thoughts
        """

        if as_stream:
            for step in self.agent.stream(*nargs, stream_mode="values", **kwargs):
                step["messages"][-1].pretty_print()
            out = step
        else:
            out = self.agent.invoke(*nargs, **kwargs)

        msgs_list = jax.tree.leaves(out)

        if as_raw:
            return out
        else:
            return msgs_list[-1].content
