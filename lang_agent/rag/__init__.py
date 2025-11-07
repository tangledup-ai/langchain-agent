"""
RAG (Retrieval Augmented Generation) 模块

该模块提供了检索增强生成的功能，包括:
- 嵌入向量生成和存储
- 相似度搜索和文档检索
- 基于FAISS的向量数据库支持
- 阿里云DashScope嵌入服务集成
"""

from .emb import QwenEmbeddings
from .simple import SimpleRag

__all__ = ["QwenEmbeddings", "SimpleRag"]