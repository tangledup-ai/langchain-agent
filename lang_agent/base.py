from typing import List, Callable, TYPE_CHECKING
from abc import ABC, abstractmethod
from PIL import Image
from io import BytesIO
import matplotlib.pyplot as plt
from loguru import logger

from langgraph.graph.state import CompiledStateGraph


class LangToolBase(ABC):

    @abstractmethod
    def get_tool_fnc(self)->List[Callable]:
        pass


class GraphBase(ABC):
    workflow: CompiledStateGraph
    
    @abstractmethod
    def invoke(self, *nargs, **kwargs):
        pass

    def show_graph(self):
        #NOTE: just a useful tool for debugging; has zero useful functionality
        
        err_str = f"{type(self)} does not have workflow, this is unsupported"
        assert hasattr(self, "workflow"), err_str

        logger.info("creating image")
        img = Image.open(BytesIO(self.workflow.get_graph().draw_mermaid_png()))
        plt.imshow(img)
        plt.show()