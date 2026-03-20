from __future__ import annotations

from typing import List, Callable, Tuple, Dict, AsyncIterator, TYPE_CHECKING
from abc import ABC, abstractmethod
from PIL import Image
from io import BytesIO
import matplotlib.pyplot as plt
from loguru import logger

from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.base import BaseMessageChunk

from lang_agent.components.text_releaser import TextReleaser, AsyncTextReleaser
from lang_agent.utils import tree_leaves

if TYPE_CHECKING:
    from lang_agent.graphs.graph_states import State


class LangToolBase(ABC):
    """
    class to inherit if to create a new local tool
    """

    @abstractmethod
    def get_tool_fnc(self)->List[Callable]:
        pass


class GraphBase(ABC):
    workflow: CompiledStateGraph     # the main workflow
    streamable_tags: List[List[str]] = [["main_llm"]] # which llm to stream outputs; see routing.py for complex usage
    textreleaser_delay_keys: List[str] = (None, None)  # use to control when to start streaming; see routing.py for complex usage

    def _build_modules(self):
        # NOTE: optional abc
        pass

    def _build_graph(self):
        # NOTE: optional abc
        pass
    
    def _stream_result(self, *nargs, **kwargs):

        def text_iterator():
            for _, mode, out in self.workflow.stream({"inp": nargs}, 
                                                     stream_mode=["messages", "values"], 
                                                     subgraphs=True,
                                                     **kwargs):
                if mode == "values":
                    val = out.get("messages")
                    if val is not None:
                        yield val
                    continue

                chunk, metadata = out
                tags = metadata.get("tags")
                if not (tags in self.streamable_tags):
                    continue

                if isinstance(chunk, (BaseMessageChunk, BaseMessage)) and getattr(chunk, "content", None):
                    yield chunk.content

        text_releaser = TextReleaser(*self.textreleaser_delay_keys)
        logger.info("streaming output")
        for chunk in text_releaser.release(text_iterator()):
            yield chunk
    
    # NOTE: DEFAULT IMPLEMENTATION; Overide to support your class
    def invoke(self, *nargs, as_stream:bool=False, as_raw:bool=False, **kwargs):
        self._validate_input(*nargs, **kwargs)

        if as_stream:
            # Stream messages from the workflow
            print("\033[93m====================STREAM OUTPUT=============================\033[0m")
            return self._stream_result(*nargs, **kwargs)
        else:
            state = self.workflow.invoke({"inp": nargs})
            
            msg_list = tree_leaves(state)

            for e in msg_list:
                if isinstance(e, BaseMessage):
                    e.pretty_print()
                    
            if as_raw:
                return msg_list

            return msg_list[-1].content
        
    # NOTE: DEFAULT IMPLEMENTATION; Overide to support your class
    async def ainvoke(self, *nargs, as_stream:bool=False, as_raw:bool=False, **kwargs):
        """Async version of invoke using LangGraph's native async support."""
        self._validate_input(*nargs, **kwargs)

        if as_stream:
            # Stream messages from the workflow asynchronously
            print("\033[93m====================ASYNC STREAM OUTPUT=============================\033[0m")
            return self._astream_result(*nargs, **kwargs)
        else:
            state = await self.workflow.ainvoke({"inp": nargs})
            
            msg_list = tree_leaves(state)

            for e in msg_list:
                if isinstance(e, BaseMessage):
                    e.pretty_print()
                    
            if as_raw:
                return msg_list

            return msg_list[-1].content

    async def _astream_result(self, *nargs, **kwargs) -> AsyncIterator[str]:
        """Async streaming using LangGraph's astream method."""

        async def text_iterator():
            async for _, mode, out in self.workflow.astream({"inp": nargs}, 
                                                        stream_mode=["messages", "values"], 
                                                        subgraphs=True,
                                                        **kwargs):
                if mode == "values":
                    val = out.get("messages")
                    if val is not None:
                        yield val
                    continue

                chunk, metadata = out
                tags = metadata.get("tags")
                if not (tags in self.streamable_tags):
                    continue

                if isinstance(chunk, (BaseMessageChunk, BaseMessage)) and getattr(chunk, "content", None):
                    yield chunk.content

        text_releaser = AsyncTextReleaser(*self.textreleaser_delay_keys)
        logger.info("streaming output")
        async for chunk in text_releaser.release(text_iterator()):
            yield chunk 
    
    def _validate_input(self, *nargs, **kwargs):
        print("\033[93m====================INPUT HUMAN MESSAGES=============================\033[0m")
        for e in nargs[0]["messages"]:
            if isinstance(e, HumanMessage):
                e.pretty_print()
        print("\033[93m====================END INPUT HUMAN MESSAGES=============================\033[0m")
        print(f"\033[93m model used: {self.config.llm_name}\033[0m")

        assert len(kwargs) == 0, "due to inp assumptions"
    
    def _get_inp_msgs(self, state:State):
        msgs = state["inp"][0]["messages"]
        return [e for e in msgs if not isinstance(e, SystemMessage)]
    
    def _agent_call_template(self, system_prompt:str,
                                  model:CompiledStateGraph, 
                                  state:State,
                                  human_msg:str = None):
        if state.get("messages") is not None:
            inp = state["messages"], state["inp"][1]
        else:
            inp = state["inp"]
        
        messages = [
            SystemMessage(system_prompt),
            *self._get_inp_msgs(state)
        ]

        if human_msg is not None:
            messages.append(HumanMessage(human_msg))

        inp = ({"messages": messages}, state["inp"][1])


        out = model.invoke(*inp)
        return {"messages": out}

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
    
    def clear_all_memory(self):
        # NOTE: self.memory = MemorySaver
        for thread_id in list(self.memory.storage):
            self.memory.delete_thread(thread_id)
    
    def clear_memory_device_id(self, device_id:str):
        # NOTE: self.memory = MemorySaver
        rm_threads = [th for th in self.memory.storage if (device_id in th)]
        for thread_id in rm_threads:
            self.memory.delete_thread(thread_id)

    def clear_memory(self, device_id:str=None):
        # Clear the agent's (LangChain) memory if available
        if hasattr(self, "memory") and self.memory is not None:
            if isinstance(self.memory, MemorySaver) and (device_id is None):
                self.clear_all_memory()
            else:
                self.clear_memory_device_id(device_id)
    
    async def aclear_memory(self, device_id:str=None):
        # Clear the agent's (LangChain) memory if available (async version)
        if hasattr(self, "memory") and self.memory is not None:
            if isinstance(self.memory, MemorySaver):
                if device_id is None:
                    # Clear all memory
                    for thread_id in list(self.memory.storage):
                        await self.memory.adelete_thread(thread_id)
                else:
                    # Clear memory for specific device_id
                    rm_threads = [th for th in self.memory.storage if (device_id in th)]
                    for thread_id in rm_threads:
                        await self.memory.adelete_thread(thread_id)
            


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