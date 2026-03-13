from dataclasses import dataclass, field
from typing import Type
import tyro
import os.path as osp
import glob
from loguru import logger

from deepagents.backends.utils import create_file_data
from deepagents.backends import StateBackend

from lang_agent.fs_bkends.base import BaseFilesystemBackend, FilesystemBackendConfig

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
class StateBkConfig(FilesystemBackendConfig):
    _target:Type = field(default_factory=lambda:StateBk)

    skills_dir:str = "./assets/skills"
    """path to directory containing skill files"""

    rt_skills_dir:str = "/skills"
    """path to directory with skills in runtime directory"""


class StateBk(BaseFilesystemBackend):
    def __init__(self, config:StateBkConfig):
        self.config = config
        self.skills_dict = None
        self._build_backend()
    
    def _build_backend(self):
        self.skills_dict = build_skill_fs_dict(self.config.skills_dir)
        self.backend = lambda rt : StateBackend(rt)
    
    def get_inf_inp(self):
        """get inference input for deepagent"""
        return {"files":self.skills_dict}