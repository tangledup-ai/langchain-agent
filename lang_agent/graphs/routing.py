from dataclasses import dataclass, field, is_dataclass
from typing import Type, TypedDict, Literal, Dict, List, Tuple
import tyro
from pydantic import BaseModel, Field
from loguru import logger
from PIL import Image
from io import BytesIO
import matplotlib.pyplot as plt

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
    messages: List[SystemMessage | HumanMessage]
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
            # TODO： this doesn't stream the entire process, we are blind
            for step in self.workflow.stream({"inp": nargs}, stream_mode="values", **kwargs):
                if "messages" in step:
                    step["messages"]["messages"][-1].pretty_print()
            state = step
        else:
            state = self.workflow.invoke({"inp": nargs})
            
        return state["messages"]
    
    def _build_modules(self):
        self.llm = init_chat_model(model=self.config.llm_name,
                                   model_provider=self.config.llm_provider,
                                   api_key=self.config.api_key,
                                   base_url=self.config.base_url)
        self.memory = MemorySaver()
        self.router = self.llm.with_structured_output(Route)

        tool_manager:ToolManager = self.config.tool_manager_config.setup()
        self.chat_model = create_agent(self.llm, [], checkpointer=self.memory)
        self.tool_model = create_agent(self.llm, tool_manager.get_langchain_tools(), checkpointer=self.memory)


    def _router_call(self, state:State):
        decision:Route = self.router.invoke(
            [
                SystemMessage(
                    content="Return a JSON object with 'step'.the value should be one of 'chat' or 'order' based on the user input"
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
        candidate_hum_msg = msgs[1]
        assert isinstance(candidate_hum_msg, HumanMessage), "not a human message"

        return candidate_hum_msg
    

    def _route_decision(self, state:State):
        logger.info(f"decision:{state["decision"]}")
        if state["decision"] == "chat":
            return "chat"
        else:
            return "tool"


    def _chat_model_call(self, state:State):
        if state.get("messages") is not None:
            inp = state["messages"], state["inp"][1]
        else:
            inp = state["inp"]

        out = self.chat_model.invoke(*inp)
        return {"messages": out}


    def _tool_model_call(self, state:State):
        inp = {"messages":[
            SystemMessage(
                "You must use tool to complete the possible task"
            ),
            # self._get_human_msg(state)
            *state["inp"][0][1:]
        ]}, state["inp"][1]

        out = self.tool_model.invoke(*inp)
        return {"messages": out}
    
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

    def show_graph(self):
        img = Image.open(BytesIO(self.workflow.get_graph().draw_mermaid_png()))
        plt.imshow(img)
        plt.show()