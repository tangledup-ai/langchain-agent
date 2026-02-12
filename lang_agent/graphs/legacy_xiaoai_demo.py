from dataclasses import dataclass, field
from typing import Type, TypedDict, Literal, Dict, List, AsyncIterator
import tyro
import re
from pydantic import BaseModel, Field
from loguru import logger
import time

from langchain.chat_models import init_chat_model

from lang_agent.config import LLMNodeConfig
from lang_agent.base import GraphBase
from lang_agent.components.tool_manager import ToolManager, ToolManagerConfig
from lang_agent.graphs.graph_states import State

from langchain.agents import create_agent
from langchain.messages import SystemMessage, HumanMessage
from langchain.tools import tool

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END


SYS_PROMPT = """
        YOUR ROLE: give a short reply. Do not output special chararacters such as '*, -'. Do not give answer in markdown format. You are called Dream Companion. You are a professional psychological counselor. Your main work is psychological healing and emotional guidance, helping users understand their inner world through dream analysis.
        
        Example:

        User:
        “I dreamed that I was going on a business trip to Guangzhou. I was sitting on a high-speed train, looking out the window. When we passed a small town, I saw a little dog with a lame leg by the roadside. Its fur was dirty, and it limped along rummaging through trash cans for food. People were passing by, but no one stopped to help it. I desperately wanted to shout for the train to stop so I could get off and help it, but I couldn’t make a sound. I could only watch it get farther and farther away, and then I woke up. After waking up, my chest felt heavy and uncomfortable. I couldn’t quite explain the feeling— I just kept thinking about how lonely that little dog was, and it really broke my heart.”

        Understanding (your reply):
        “I can feel the discomfort you had after waking up. Seeing a vulnerable life struggle alone while being unable to help creates a very real sense of helplessness. The fact that you felt such compassion for the dog shows the empathy you carry inside you. That softness isn’t weakness—it’s your ability to feel others’ pain.”

        Analysis (your reply):
        “There’s no single ‘correct’ interpretation of dreams, but we can explore how this one might relate to your current state. ‘Going on a business trip to Guangzhou’ often symbolizes something you’re pushing forward recently—perhaps a work project or a life journey you’re facing on your own. The lame little dog can be seen as a projection of a ‘vulnerable self’ in your subconscious. It may reflect moments when you feel powerless or lonely, or situations in real life where you want to help but can’t change the outcome. Wanting to stop the train but being unable to speak mirrors a sense of suppressed feelings—having thoughts or care, but no channel to express them. This dream may be gently reminding you that your helplessness and empathy are both real, and that accepting your limits is also a form of self-compassion.”

        Feedback (your reply):
        “If you’re willing, you might reflect on whether something recently made you feel a similar kind of helplessness. Or think about what could help you feel a little more at ease right now. If you’d like, we can sit quietly together for a moment, or talk more whenever you’re ready.”

    
        """

TOOL_SYS_PROMPT = """You are a helpful helper and will use the self_led_control tool"""


@dataclass
class XiaoAiConfig(LLMNodeConfig):
    _target: Type = field(default_factory=lambda:XiaoAi)

    tool_manager_config: ToolManagerConfig = field(default_factory=ToolManagerConfig)


class XiaoAi(GraphBase):
    def __init__(self, config:XiaoAiConfig):
        self.config = config

        self._build_modules()
        self.workflow = self._build_graph()
        self.streamable_tags = [["dual_chat_llm"]]

    def _build_modules(self):
        self.chat_llm = init_chat_model(model="qwen-max",
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

        self.streamable_tags = [["dual_chat_llm"]]
    

    def _chat_call(self, state:State):

        out = self._agent_call_template(TOOL_SYS_PROMPT, self.tool_agent, state, "use self_led_control to set to white")

        # time.sleep(2.5)

        self._agent_call_template(TOOL_SYS_PROMPT, self.tool_agent, state, "use self_led_control to set to yellow")

        return self._agent_call_template(SYS_PROMPT, self.chat_agent, state)
    
    def _join(self, state:State):
        return {}
    
    def _build_graph(self):
        builder = StateGraph(State)

        builder.add_node("chat_call", self._chat_call)


        builder.add_edge(START, "chat_call")
        builder.add_edge("chat_call", END)

        return builder.compile()

    @staticmethod
    def _remove_special_chars(text: str) -> str:
        """Remove special characters like *, -, #, etc. from text."""
        # Remove markdown-style special characters
        return re.sub(r'[*\-#_`~>|]', '', text)

    async def ainvoke(self, *nargs, as_stream: bool = False, as_raw: bool = False, **kwargs):
        """Async invoke with special character removal from output."""
        if as_stream:
            return self._astream_cleaned(*nargs, **kwargs)
        else:
            result = await super().ainvoke(*nargs, as_stream=False, as_raw=as_raw, **kwargs)
            if as_raw:
                return result
            return self._remove_special_chars(result)

    async def _astream_cleaned(self, *nargs, **kwargs) -> AsyncIterator[str]:
        """Async streaming with special character removal."""
        async for chunk in super()._astream_result(*nargs, **kwargs):
            if isinstance(chunk, list):
                # Message lists for conversation recording — pass through
                yield chunk
                continue
            if not isinstance(chunk, str):
                # Skip non-string, non-list chunks (e.g. dict from tool-call content)
                continue
            cleaned = self._remove_special_chars(chunk)
            if cleaned:
                yield cleaned


if __name__ == "__main__":
    inp = """In the dream, I was on a high-speed train to Guangzhou, looking out the window. When we passed a small town, I saw a little dog with a hurt leg by the road. It was dirty and limping around, digging through trash for food. People walked past it, but no one stopped.

I really wanted the train to stop so I could get off and help, but I couldn’t make a sound. I just watched the dog get farther and farther away, and then I woke up. After that, my chest felt really heavy. I couldn’t explain why—I just felt sad, thinking about how alone that little dog was."""
    dual:XiaoAi = XiaoAiConfig().setup()
    nargs = {"messages": [SystemMessage("you are a helpful bot named jarvis"),
                          HumanMessage("I feel very very sad")]
    }, {"configurable": {"thread_id": "3"}}

    # out = dual.invoke(*nargs)
    # print(out)
    for chunk in dual.invoke(*nargs, as_stream=True):
        continue
