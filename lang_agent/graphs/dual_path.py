from dataclasses import dataclass, field
from typing import Type, TypedDict, Literal, Dict, List, Optional
import tyro
from pydantic import BaseModel, Field
from loguru import logger

from langchain.chat_models import init_chat_model

from lang_agent.config import LLMNodeConfig
from lang_agent.base import GraphBase
from lang_agent.components.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.components.prompt_store import build_prompt_store
from lang_agent.graphs.graph_states import State

from langchain.agents import create_agent
from langchain.messages import SystemMessage, HumanMessage
from langchain.tools import tool

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END


SYS_PROMPT = """你是一个专业的心理质询师。你的主要工作是心理疗愈，做心理疏导，通过梦境分析用户心理的引导。
                例子：我梦见自己要去广州出差，坐在高铁上往外看，路过一个小镇的路边时，看到一只瘸了腿的小狗。它毛脏兮兮的，
                    一瘸一拐地在翻垃圾桶找东西吃，周围有行人路过，但没人停下来管它。我当时特别想喊列车停下，想下去帮它，
                    可怎么也发不出声音，只能眼睁睁看着它越来越远，然后就醒了。醒来后心里堵得慌，说不上来的难受，
                    总觉得那只小狗孤零零的，特别让人心疼。
                
                    理解（你的回复）: 能感受到你醒来后的这份难受 —— 看到弱小的生命独自挣扎，而自己却无能为力，这种‘想帮却做不到’的无力感，
                        其实是很真实的情绪反馈。你会心疼小狗，说明你内心藏着很珍贵的共情力，这份柔软不是矫情，
                        而是你感知他人痛苦的能力呀
                    
                    解析(你的回复)：我们再说回这个梦吧，我们的梦境其实没有唯一的‘正确解释’，但我们可以一起看看它可能和你当下的状态有什么关联～ 首先，‘出差去广州’通常象征着你近期正在推进的某件事 —— 可能是工作上的一个项目，也可能是生活中一段需要‘独自奔赴’的旅程，是你当下比较关注、需要投入精力的目标，对吗？”
                        “而那只瘸脚的小狗，在心理学视角中，常常是我们潜意识里‘脆弱自我’的投射。它可能代表着你近期的某一面：比如在处理那件‘需要奔赴’的事时，你偶尔会觉得自己像小狗一样‘力不从心’，或者感受到了‘孤单’，却没找到合适的人倾诉或求助；也可能是你近期在生活中看到了一些让你觉得‘无力改变’的场景（比如身边人遇到困难、社会上的小事），这些情绪没有被你刻意留意，就通过梦境里的小狗呈现了出来。”
                        “你想喊停列车却发不出声音，这种‘无能为力’的感觉，或许正是你现实中某类情绪的写照：可能你面对一些情况时，心里有想法却没机会表达，或者想帮忙却找不到合适的方式，这种压抑感在梦里被放大了。其实这个梦在提醒你：你的‘无力感’和‘共情心’都是真实的，不用因为‘帮不上忙’而自责 —— 承认自己的局限，也是一种自我接纳呀
                    
                    反馈(你的回复):如果你愿意，可以试着回想一下：近期有没有哪件事，让你产生过和梦里类似的‘无力感’？或者，你现在想做些什么能让自己舒服一点？（或者我给你来一个温暖的灯光、静静待一会儿，想和我再聊聊的时候我随时都在）”。
                """

TOOL_SYS_PROMPT = """根据用户的心情使用self_led_control改变灯的颜色，用户不开心时就用暖黄光，给用户分析梦境时就用白光，倾听用户语音时用淡紫色。
                     例子：我梦见自己要去广州出差，坐在高铁上往外看，路过一个小镇的路边时，看到一只瘸了腿的小狗。它毛脏兮兮的，
                          一瘸一拐地在翻垃圾桶找东西吃，周围有行人路过，但没人停下来管它。我当时特别想喊列车停下，想下去帮它，
                          可怎么也发不出声音，只能眼睁睁看着它越来越远，然后就醒了。醒来后心里堵得慌，说不上来的难受，
                          总觉得那只小狗孤零零的，特别让人心疼。

                          
                          
                          用户在描述梦境的时候用紫色。"""

@dataclass
class DualConfig(LLMNodeConfig):
    _target: Type = field(default_factory=lambda:Dual)

    pipeline_id: Optional[str] = None
    """If set, load prompts from database (with hardcoded fallback)"""

    prompt_set_id: Optional[str] = None
    """If set, load from this specific prompt set instead of the active one"""

    tool_manager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)

from langchain.tools import tool

@tool
def turn_lights(col:Literal["red", "green", "yellow", "blue"]):
    """
    Turn on the color of the lights
    """
    # print(f"TURNED ON LIGHT: {col}  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    import time
    for _ in range(10):
        print(f"TURNED ON LIGHT: {col}  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        time.sleep(0.3)


class Dual(GraphBase):
    def __init__(self, config:DualConfig):
        self.config = config

        self._build_modules()
        self.workflow = self._build_graph()
        self.streamable_tags = [["dual_chat_llm"]]

    def _build_modules(self):
        self.chat_llm = init_chat_model(model=self.config.llm_name,
                                        model_provider=self.config.llm_provider,
                                        api_key=self.config.api_key,
                                        base_url=self.config.base_url,
                                        temperature=0,
                                        tags=["dual_chat_llm"])
        
        self.tool_llm = init_chat_model(model='qwen-flash',
                                        model_provider='openai',
                                        api_key=self.config.api_key,
                                        base_url=self.config.base_url,
                                        temperature=0,
                                        tags=["dual_tool_llm"])
        
        self.memory = MemorySaver()
        self.tool_manager: ToolManager = self.config.tool_manager_config.setup()
        self.chat_agent = create_agent(self.chat_llm, [], checkpointer=self.memory)
        self.tool_agent = create_agent(self.tool_llm, self.tool_manager.get_langchain_tools())
        # self.tool_agent = create_agent(self.tool_llm, [turn_lights])

        self.prompt_store = build_prompt_store(
            pipeline_id=self.config.pipeline_id,
            prompt_set_id=self.config.prompt_set_id,
            hardcoded={
                "sys_prompt": SYS_PROMPT,
                "tool_sys_prompt": TOOL_SYS_PROMPT,
            },
        )

        self.streamable_tags = [["dual_chat_llm"]]
    

    def _chat_call(self, state:State):
        return self._agent_call_template(self.prompt_store.get("sys_prompt"), self.chat_agent, state)
    
    def _tool_call(self, state:State):
        self._agent_call_template(self.prompt_store.get("tool_sys_prompt"), self.tool_agent, state)
        return {}

    def _join(self, state:State):
        return {}
    
    def _build_graph(self):
        builder = StateGraph(State)

        builder.add_node("chat_call", self._chat_call)
        builder.add_node("tool_call", self._tool_call)
        builder.add_node("join", self._join)


        builder.add_edge(START, "chat_call")
        builder.add_edge(START, "tool_call")
        builder.add_edge("chat_call", "join")
        builder.add_edge("tool_call", "join")
        builder.add_edge("join", END)

        return builder.compile()


if __name__ == "__main__":
    dual:Dual = DualConfig().setup()
    nargs = {"messages": [SystemMessage("you are a helpful bot named jarvis"),
                          HumanMessage("I feel very very sad")]
    }, {"configurable": {"thread_id": "3"}}

    # out = dual.invoke(*nargs)
    # print(out)
    for chunk in dual.invoke(*nargs, as_stream=True):
        continue
