from dataclasses import dataclass, field
from typing import Type
import tyro

from lang_agent.rag.emb import QwenEmbeddings

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class SimpleRagConfig:
    _target: Type = field(default_factory=lambda: SimpleRag)

    model_name:str = "text-embedding-v4"
    """embedding model name"""

    api_key:str = "wrong-key"
    """api_key for model; for generic text splitting; give a wrong key"""

    database_path:str = None
    """path to local database"""


class SimpleRag:
    def __init__(self, config:SimpleRagConfig):
        self.config = config
        self.emb = QwenEmbeddings(self.config.api_key,
                                  self.config.model_name)