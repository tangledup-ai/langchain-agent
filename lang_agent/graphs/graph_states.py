from typing import Type, TypedDict, Literal, Dict, List, Tuple, Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

class State(TypedDict):
    inp: Tuple[Dict[str, List[SystemMessage | HumanMessage]], 
               Dict[str, Dict[str, str|int]]]
    messages: List[SystemMessage | HumanMessage]
    decision: str


class ChattyToolState(TypedDict):
    inp: Tuple[Dict[str, List[SystemMessage | HumanMessage]], 
               Dict[str, Dict[str, str|int]]]
    tool_messages: List[SystemMessage | HumanMessage | AIMessage]
    chatty_messages: List[SystemMessage | HumanMessage | AIMessage]
    tool_done: bool  # Flag to signal when tool execution is complete
