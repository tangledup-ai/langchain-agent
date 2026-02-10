from dataclasses import dataclass, field, is_dataclass
from typing import Type, TypedDict, Literal, Dict, List, Tuple, Optional
import tyro
import os.path as osp
import time
import asyncio
from loguru import logger

from lang_agent.config import InstantiateConfig, KeyConfig
from lang_agent.components.tool_manager import ToolManager
from lang_agent.components.prompt_store import build_prompt_store
from lang_agent.components.reit_llm import ReitLLM
from lang_agent.base import ToolNodeBase
from lang_agent.graphs.graph_states import State, ChattyToolState
from lang_agent.utils import make_llm, words_only, tree_leaves

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END


@dataclass
class ToolNodeConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: ToolNode)

    tool_prompt_f:str = osp.join(osp.dirname(osp.dirname(osp.dirname(__file__))), "configs", "route_sys_prompts", "tool_prompt.txt")

    pipeline_id: Optional[str] = None
    """If set, load prompts from database (with file fallback)"""

    prompt_set_id: Optional[str] = None
    """If set, load from this specific prompt set instead of the active one"""


class ToolNode(ToolNodeBase):
    def __init__(self, config: ToolNodeConfig, 
                       tool_manager:ToolManager,
                       memory:MemorySaver):
        self.config = config
        self.tool_manager = tool_manager
        self.mem = memory if memory is not None else MemorySaver()

        self.populate_modules()

    def populate_modules(self):
        self.llm = make_llm(tags=["tool_llm"])

        self.tool_agent = create_agent(self.llm, self.tool_manager.get_langchain_tools(), checkpointer=self.mem)
        self.prompt_store = build_prompt_store(
            pipeline_id=self.config.pipeline_id,
            prompt_set_id=self.config.prompt_set_id,
            file_path=self.config.tool_prompt_f,
            default_key="tool_prompt",
        )
        self.sys_prompt = self.prompt_store.get("tool_prompt")

    def invoke(self, state:State):
        inp = {"messages":[
            SystemMessage(
                self.sys_prompt
            ),
            *self._get_inp_msgs(state)
        ]}, state["inp"][1]

        out = self.tool_agent.invoke(*inp)
        return {"messages": out["messages"]}

    async def ainvoke(self, state:State):
        """Async version of invoke using LangGraph's native async support."""
        inp = {"messages":[
            SystemMessage(
                self.sys_prompt
            ),
            *self._get_inp_msgs(state)
        ]}, state["inp"][1]

        out = await self.tool_agent.ainvoke(*inp)
        return {"messages": out["messages"]}
    
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
    """path to chatty system prompt"""

    # pipeline_id and prompt_set_id are inherited from ToolNodeConfig

    tool_node_conf:ToolNodeConfig = field(default_factory=ToolNodeConfig)


class ChattyToolNode(ToolNodeBase):
    def __init__(self, config:ChattyToolNodeConfig, 
                       tool_manager:ToolManager,
                       memory:MemorySaver):
        self.config = config
        self.tool_manager = tool_manager
        self.mem = memory

        self.chat_key = "[CHATTY_OUT]"
        self.tool_key = "[TOOL_OUT]"

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
        
        self.reit_llm = ReitLLM(tags=["reit_llm"])
        
        self.chatty_agent = create_agent(self.chatty_llm, [], checkpointer=self.mem)
        # self.tool_agent = create_agent(self.tool_llm, self.tool_manager.get_list_langchain_tools(), checkpointer=self.mem)

        # Propagate pipeline_id and prompt_set_id to inner tool_node_conf
        if self.config.pipeline_id and hasattr(self.config.tool_node_conf, 'pipeline_id'):
            self.config.tool_node_conf.pipeline_id = self.config.pipeline_id
        if self.config.prompt_set_id and hasattr(self.config.tool_node_conf, 'prompt_set_id'):
            self.config.tool_node_conf.prompt_set_id = self.config.prompt_set_id

        self.tool_agent = self.config.tool_node_conf.setup(tool_manager=self.tool_manager, 
                                                           memory=self.mem)

        self.chatty_prompt_store = build_prompt_store(
            pipeline_id=self.config.pipeline_id,
            prompt_set_id=self.config.prompt_set_id,
            file_path=self.config.chatty_sys_prompt_f,
            default_key="chatty_prompt",
        )
        self.chatty_sys_prompt = self.chatty_prompt_store.get("chatty_prompt")

        self.tool_prompt_store = build_prompt_store(
            pipeline_id=self.config.pipeline_id,
            prompt_set_id=self.config.prompt_set_id,
            file_path=self.config.tool_prompt_f,
            default_key="tool_prompt",
        )
        self.tool_sys_prompt = self.tool_prompt_store.get("tool_prompt")
    
    def get_streamable_tags(self):
        return [["chatty_llm"], ["reit_llm"]]

    def invoke(self, state:State):
        inp = {"inp": state["inp"], "tool_done": False}
        out = self.workflow.invoke(inp)
        chat_msgs = out.get("chatty_messages")["messages"]
        tool_msgs = out.get("tool_messages")["messages"]

        state_msgs = [] if state.get("messages") is None else state.get("messages")
        return {"messages": state_msgs + chat_msgs + tool_msgs}

    async def ainvoke(self, state:State):
        """Async version of invoke using LangGraph's native async support."""
        inp = {"inp": state["inp"], "tool_done": False}
        out = await self.workflow.ainvoke(inp)
        chat_msgs = out.get("chatty_messages")["messages"]
        tool_msgs = out.get("tool_messages")["messages"]

        state_msgs = [] if state.get("messages") is None else state.get("messages")
        return {"messages": state_msgs + chat_msgs + tool_msgs}
    
    def _tool_node_call(self, state:ChattyToolState):

        out = self.tool_agent.invoke(state)

        return {"tool_messages": out["messages"], "tool_done": True}

    
    def _chat_node_call(self, state:ChattyToolState):
        outs:List[BaseMessage] = []

        while not state.get("tool_done", False):
            inp = {"messages":[
                        SystemMessage(
                            f"回复的最开始应该是{self.chat_key}\n"+self.chatty_sys_prompt
                        ),
                        *self._get_inp_msgs(state)
                    ]}, state["inp"][1]
            outs.extend(self.chatty_agent.invoke(*inp)["messages"])

            # NOTE: words generate faster than speech
            content = words_only(outs[-1].content)
            # time.sleep(len(content) * 0.20) # 0.22 = sec/words

        
        return {"chatty_messages": {"messages":outs}}


    def _handoff_node(self, state:ChattyToolState):
        # NOTE: This exists just to stream the thing correctly
        tool_msgs = state.get("tool_messages")
        reit_msg = f"{self.tool_key}\n"+tool_msgs[-1].content
        inp = [
                SystemMessage(
                    "REPEAT THE LAST MESSAGE AND DO NOTHING ELSE!"
                ),
                HumanMessage(reit_msg)
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

    def get_delay_keys(self):
        return self.chat_key, self.tool_key

tool_node_dict = {
    "tool_node" : ToolNodeConfig(),
    "chatty_tool_node" : ChattyToolNodeConfig()
}

tool_node_union = tyro.extras.subcommand_type_from_defaults(tool_node_dict, prefix_names=False)
AnnotatedToolNode = tyro.conf.OmitSubcommandPrefixes[tyro.conf.SuppressFixed[tool_node_union]]


def debug_chatty_node():
    from langchain_core.messages.base import BaseMessageChunk
    from lang_agent.components.tool_manager import ToolManagerConfig
    
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


def check_mcp_conn():
    import httpx
    mcp_url = "https://therianclouds.mynatapp.cc/api/mcp/"
    try:
        response = httpx.get(mcp_url, timeout=5.0)
        logger.info(f"MCP server at {mcp_url} is accessible, status: {response.status_code}")
    except httpx.ConnectError as e:
        logger.warning(f"MCP server at {mcp_url} connection failed: {e}")
    except httpx.TimeoutException:
        logger.warning(f"MCP server at {mcp_url} connection timed out")
    except Exception as e:
        logger.warning(f"MCP server at {mcp_url} check failed: {e}")

def debug_tool_node():
    import httpx
    from langchain_core.messages.base import BaseMessageChunk
    from lang_agent.components.tool_manager import ToolManagerConfig
    
    from dotenv import load_dotenv
    load_dotenv()

    mem = MemorySaver()
    tool_manager = ToolManagerConfig().setup()
    tool_node:ToolNode = ToolNodeConfig().setup(tool_manager=tool_manager, 
                                                memory=mem)
    graph = tool_node.tool_agent
    
    print("Tool Node Debug Chat - Enter 'quit' or 'exit' to stop")
    print("-" * 50)
    
    try:
        while True:
            # Get user input for the query
            query = input("\nYou: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
            
            # Check MCP server connectivity
            check_mcp_conn()
            
            input_data = ({"messages":[SystemMessage("you are a kind helper"), HumanMessage(query)]}, 
                            {"configurable": {"thread_id": '3'}})
            
            print("Assistant: ", end="", flush=True)
            for chunk in graph.stream(*input_data, stream_mode="updates"):
                el = tree_leaves(chunk)[-1]
                el.pretty_print()
    except Exception as e:
        print(e)
        check_mcp_conn()


if __name__ == "__main__":
    # debug_chatty_node()
    debug_tool_node()