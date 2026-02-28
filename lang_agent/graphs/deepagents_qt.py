from dataclasses import dataclass, field
from typing import Type, Literal
import tyro
import os.path as osp

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage

from deepagents import create_deep_agent

from lang_agent.utils import make_llm
from lang_agent.components.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.components.prompt_store import build_prompt_store
from lang_agent.graphs.graph_states import State
from lang_agent.config import LLMNodeConfig
from lang_agent.base import GraphBase

from lang_agent.fs_bkends import StateBk, StateBkConfig, LocalShell, LocalShellConfig, DaytonaSandboxBk, DaytonaSandboxConfig

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class DeepAgentConfig(LLMNodeConfig):
    _target: Type = field(default_factory=lambda : DeepAgent)

    sys_prompt_f: str = osp.join(osp.dirname(osp.dirname(osp.dirname(__file__))), "configs", "prompts", "deepagent.txt")
    """path to system prompt"""

    tool_manager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)

    # file_backend_config: StateBkConfig = field(default_factory=StateBkConfig)
    # file_backend_config: LocalShellConfig = field(default_factory=LocalShellConfig)
    file_backend_config: DaytonaSandboxConfig = field(default_factory=DaytonaSandboxConfig)

    def __post_init__(self):
        super().__post_init__()
        assert osp.exists(self.sys_prompt_f), "prompt path does not exist"

class DeepAgent(GraphBase):
    def __init__(self, config:DeepAgentConfig):
        self.config = config
        self._build_modules()
        self.workflow = self._build_graph()

    def _build_modules(self):
        llm = make_llm(self.config.llm_name,
                       self.config.llm_provider,
                       api_key=self.config.api_key,
                       tags=["main_llm"])
        
        self.tool_man: ToolManager = self.config.tool_manager_config.setup()
        self.file_backend: StateBk = self.config.file_backend_config.setup()
        bkend_agent_params = self.file_backend.get_deepagent_params()

        self.mem = MemorySaver()
        self.deep_agent = create_deep_agent(model=llm,
                                            tools=self.tool_man.get_langchain_tools(),
                                            backend=self.file_backend.get_backend(),
                                            checkpointer=self.mem,
                                            **bkend_agent_params)
        
        self.prompt_store = build_prompt_store(file_path=self.config.sys_prompt_f, default_key="sys_prompt")
        self.sys_prompt = self.prompt_store.get("sys_prompt")

    def _agent_call(self, state:State):
        msg_dict = {"messages":[
            SystemMessage(
                self.sys_prompt
            ),
            *self._get_inp_msgs(state)
        ]}
        msg_dict.update(self.file_backend.get_inf_inp())
        inp = msg_dict, state["inp"][1]
        
        out = self.deep_agent.invoke(*inp)
        return {"messages": out["messages"]}

    def _build_graph(self):
        builder = StateGraph(State)
        builder.add_node("agent_call", self._agent_call)
        builder.add_edge(START, "agent_call")
        builder.add_edge("agent_call", END)
        return builder.compile()


if __name__ == "__main__":
    config = DeepAgentConfig()
    deepagent = DeepAgent(config)
    deepagent.workflow.invoke({"inp": ({"messages":[SystemMessage("you are a helpful bot enhanced with skills")]}, {"configurable": {"thread_id": '3'}})})