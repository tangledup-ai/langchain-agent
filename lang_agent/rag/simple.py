from dataclasses import dataclass, field
from typing import Type, List
import tyro
from mcp.server.fastmcp import FastMCP
from loguru import logger
import os.path as osp

from langchain_community.vectorstores import FAISS
from langchain_core.documents.base import Document

from lang_agent.rag.emb import QwenEmbeddings
from lang_agent.config import ToolConfig, LLMKeyConfig
from lang_agent.base import LangToolBase


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class SimpleRagConfig(ToolConfig, LLMKeyConfig):
    _target: Type = field(default_factory=lambda: SimpleRag)

    model_name:str = "text-embedding-v4"
    """embedding model name"""

    folder_path:str = None
    """path to docker database"""
    
    def __post_init__(self):
        super().__post_init__()
        if self.folder_path is None:
            self.folder_path = osp.join(osp.dirname(osp.dirname(osp.dirname(__file__))), "assets", "xiaozhan_emb")
            logger.info(f"no rag database provided, using default {self.folder_path}")

    



class SimpleRag(LangToolBase):
    def __init__(self, config:SimpleRagConfig):
        self.config = config
        self.emb = QwenEmbeddings(self.config.api_key,
                                  self.config.model_name)
        
        
        self.vec_store = FAISS.load_local(
            folder_path=self.config.folder_path,
            embeddings=self.emb,
            allow_dangerous_deserialization=True  # Required for LangChain >= 0.1.1
        )

        # self.retriever = self.vec_store.as_retriever(search_kwargs={"k":3})
        
    def retrieve(self, query:str)->str:
        """
        检索与给定查询相关的文档，并将其序列化为字符串格式。
        参数:
            query (str): 用户输入的查询字符串。
        返回:
            str
            - 序列化后的文档内容字符串，每个文档包含来源和内容。
        该工具用于基于向量存储检索相关文档，适用于问答和知识检索场景。

        用例示例:
        1. 用户询问“推荐一些辣味食物”，系统会检索并返回相关的辣味美食推荐文档。
        2. 用户搜索“适合夏天的清爽饮品”，系统会检索并返回相关饮品推荐及其来源信息。
        """
        retrieved_docs:List[Document] = self.vec_store.similarity_search(query,
                                                                         k=10)
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )
        return serialized #, retrieved_docs
    
    def get_tool_fnc(self):
        return [self.retrieve]


# if __name__ == "__main__":
# #     # config = tyro.cli(SimpleRagConfig)
#     config = SimpleRagConfig()
#     rag:SimpleRag = config.setup()

#     import time 
#     st_time = time.time()
#     u = rag.retrieve("灯与尘")
#     print(time.time() - st_time)
#     print(u)
#     mcp.run(transport="stdio")