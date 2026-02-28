from dataclasses import dataclass, field, is_dataclass
from typing import Type, TypedDict, Literal, Dict, List, Tuple, Optional
import tyro
import os.path as osp
from abc import ABC, abstractmethod
import glob
from loguru import logger

from deepagents.backends.utils import create_file_data
from deepagents.backends import LocalShellBackend

from lang_agent.config import InstantiateConfig
from lang_agent.fs_bkends import BaseFilesystemBackend


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class LocalShellConfig(InstantiateConfig):
    _target:Type = field(default_factory=lambda:LocalShell)

    workspace_dir:str = "./workspace"
    """path to workspace directory"""

    skills_dir:str = "./workspace/skills"
    """path to directory containing skill files"""

    rt_skills_dir:str = "/skills"
    """path to directory with skills in runtime directory"""


class LocalShell(BaseFilesystemBackend):
    def __init__(self, config:LocalShellConfig):
        logger.warning("Caution: The LocalShell backend grants direct access to the local system shell. Improper use can pose significant security and safety risks, including unintended code execution and file access. Use this backend with extreme care.")
        self.config = config
        self._build_backend()
    
    def _build_backend(self):
        self.backend = LocalShellBackend(root_dir=self.config.workspace_dir,
                                         virtual_mode=True,
                                        #  env={"PATH": "/usr/bin:/bin"}
                                         inherit_env=True)