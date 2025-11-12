from typing import Type, TypedDict, Literal, Dict, List, Tuple, Any

from langchain_core.messages import SystemMessage, HumanMessage

class State(TypedDict):
    inp: Tuple[Dict[str, List[SystemMessage | HumanMessage]], 
               Dict[str, Dict[str, str|int]]]
    messages: List[SystemMessage | HumanMessage]
    decision: str
    subgraph_states: Dict[str, Any]   # NOTE: Naively assuming subgraphs
                                      #       won't be so complicated

