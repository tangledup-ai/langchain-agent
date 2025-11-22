from dataclasses import dataclass, field, is_dataclass
from typing import Type, TypedDict, Literal, Dict, List, Tuple
import tyro
import os.path as osp


from lang_agent.config import InstantiateConfig, KeyConfig
from lang_agent.tool_manager import ToolManager
from lang_agent.base import ToolNodeBase
from lang_agent.graphs.graph_states import State, ChattyToolState
from lang_agent.utils import make_llm

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
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
                       memory:MemorySaver):
        self.config = config
        self.tool_manager = tool_manager
        self.mem = memory

        self.populate_modules()

    def populate_modules(self):
        self.llm = make_llm(tags=["tool_llm"])

        self.tool_agent = create_agent(self.llm, self.tool_manager.get_list_langchain_tools(), checkpointer=self.mem)
        with open(self.config.tool_prompt_f, "r") as f:
            self.sys_prompt = f.read()

    def invoke(self, state:State):
        inp = {"messages":[
            SystemMessage(
                self.sys_prompt
            ),
            *state["inp"][0]["messages"][1:]
        ]}, state["inp"][1]

        out = self.tool_agent.invoke(*inp)
        return {"messages": out}
    
    def get_streamable_tags(self):
        return super().get_streamable_tags()

    
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


class ChattyToolNode(ToolNodeBase):
    def __init__(self, config:ChattyToolNodeConfig, 
                       tool_manager:ToolManager,
                       memory:MemorySaver):
        self.config = config
        self.tool_manager = tool_manager
        self.mem = memory
        self.tool_done = False

        self.populate_modules()
        self.build_graph()
    
    
    def populate_modules(self):
        self.chatty_llm = init_chat_model(model=self.config.llm_name,
                                          model_provider=self.config.llm_provider,
                                          api_key=self.config.api_key,
                                          base_url=self.config.base_url,
                                          temperature=0,
                                          tags=["chatty_llm"])
        self.tool_llm = init_chat_model(model=self.config.llm_name,
                                        model_provider=self.config.llm_provider,
                                        api_key=self.config.api_key,
                                        base_url=self.config.base_url,
                                        temperature=0,
                                        tags=["tool_llm"])
        self.reit_llm = make_llm(model="qwen-flash", tags=["reit_llm"])
        
        self.chatty_agent = create_agent(self.chatty_llm, [], checkpointer=self.mem)
        self.tool_agent = create_agent(self.tool_llm, self.tool_manager.get_list_langchain_tools(), checkpointer=self.mem)

        with open(self.config.chatty_sys_prompt_f, "r") as f:
            self.chatty_sys_prompt = f.read()
        
        with open(self.config.tool_prompt_f, "r") as f:
            self.tool_sys_prompt = f.read()
    
    def get_streamable_tags(self):
        return [["chatty_llm"], ["reit_llm"]]

    def invoke(self, state:State):
        self.tool_done = False

        inp = {"inp": state["inp"]}
        out = self.workflow.invoke(inp)
        chat_msgs = out.get("chatty_messages")["messages"]
        tool_msgs = out.get("tool_messages")["messages"]

        state_msgs = [] if state.get("messages") is None else state.get("messages")
        return {"messages": state_msgs + chat_msgs + tool_msgs}
    
    def _tool_node_call(self, state:ChattyToolState):
        inp = {"messages":[
            SystemMessage(
                self.tool_sys_prompt
            ),
            *state["inp"][0]["messages"][1:]
        ]}, state["inp"][1]

        out = self.tool_agent.invoke(*inp)

        self.tool_done = True
        return {"tool_messages": out}

    
    def _chat_node_call(self, state:ChattyToolState):
        outs = []

        while not self.tool_done:
            inp = {"messages":[
                        SystemMessage(
                            self.chatty_sys_prompt
                        ),
                        *state["inp"][0]["messages"][1:]
                    ]}, state["inp"][1]
            outs.extend(self.chatty_agent.invoke(*inp)["messages"])
        
        return {"chatty_messages": {"messages":outs}}


    def _handoff_node(self, state:ChattyToolState):
        # NOTE: This exists just to stream the thing correctly
        tool_msgs = state.get("tool_messages")["messages"]
        inp = [
                SystemMessage(
                    "do nothing and repeat the last message"
                ),
                tool_msgs[-1].content
              ]
        self.reit_llm.invoke(inp)
        return {}


    def build_graph(self):
        builder = StateGraph(ChattyToolState)
        builder.add_node("chatty_tool_call", self._tool_node_call)
        builder.add_node("chatty_chat_call", self._chat_node_call)
        builder.add_node("chatty_handoff_node", self._handoff_node)

        builder.add_edge(START, "chatty_tool_call")
        builder.add_edge(START, "chatty_chat_call")
        builder.add_edge("chatty_chat_call", "chatty_handoff_node")
        builder.add_edge("chatty_tool_call", "chatty_handoff_node")
        builder.add_edge("chatty_handoff_node", END)

        self.workflow = builder.compile()



tool_node_dict = {
    "tool_node" : ToolNodeConfig(),
    "chatty_tool_node" : ChattyToolNodeConfig()
}

tool_node_union = tyro.extras.subcommand_type_from_defaults(tool_node_dict, prefix_names=False)
AnnotatedToolNode = tyro.conf.OmitSubcommandPrefixes[tyro.conf.SuppressFixed[tool_node_union]]

if __name__ == "__main__":
    from langchain_core.messages.base import BaseMessageChunk
    from langchain_core.messages import BaseMessage
    
    from lang_agent.tool_manager import ToolManagerConfig
    
    from dotenv import load_dotenv
    load_dotenv()

    mem = MemorySaver()
    tool_manager = ToolManagerConfig().setup()
    chatty_node:ChattyToolNode = ChattyToolNodeConfig().setup(tool_manager=tool_manager,
                                               memory=mem)
    
    query = "use calculator to calculate 33*42"
    input = {"inp" : ({"messages":[SystemMessage("you are a kind helper"), HumanMessage(query)]}, 
                      {"configurable": {"thread_id": '3'}})}
    inp = input
    graph = chatty_node.workflow

    for chunk, metadata in graph.stream(inp, stream_mode="messages"):
        tags = metadata.get("tags")
        if not (tags in [["chatty_llm"], ["reit_llm"]]):
            continue

        if isinstance(chunk, (BaseMessageChunk, BaseMessage)) and getattr(chunk, "content", None):
            print(chunk.content, end="", flush=True)
