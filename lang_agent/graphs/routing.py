from dataclasses import dataclass, field, is_dataclass
from typing import Type, TypedDict, Literal, Dict, List, Tuple, Any, AsyncIterator, Optional
import tyro
from pydantic import BaseModel, Field
from loguru import logger
import os.path as osp
import commentjson
import glob
import time

from lang_agent.config import LLMKeyConfig
from lang_agent.components.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.components.prompt_store import build_prompt_store
from lang_agent.base import GraphBase, ToolNodeBase
from lang_agent.graphs.graph_states import State
from lang_agent.graphs.tool_nodes import AnnotatedToolNode, ToolNodeConfig
from lang_agent.components.text_releaser import TextReleaser, AsyncTextReleaser

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langchain_core.messages.base import BaseMessageChunk
from langchain.agents import create_agent

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class RoutingConfig(LLMKeyConfig):
    _target: Type = field(default_factory=lambda: RoutingGraph)

    llm_name: str = "qwen-plus"
    """name of llm"""

    llm_provider:str = "openai"
    """provider of the llm"""

    base_url:str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """base url; could be used to overwrite the baseurl in llm provider"""

    sys_promp_dir: str = osp.join(osp.dirname(osp.dirname(osp.dirname(__file__))), "configs", "route_sys_prompts")
    """path to directory or json contantaining system prompt for graphs; Will overwrite systemprompt from xiaozhi if 'chat_prompt' is provided"""

    pipeline_id: Optional[str] = None
    """If set, load prompts from database (with file fallback)"""

    prompt_set_id: Optional[str] = None
    """If set, load from this specific prompt set instead of the active one"""

    tool_manager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)

    tool_node_config: AnnotatedToolNode = field(default_factory=ToolNodeConfig)



class Route(BaseModel):
    step: Literal["chat", "tool"] = Field(
        None, description="The next step in the routing process"
    )


class RoutingGraph(GraphBase):
    def __init__(self, config: RoutingConfig):
        self.config = config
        
        self._build_modules()

        self.workflow = self._build_graph()

        self.streamable_tags:List[List[str]] = self.tool_node.get_streamable_tags() + [["route_chat_llm"]]
        self.textreleaser_delay_keys = self.tool_node.get_delay_keys()
    
    def _build_modules(self):
        self.chat_llm = init_chat_model(model=self.config.llm_name,
                                     model_provider=self.config.llm_provider,
                                     api_key=self.config.api_key,
                                     base_url=self.config.base_url,
                                     temperature=0,
                                     tags=["route_chat_llm"])
        self.fast_llm = init_chat_model(model='qwen-flash',
                                        model_provider='openai',
                                        api_key=self.config.api_key,
                                        base_url=self.config.base_url,
                                        temperature=0,
                                        tags=["route_fast"])

        self.memory = MemorySaver()  # shared memory between the two branch
        self.router = self.fast_llm.with_structured_output(Route)

        tool_manager:ToolManager = self.config.tool_manager_config.setup()
        self.chat_model = create_agent(self.chat_llm, [], checkpointer=self.memory)

        self.tool_node:ToolNodeBase = self.config.tool_node_config.setup(tool_manager=tool_manager,
                                                                         memory=self.memory)

        self._load_sys_prompts()
    
    def _load_sys_prompts(self):
        self.prompt_store = build_prompt_store(
            pipeline_id=self.config.pipeline_id,
            prompt_set_id=self.config.prompt_set_id,
            file_path=self.config.sys_promp_dir,
        )
        self.prompt_dict: Dict[str, str] = self.prompt_store.get_all()

        for k in self.prompt_dict:
            logger.info(f"loaded '{k}' system prompt")



    def _router_call(self, state:State):
        decision:Route = self.router.invoke(
            [
                SystemMessage(
                    content=self.prompt_dict["route_prompt"]
                ),
                self._get_human_msg(state)
            ]
        )

        return {"decision": decision.step}


    def _get_human_msg(self, state: State)->HumanMessage:
        """
        get user message of current invocation
        """
        msgs = state["inp"][0]["messages"]

        candidate_hum_msg = None
        for msg in msgs:
            if isinstance(msg, HumanMessage):
                candidate_hum_msg = msg
                break
                
        assert isinstance(candidate_hum_msg, HumanMessage), "not a human message"

        return candidate_hum_msg
    

    def _route_decision(self, state:State):
        logger.info(f"decision:{state['decision']}")
        if state["decision"] == "chat":
            return "chat"
        else:
            return "tool"


    def _chat_model_call(self, state:State):
        if state.get("messages") is not None:
            inp = state["messages"], state["inp"][1]
        else:
            inp = state["inp"]
        
        if self.prompt_dict.get("chat_prompt") is not None:
            inp = {"messages":[
                        SystemMessage(
                            self.prompt_dict["chat_prompt"]
                        ),
                        *self._get_inp_msgs(state)
                    ]}, state["inp"][1]


        out = self.chat_model.invoke(*inp)
        return {"messages": out["messages"]}


    def _tool_model_call(self, state:State):
        out = self.tool_node.invoke(state)
        return {"messages": out["messages"]}
    
    def _build_graph(self):
        builder = StateGraph(State)

        # add nodes
        builder.add_node("chat_model_call", self._chat_model_call)
        builder.add_node("tool_model_call", self._tool_model_call)
        builder.add_node("router_call", self._router_call)

        # add edge connections
        builder.add_edge(START, "router_call")
        builder.add_conditional_edges(
            "router_call",
            self._route_decision,
            {
                "chat": "chat_model_call",
                "tool": "tool_model_call"
            }
        )
        builder.add_edge("tool_model_call", END)
        # builder.add_edge("tool_model_call", "chat_model_call")
        builder.add_edge("chat_model_call", END)

        workflow = builder.compile()

        return workflow

if __name__ == "__main__":
    from dotenv import load_dotenv
    from langchain.messages import SystemMessage, HumanMessage
    from langchain_core.messages.base import BaseMessageChunk
    from lang_agent.graphs.tool_nodes import AnnotatedToolNode, ToolNodeConfig, ChattyToolNodeConfig
    load_dotenv()

    route:RoutingGraph = RoutingConfig().setup()
    # route:RoutingGraph = RoutingConfig(tool_node_config=ChattyToolNodeConfig()).setup()
    graph = route.workflow

    nargs = {
        "messages": [SystemMessage("you are a helpful bot named jarvis"),
                     HumanMessage("use calculator to calculate 926*84")]
    },{"configurable": {"thread_id": "3"}}

    # for chunk in route.invoke(*nargs, as_stream=True):
    #     # print(f"\033[92m{chunk}\033[0m", end="", flush=True)
    #     continue

    
    for _, mode, out in graph.stream({"inp": nargs}, 
                                  subgraphs=True,
                                  stream_mode=["messages", "values"]):
        # print(mode)
        if mode == "values":
            msgs = out.get("messages")
            l = len(msgs) if msgs is not None else -1
            print(type(out), out.keys(), l)
        else:
            print(type(out), mode, "==================================================")
            print(out[0].content)
