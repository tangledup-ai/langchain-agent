from dataclasses import dataclass, field
from typing import Type, List, Dict, Any, Tuple
import tyro
import os
from loguru import logger

from langchain_postgres import PGVector
from langchain_core.documents.base import Document

from lang_agent.rag.emb import QwenEmbeddings
from lang_agent.config import ToolConfig, LLMKeyConfig

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class PGRetrieverConfig(ToolConfig, LLMKeyConfig):
    _target: Type = field(default_factory=lambda: PGRetriever)

    model_name: str = "text-embedding-v4"
    """embedding model name"""

    connection_string: str = None
    """PG database connection string. If None, will fallback to PG_VECTOR_CONN_STR from env."""
    
    collection_name: str = "my_docs"
    """collection name in PGVector"""
    
    top_k: int = 4
    """Number of documents to retrieve"""

    def __post_init__(self):
        super().__post_init__()
        if self.connection_string is None:
            # Fallback to specific vector DB env var
            env_conn = os.environ.get("PG_VECTOR_CONN_STR")
            if env_conn:
                # PGVector requires postgresql+psycopg:// or postgresql+psycopg2://
                if env_conn.startswith("postgresql://"):
                    env_conn = env_conn.replace("postgresql://", "postgresql+psycopg://", 1)
                self.connection_string = env_conn
            else:
                # Default fallback (pointing to the business DB on port 5433)
                self.connection_string = "postgresql+psycopg://xiaoliang:123xiaoliang@47.101.218.42:5433/your_business_db"
                logger.warning(f"No PG_VECTOR_CONN_STR found in env, using default: {self.connection_string}")



class PGRetriever:
    """
    Direct PGVector retriever that fetches documents using similarity search.
    """
    def __init__(self, config: PGRetrieverConfig):
        self.config = config
        self.emb = QwenEmbeddings(self.config.api_key, self.config.model_name)
        
        self.vectorstore = PGVector(
            embeddings=self.emb,
            collection_name=self.config.collection_name,
            connection=self.config.connection_string
        )
        
    def retrieve_with_scores(self, query: str) -> Tuple[List[str], List[float], float]:
        """
        检索文档并返回分数
        """
        try:
            docs_with_scores = self.vectorstore.similarity_search_with_score(
                query, 
                k=self.config.top_k
            )
            
            docs = [doc.page_content for doc, _ in docs_with_scores]
            scores = [score for _, score in docs_with_scores]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            
            return docs, scores, avg_score
            
        except Exception as e:
            logger.error(f"PGVector retrieval failed: {type(e).__name__} - {str(e)}")
            return [], [], 0.0

    # 如果后续需要基于 metadata 过滤，可以使用类似以下方法：
    # def retrieve_available(self, query: str) -> List[Document]:
    #     return self.vectorstore.similarity_search(
    #         query, 
    #         k=self.config.top_k, 
    #         filter={"is_available": "t"}
    #     )
