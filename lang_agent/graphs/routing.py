from dataclasses import dataclass, field, is_dataclass
from typing import Type, TypedDict, Literal, Dict, List, Tuple
import tyro
from pydantic import BaseModel, Field

from lang_agent.config import KeyConfig
from lang_agent.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.base import GraphBase

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.agents import create_agent

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class RoutingConfig(KeyConfig):
    _target: Type = field(default_factory=lambda: RoutingGraph)

    llm_name: str = "qwen-turbo"
    """name of llm"""

    llm_provider:str = "openai"
    """provider of the llm"""

    base_url:str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    """base url; could be used to overwrite the baseurl in llm provider"""

    tool_manager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)



class Route(BaseModel):
    step: Literal["chat", "order"] = Field(
        None, description="The next step in the routing process"
    )


class State(TypedDict):
    inp: Tuple[Dict[str, List[SystemMessage | HumanMessage]], 
               Dict[str, Dict[str, str|int]]]
    output: str
    decision:str



class RoutingGraph(GraphBase):
    def __init__(self, config: RoutingConfig):
        self.config = config
        self.chat_sys_msg = None
        self._build_modules()

        self.workflow = self._build_graph()
    

    def invoke(self, *nargs, as_stream:bool=False, **kwargs):
        assert len(kwargs) == 0, "due to inp assumptions"

        if as_stream:
            for step in self.workflow.stream({"inp": nargs}, stream_mode="values", **kwargs):
                step["messages"][-1].pretty_print()
            state = step
        else:
            state = self.workflow.invoke({"inp": nargs})
            
        return state["output"]
    
    def _build_modules(self):
        self.llm = init_chat_model(model=self.config.llm_name,
                                   model_provider=self.config.llm_provider,
                                   api_key=self.config.api_key,
                                   base_url=self.config.base_url)
        self.memory = MemorySaver()
        self.router = self.llm.with_structured_output(Route)

        tool_manager:ToolManager = self.config.tool_manager_config.setup()
        self.chat_model = create_agent(self.llm, [], self.memory)
        self.tool_model = create_agent(self.llm, tool_manager.get_langchain_tools(), self.memory)


    def _router_call(self, state:State):
        decision:Route = self.router.invoke(
            [
                SystemMessage(
                    content="Route to chat or order based on the need of the user"
                ),
                self._get_human_msg(state)
            ]
        )

        return {"decision": decision.step}


    def _get_human_msg(self, state: State)->HumanMessage:
        msgs = state["inp"][0]["messages"]
        assert len(msgs) == 2, "Expect 1 systemMessage, 1 HumanMessage"
        candidate_hum_msg = msgs[1]
        assert isinstance(candidate_hum_msg, HumanMessage), "not a human message"

        return candidate_hum_msg
    

    def _route_decision(self, state:State):
        if state.decision == "chat":
            return "_chat_model_call"
        else:
            return "_tool_model_call"


    def _chat_model_call(self, state:State):
        out = self.chat_model.invoke(*state["inp"])
        return {"output":out["messages"][-1].content}


    def _tool_model_call(self, state:State):
        inp = [
            SystemMessage(
                "You must use tool to complete the possible task"
            ),self._get_human_msg(state)
        ], state["inp"][1]

        out = self.tool_model.invoke(*inp)
        return {"output": out["messages"][-1].content}
    
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
        builder.add_edge("chat_model_call", END)
        builder.add_edge("tool_model_call", END)

        workflow = builder.compile()

        return workflow