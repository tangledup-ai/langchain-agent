from typing import List, Callable, Tuple, Dict, AsyncIterator
from abc import ABC, abstractmethod
from PIL import Image
from io import BytesIO
import matplotlib.pyplot as plt
from loguru import logger

from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import BaseMessage


class LangToolBase(ABC):
    """
    class to inherit if to create a new local tool
    """

    @abstractmethod
    def get_tool_fnc(self)->List[Callable]:
        pass


class GraphBase(ABC):
    workflow: CompiledStateGraph
    
    @abstractmethod
    def invoke(self, *nargs, **kwargs):
        pass

    async def ainvoke(self, *nargs, **kwargs):
        """Async version of invoke. Subclasses should override for true async support."""
        raise NotImplementedError("Subclass should implement ainvoke for async support")

    def show_graph(self, ret_img:bool=False):
        #NOTE: just a useful tool for debugging; has zero useful functionality
        
        err_str = f"{type(self)} does not have workflow, this is unsupported"
        assert hasattr(self, "workflow"), err_str

        logger.info("creating image")
        img = Image.open(BytesIO(self.workflow.get_graph().draw_mermaid_png()))

        if not ret_img:
            plt.imshow(img)
            plt.show()
        else:
            return img


class ToolNodeBase(GraphBase):
    @abstractmethod
    def get_streamable_tags(self)->List[List[str]]:
        """
        returns names of llm model to listen to when streaming
        NOTE: must be [['A1'], ['A2'] ...]
        """
        return [["tool_llm"]]
    
    def get_delay_keys(self)->Tuple[str, str]:
        """
        returns 2 words, one for starting delayed yeilding, the other for ending delayed yielding,
        they should be of format ('[key1]', '[key2]'); key1 is starting, key2 is ending
        """
        return None, None
    
    @abstractmethod
    def invoke(self, inp)->Dict[str, List[BaseMessage]]:
        pass

    async def ainvoke(self, inp)->Dict[str, List[BaseMessage]]:
        """Async version of invoke. Subclasses should override for true async support."""
        raise NotImplementedError("Subclass should implement ainvoke for async support")