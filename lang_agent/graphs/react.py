from dataclasses import dataclass, field, is_dataclass
from typing import Type, List, Callable, Any, AsyncIterator
import tyro

from lang_agent.config import KeyConfig
from lang_agent.components.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.base import GraphBase
from lang_agent.utils import tree_leaves

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

# NOTE: maybe make this into a base_graph_config?
@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ReactGraphConfig(KeyConfig):
    _target: Type = field(default_factory=lambda: ReactGraph)

    llm_name: str = "qwen-plus"
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
                                   base_url=self.config.base_url,
                                   tags=["main_llm"])
        

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

        msgs_list = tree_leaves(out)

        for e in msgs_list:
            if isinstance(e, BaseMessage):
                e.pretty_print()

        if as_raw:
            return msgs_list
        else:
            return msgs_list[-1].content

    async def ainvoke(self, *nargs, as_stream:bool=False, as_raw:bool=False, **kwargs):
        """
        Async version of invoke using LangGraph's native async support.
        as_stream (bool): for debug only, gets the agent to print its thoughts
        """

        if as_stream:
            async for step in self.agent.astream(*nargs, stream_mode="values", **kwargs):
                step["messages"][-1].pretty_print()
            out = step
        else:
            out = await self.agent.ainvoke(*nargs, **kwargs)

        msgs_list = tree_leaves(out)

        for e in msgs_list:
            if isinstance(e, BaseMessage):
                e.pretty_print()

        if as_raw:
            return msgs_list
        else:
            return msgs_list[-1].content


if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
    from langchain_core.messages.base import BaseMessageChunk
    load_dotenv()

    route:ReactGraph = ReactGraphConfig().setup()
    graph = route.agent

    nargs = {
        "messages": [SystemMessage("you are a helpful bot named jarvis"),
                     HumanMessage("use the calculator tool to calculate 92*55 and say the answer")]
    },{"configurable": {"thread_id": "3"}}

    out = route.invoke(*nargs)
    assert 0
    
    # for chunk, metadata in graph.stream({"inp": nargs}, stream_mode="messages"):
    #     node = metadata.get("langgraph_node")
    #     if node not in ("model"):
    #         print(node)
    #         continue  # skip router or other intermediate nodes

    #     # Print only the final message content
    #     if isinstance(chunk, (BaseMessageChunk, BaseMessage)) and getattr(chunk, "content", None):
    #         print(chunk.content, end="", flush=True)
    