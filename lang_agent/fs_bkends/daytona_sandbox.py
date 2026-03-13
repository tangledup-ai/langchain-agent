from dataclasses import dataclass, field
from typing import Type, Optional
from pathlib import Path
import os
import tyro
from loguru import logger

from daytona import Daytona, DaytonaConfig, FileUpload
from langchain_daytona import DaytonaSandbox

from lang_agent.fs_bkends.base import BaseFilesystemBackend, FilesystemBackendConfig


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class DaytonaSandboxConfig(FilesystemBackendConfig):
    _target: Type = field(default_factory=lambda: DaytonaSandboxBk)

    api_key: Optional[str] = None
    """Daytona API key. Falls back to DAYTONA_API_KEY env var."""

    skills_dir: str = "./workspace/skills"
    """local path to directory containing skill files to upload"""

    rt_skills_dir: str = ""
    """runtime skills path inside the sandbox (auto-set from sandbox workdir)"""

    def __post_init__(self):
        super().__post_init__()
        if self.api_key is None:
            self.api_key = os.environ.get("DAYTONA_API_KEY")
            if self.api_key is None:
                logger.error("no DAYTONA_API_KEY provided")
            else:
                logger.info("DAYTONA_API_KEY loaded from environ")


class DaytonaSandboxBk(BaseFilesystemBackend):
    def __init__(self, config: DaytonaSandboxConfig):
        self.config = config
        self.sandbox = None
        self._build_backend()

    def _build_backend(self):
        daytona = Daytona(DaytonaConfig(api_key=self.config.api_key))
        self.sandbox = daytona.create()
        workdir = self.sandbox.get_work_dir()
        logger.info(f"Daytona sandbox created: {self.sandbox.id}, workdir: {workdir}")

        if not self.config.rt_skills_dir:
            self.config.rt_skills_dir = f"{workdir}/skills"

        self._upload_skills(workdir)
        self.backend = DaytonaSandbox(sandbox=self.sandbox)

    def _upload_skills(self, workdir: str):
        skills_dir = Path(self.config.skills_dir)
        if not skills_dir.exists():
            logger.warning(f"Skills directory not found: {skills_dir}")
            return

        files_to_upload = []
        for skill_path in skills_dir.rglob("*"):
            if not skill_path.is_file():
                continue
            relative_path = skill_path.relative_to(skills_dir)
            remote_path = f"{workdir}/skills/{relative_path.as_posix()}"
            with open(skill_path, "rb") as f:
                files_to_upload.append(FileUpload(source=f.read(), destination=remote_path))

        if not files_to_upload:
            logger.warning("No skill files found to upload")
            return

        unique_dirs = {str(Path(u.destination).parent) for u in files_to_upload}
        for dir_path in sorted(unique_dirs):
            try:
                self.sandbox.fs.create_folder(dir_path, "755")
            except Exception as e:
                if "permission denied" not in str(e).lower():
                    logger.debug(f"Creating dir {dir_path}: {e}")

        self.sandbox.fs.upload_files(files_to_upload)
        logger.info(f"Uploaded {len(files_to_upload)} skill files to {workdir}/skills/")

    def get_deepagent_params(self):
        return {"skills": [self.config.rt_skills_dir]}

    def stop(self):
        if self.sandbox is not None:
            self.sandbox.stop()
            logger.info("Daytona sandbox stopped")
