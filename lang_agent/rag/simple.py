from dataclasses import dataclass, field
from typing import Type
import tyro
from mcp.server.fastmcp import FastMCP
from typing import List
import tyro

from langchain_community.vectorstores import FAISS
from langchain_core.documents.base import Document

from lang_agent.rag.emb import QwenEmbeddings
from lang_agent.config import InstantiateConfig


mcp = FastMCP("Rag")

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class SimpleRagConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda: SimpleRag)

    model_name:str = "text-embedding-v4"
    """embedding model name"""

    api_key:str = "wrong-key"
    """api_key for model; for generic text splitting; give a wrong key"""

    folder_path:str = None
    """path to local database"""


class SimpleRag:
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
        
    @mcp.tool()
    def retrieve(self, query:str):
        retrieved_docs:List[Document] = self.vec_store.search(query, search_kwargs={"k":3})
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in retrieved_docs
        )
        return serialized, retrieved_docs


if __name__ == "__main__":
    config = tyro.cli(SimpleRagConfig)
    rag = SimpleRag(config)
    mcp.run(transport="stdio")