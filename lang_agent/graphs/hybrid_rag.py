from dataclasses import dataclass, field
from typing import Type
import tyro
from loguru import logger

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from lang_agent.config import LLMNodeConfig
from lang_agent.base import GraphBase
from lang_agent.graphs.graph_states import HybridRagState
from langgraph.graph import StateGraph, START, END

# 导入我们刚刚封装好的独立节点组件
from lang_agent.components.hybrid_retriever_node import HybridRetrieverNodeConfig, HybridRetrieverNode


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class HybridRagGraphConfig(LLMNodeConfig):
    _target: Type = field(default_factory=lambda: HybridRagGraph)

    # 现在的 Graph 只需要配置一个子节点 config
    retriever_node_config: HybridRetrieverNodeConfig = field(default_factory=HybridRetrieverNodeConfig)


class HybridRagGraph(GraphBase):
    def __init__(self, config: HybridRagGraphConfig):
        self.config = config

        self.populate_modules()
        self.workflow = self._build_graph()

        self.streamable_tags = [["main_llm"]]

    def populate_modules(self):
        # 1. Init Main LLM for Generation
        self.llm = init_chat_model(
            model=self.config.llm_name,
            model_provider=self.config.llm_provider,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            tags=["main_llm"]
        )
        
        # 2. 初始化封装好的双重验证节点实例
        self.retriever_node: HybridRetrieverNode = self.config.retriever_node_config.setup()

    def _get_last_user_query(self, state: HybridRagState) -> str:
        msgs = state.get("messages", [])
        if not msgs and "inp" in state:
            msgs = state["inp"][0]["messages"]
        
        for msg in reversed(msgs):
            if isinstance(msg, HumanMessage):
                return msg.content
        return "Unknown query"

    def _generate(self, state: HybridRagState):
        query = self._get_last_user_query(state)
        context = state.get("context", "No context provided.")
        
        prompt_content = (
            "You are a helpful and enthusiastic AI assistant for a tea/beverage store.\n"
            "Please answer the user's question based on the provided context.\n"
            "If Real-time Verification Results contradict Semantic Search Results, ALWAYS trust the Real-time Verification.\n"
            "If the Real-time Verification provides a detailed introduction of a dish (e.g. '我俩最最好'), present it to the user naturally and attractively.\n\n"
            f"Context:\n{context}\n\n"
        )
        
        response = self.llm.invoke([
            SystemMessage(content=prompt_content),
            HumanMessage(content=query)
        ])
        
        return {"messages": [AIMessage(content=response.content)]}

    def _build_graph(self):
        builder = StateGraph(HybridRagState)

        # 把类的方法作为节点传入
        builder.add_node("hybrid_retrieve", self.retriever_node.as_node())
        builder.add_node("generate", self._generate)
        
        # 现在的图结构非常简单：检索 -> 生成
        builder.add_edge(START, "hybrid_retrieve")
        builder.add_edge("hybrid_retrieve", "generate")
        builder.add_edge("generate", END)

        return builder.compile()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    config = HybridRagGraphConfig()
    graph = config.setup()
    
    # print(graph.invoke({"messages": [HumanMessage("推荐一款好喝的茶")]}, {"configurable": {"thread_id": "1"}}))
