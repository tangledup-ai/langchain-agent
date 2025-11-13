from typing import List, Callable
from abc import ABC, abstractmethod


class LangToolBase(ABC):

    @abstractmethod
    def get_tool_fnc(self)->List[Callable]:
        pass


class GraphBase(ABC):
    
    @abstractmethod
    def invoke(self, *nargs, **kwargs):
        pass


class ToolNodeBase(ABC):

    @abstractmethod
    def tool_node_call(self, *nargs, **kwargs):
        pass