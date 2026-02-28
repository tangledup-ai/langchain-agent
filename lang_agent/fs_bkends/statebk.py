from dataclasses import dataclass, field, is_dataclass
from typing import Type, TypedDict, Literal, Dict, List, Tuple, Optional
import tyro
import os.path as osp
from abc import ABC, abstractmethod
import glob
from loguru import logger

from deepagents.backends.utils import create_file_data
from deepagents.backends import StateBackend

from lang_agent.config import InstantiateConfig
from lang_agent.fs_bkends import BaseFilesystemBackend

def read_as_utf8(file_path:str):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def build_skill_fs_dict(skill_dir:str, virt_path:str="/skills"):
    skills_fs = sorted(glob.glob(osp.join(skill_dir, "**/*.md")))

    get_parent = lambda f: osp.basename(osp.dirname(f))
    build_vert_path = lambda f: osp.join(virt_path, get_parent(f), osp.basename(f))

    skill_fs_dict = {}
    for skill_f in skills_fs:
        logger.info(f"loading skill: {skill_f}")
        skill_fs_dict[build_vert_path(skill_f)] = create_file_data(read_as_utf8(skill_f))
    return skill_fs_dict


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class StateBkConfig(InstantiateConfig):
    _target:Type = field(default_factory=lambda:StateBk)

    skills_dir:str = "./assets/skills"
    """path to directory containing skill files"""

    rt_skills_dir:str = "/skills"
    """path to directory with skills in runtime directory"""

    def __post_init__(self):
        err_msg = f"{self.skills_dir} does not exist"
        assert osp.exists(self.skills_dir), err_msg


class StateBk(BaseFilesystemBackend):
    def __init__(self, config:StateBkConfig):
        self.config = config
        self.skills_dict = None
        self._build_backend()
    
    def _build_backend(self):
        self.skills_dict = build_skill_fs_dict(self.config.skills_dir)
        self.backend = lambda rt : StateBackend(rt)

    def get_backend(self):
        return self.backend
    
    def _get_rt_skill_dir(self)->List[str]:
        """get runtime skill dir"""
        return [self.config.rt_skills_dir]

    def get_inf_inp(self):
        """get inference input for deepagent"""
        return {"files":self.skills_dict}

    def get_deepagent_params(self):
        return {"skills" : self._get_rt_skill_dir()}