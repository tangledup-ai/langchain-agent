from dataclasses import dataclass, field
from typing import Type, Optional
import tyro
import os.path as osp
from loguru import logger

from lang_agent.config import LLMKeyConfig
from lang_agent.components.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.components.prompt_store import build_prompt_store
from lang_agent.base import GraphBase
from lang_agent.utils import tree_leaves
from lang_agent.graphs.graph_states import State

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

# NOTE: maybe make this into a base_graph_config?
@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ReactGraphConfig(LLMKeyConfig):
    _target: Type = field(default_factory=lambda: ReactGraph)

    sys_prompt_f:str = osp.join(osp.dirname(osp.dirname(osp.dirname(__file__))), "configs", "prompts", "blueberry.txt")
    """path to system prompt"""

    pipeline_id: Optional[str] = None
    """If set, load prompts from database (with file fallback)"""

    prompt_set_id: Optional[str] = None
    """If set, load from this specific prompt set instead of the active one"""

    tool_manager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)

    def __post_init__(self):
        super().__post_init__()
        err_msg = f"{self.sys_prompt_f} does not exist"
        assert osp.exists(self.sys_prompt_f), err_msg
        logger.info(f"will be loading react sys promtp from {self.sys_prompt_f}")


class ReactGraph(GraphBase):
    def __init__(self, config: ReactGraphConfig):
        self.config = config

        self.populate_modules()
        self.workflow = self._build_graph()

        self.streamable_tags = [["main_llm"]]

    def populate_modules(self):
        self.llm = init_chat_model(model=self.config.llm_name,
                                   model_provider=self.config.llm_provider,
                                   api_key=self.config.api_key,
                                   base_url=self.config.base_url,
                                   tags=["main_llm"])
        

        self.tool_manager:ToolManager = self.config.tool_manager_config.setup()
        self.memory = MemorySaver()
        tools = self.tool_manager.get_langchain_tools()
        self.agent = create_agent(self.llm, tools, checkpointer=self.memory)
        
        self.prompt_store = build_prompt_store(
            pipeline_id=self.config.pipeline_id,
            prompt_set_id=self.config.prompt_set_id,
            file_path=self.config.sys_prompt_f,
            default_key="sys_prompt",
        )
        self.sys_prompt = self.prompt_store.get("sys_prompt")
    
    def _agent_call(self, state:State):
        if state.get("messages") is not None:
            inp = state["messages"], state["inp"][1]
        else:
            inp = state["inp"]
        
        inp = {"messages":[
                    SystemMessage(
                        self.sys_prompt
                    ),
                    *self._get_inp_msgs(state)
                ]}, state["inp"][1]


        out = self.agent.invoke(*inp)
        return {"messages": out["messages"]}


    def _build_graph(self):
        builder = StateGraph(State)

        builder.add_node("agent_call", self._agent_call)
        
        builder.add_edge(START, "agent_call")
        builder.add_edge("agent_call", END)

        return builder.compile()


if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
    from langchain_core.messages.base import BaseMessageChunk
    load_dotenv()

    route:ReactGraph = ReactGraphConfig().setup()
    graph = route.agent

    nargs = {
        "messages": [SystemMessage("you are a helpful bot named jarvis"),
                     HumanMessage("say something cool")]
    },{"configurable": {"thread_id": "3"}}

    for out in route.invoke(*nargs, as_stream=True):
        print(out)

    # out = route.invoke(*nargs)
    # assert 0
    
    # for mode, data in graph.stream(*nargs, stream_mode=["messages", "values"]):
    #     print(data)

    # for _, mode, out in graph.stream(*nargs, subgraphs=True,
    #                               stream_mode=["messages", "values"]):
    #     if mode == "values":
    #         msgs = out.get("messages")
    #         l = len(msgs) if msgs is not None else -1
    #         print(type(out), out.keys(), l)