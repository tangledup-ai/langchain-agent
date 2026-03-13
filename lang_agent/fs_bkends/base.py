import os
from dataclasses import dataclass
from typing import Any
from abc import ABC, abstractmethod
from loguru import logger

from lang_agent.config import InstantiateConfig


class BaseFilesystemBackend(ABC):
    backend: Any
    config: Any

    @abstractmethod
    def _build_backend(self):
        pass

    def get_backend(self):
        return self.backend
    
    def get_inf_inp(self):
        """get inference input for deepagent"""
        return {}

    def get_deepagent_params(self):
        """extra params to pass into the creation of deepagents"""
        if hasattr(self.config, "rt_skills_dir"):
            return {"skills" : [self.config.rt_skills_dir]}
        else:
            return {}


@dataclass
class FilesystemBackendConfig(InstantiateConfig):
    """
    Shared filesystem backend config behavior.
    If subclasses define these fields, this hook ensures they exist:
      - skills_dir
      - workspace_dir
    """

    def _ensure_dir_if_present(self, attr_name: str) -> None:
        path = getattr(self, attr_name, None)
        if not isinstance(path, str) or not path.strip():
            return
        os.makedirs(path, exist_ok=True)
        logger.info(f"Ensured {attr_name} exists: {path}")

    def __post_init__(self) -> None:
        self._ensure_dir_if_present("skills_dir")
        self._ensure_dir_if_present("workspace_dir")