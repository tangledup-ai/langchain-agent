from dataclasses import dataclass, field, is_dataclass
from typing import Type, TypedDict, Literal, Dict, List, Tuple
import tyro
import os
import os.path as osp


from lang_agent.config import InstantiateConfig, KeyConfig
from lang_agent.tool_manager import ToolManager
from lang_agent.base import ToolNodeBase
from lang_agent.graphs.graph_states import State

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END


@dataclass
class ToolNodeConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: ToolNode)

    tool_prompt_f:str = osp.join(osp.dirname(osp.dirname(osp.dirname(__file__))), "configs", "route_sys_prompts", "tool_prompt.txt")


class ToolNode(ToolNodeBase):
    def __init__(self, config: ToolNodeConfig, 
                       tool_manager:ToolManager,
                       llm:BaseChatModel,
                       memory:MemorySaver):
        self.config = config
        self.tool_manager = tool_manager
        self.llm = llm
        self.mem = memory

        self.populate_modules()

    def populate_modules(self):
        self.tool_agent = create_agent(self.llm, self.tool_manager.get_list_langchain_tools(), checkpointer=self.mem)
        with open(self.config.tool_prompt_f, "r") as f:
            self.sys_prompt = f.read()

    def tool_node_call(self, state:State):
        inp = {"messages":[
            SystemMessage(
                self.sys_prompt
            ),
            *state["inp"][0]["messages"][1:]
        ]}, state["inp"][1]

        out = self.tool_agent.invoke(*inp)
        return {"messages": out}

    
@dataclass
class ChattyToolNodeConfig(KeyConfig, ToolNodeConfig):
    _target: Type = field(default_factory=lambda: ChattyToolNode)

    llm_name: str = "qwen-plus"
    """name of llm"""

    llm_provider:str = "openai"
    """provider of the llm"""

    base_url:str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """base url; could be used to overwrite the baseurl in llm provider"""

    chatty_sys_prompt_f:str = osp.join(osp.dirname(osp.dirname(osp.dirname(__file__))), "configs", "route_sys_prompts", "chatty_prompt.txt")


class ChattyToolNode:
    def __init__(self, config:ChattyToolNodeConfig, 
                       tool_manager:ToolManager,
                       llm:BaseChatModel,
                       memory:MemorySaver):
        self.config = config
        self.tool_manager = tool_manager
        self.tool_llm = llm
        self.mem = memory
        self.tool_done = False

        self.populate_modules()
        self.build_graph()
    
    
    def populate_modules(self):
        self.chatty_llm = init_chat_model(model=self.config.llm_name,
                                          model_provider=self.config.llm_provider,
                                          api_key=self.config.api_key,
                                          base_url=self.config.base_url,
                                          temperature=0)
        
        self.chatty_agent = create_agent(self.chatty_agent, [], checkpointer=self.mem)
        self.tool_agent = create_agent(self.tool_llm, self.tool_manager.get_list_langchain_tools(), checkpointer=self.mem)

        with open(self.config.chatty_sys_prompt_f, "r") as f:
            self.chatty_sys_prompt = f.read()
        
        with open(self.config.tool_prompt_f, "r") as f:
            self.tool_sys_prompt = f.read()

    
    def _tool_node_call(self, state:State):
        inp = {"messages":[
            SystemMessage(
                self.tool_sys_prompt
            ),
            *state["inp"][0]["messages"][1:]
        ]}, state["inp"][1]

        out = self.tool_agent.invoke(*inp)


        return {"subgraph_states":{"tool_message": out}}

    
    def _chat_node_call(self, state:State):
        outs = []

        while not self.tool_done:
            inp = {"messages":[
                        SystemMessage(
                            self.chatty_sys_prompt
                        ),
                        *state["inp"][0]["messages"][1:]
                    ]}, state["inp"][1]
            outs.append(self.chatty_agent.invoke(*inp))
        
        return {"subgraph_states":{"chatty_message": outs}}


    def _handoff_node(self, state:State):
        chat_msgs = state.get("subgraph_states").get("chatty_message")
        tool_msgs = state.get("subgraph_states").get("tool_message")

        return {"messages": state["messages"] + chat_msgs + tool_msgs}


    def build_graph(self):
        builder = StateGraph(State)
        builder.add_node("chatty_tool_call", self._tool_node_call)
        builder.add_node("chatty_chat_call", self._chat_node_call)
        builder.add_node("chatty_handoff_node", self._handoff_node)

        builder.add_edge(START, "chatty_tool_call")
        builder.add_edge(START, "chatty_chat_call")
        builder.add_edge("chatty_chat_call", "chatty_handoff_node")
        builder.add_edge("chatty_node_call", "chatty_handoff_node")
        builder.add_edge("chatty_handoff_node", END)

        self.workflow = builder.compile()



tool_node_dict = {
    "tool_node" : ToolNodeConfig(),
    "chatty_tool_node" : ChattyToolNodeConfig()
}

tool_node_union = tyro.extras.subcommand_type_from_defaults(tool_node_dict, prefix_names=False)
AnnotatedToolNode = tyro.conf.OmitSubcommandPrefixes[tyro.conf.SuppressFixed[tool_node_union]]

if __name__ == "__main__":
    tyro.cli(ToolNodeConfig)
        
