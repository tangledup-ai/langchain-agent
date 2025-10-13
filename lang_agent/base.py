from typing import List, Callable
from abc import ABC, abstractmethod


class LangToolBase(ABC):

    @abstractmethod
    def get_tool_fnc(self)->List[Callable]:
        pass