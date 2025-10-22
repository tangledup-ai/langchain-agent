from typing import List, Callable
from abc import ABC, abstractmethod


class LangToolBase(ABC):

    @abstractmethod
    def get_tool_fnc(self)->List[Callable]:
        pass


class GraphBase(ABC):
    
    @property
    @abstractmethod
    def agent(self):
        """The agent object that must be provided by concrete implementations."""
        pass
    
    def get_agent(self):
        """Convenience method to access the agent."""
        return self.agent