from dataclasses import dataclass, field, is_dataclass
from typing import Any
import tyro
import os.path as osp
from abc import ABC, abstractmethod


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