from dataclasses import dataclass, field
from typing import Type, Optional, List, Tuple
from pathlib import Path
import os
import tyro
from loguru import logger

from agentbay import AgentBay, CreateSessionParams
from deepagents.backends.sandbox import BaseSandbox
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileUploadResponse,
    FileDownloadResponse,
)

from lang_agent.fs_bkends.base import BaseFilesystemBackend, FilesystemBackendConfig


class AgentBayBackend(BaseSandbox):
    """AgentBay sandbox implementation conforming to SandboxBackendProtocol.

    Implements execute(), upload_files(), and download_files() using
    AgentBay's session API. All other file operations (read, write, edit,
    ls_info, grep_raw, glob_info) are inherited from BaseSandbox and
    delegate to execute().
    """

    def __init__(self, *, session, timeout_ms: int = 300_000):
        self._session = session
        self._timeout_ms = timeout_ms

    @property
    def id(self) -> str:
        return self._session.session_id

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        ms = timeout * 1000 if timeout else self._timeout_ms
        result = self._session.command.execute_command(command, timeout_ms=ms)
        output = (result.stdout or "") + (result.stderr or "")
        return ExecuteResponse(
            output=output,
            exit_code=result.exit_code,
            truncated=False,
        )

    def upload_files(self, files: List[Tuple[str, bytes]]) -> List[FileUploadResponse]:
        responses: List[FileUploadResponse] = []
        for path, content in files:
            try:
                self._session.file_system.write_file(path, content.decode("utf-8"))
                responses.append(FileUploadResponse(path=path, error=None))
            except UnicodeDecodeError:
                responses.append(
                    FileUploadResponse(path=path, error="binary_not_supported")
                )
            except Exception as e:
                responses.append(FileUploadResponse(path=path, error=str(e)))
        return responses

    def download_files(self, paths: List[str]) -> List[FileDownloadResponse]:
        responses: List[FileDownloadResponse] = []
        for path in paths:
            try:
                result = self._session.file_system.read_file(path)
                if result.success:
                    responses.append(
                        FileDownloadResponse(
                            path=path,
                            content=result.content.encode("utf-8"),
                            error=None,
                        )
                    )
                else:
                    responses.append(
                        FileDownloadResponse(
                            path=path,
                            content=None,
                            error=result.error_message or "file_not_found",
                        )
                    )
            except Exception as e:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error=str(e))
                )
        return responses


@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class AgentBaySandboxConfig(FilesystemBackendConfig):
    _target: Type = field(default_factory=lambda: AgentBaySandboxBk)

    api_key: Optional[str] = None
    """AgentBay API key. Falls back to AGENTBAY_API_KEY env var."""

    image_id: str = "code_latest"
    """AgentBay image ID for the session."""

    timeout_ms: int = 300_000
    """Default command execution timeout in milliseconds (5 min)."""

    skills_dir: str = "./workspace/skills"
    """Local path to directory containing skill files to upload."""

    rt_skills_dir: str = ""
    """Runtime skills path inside the sandbox (auto-set from session workdir)."""

    def __post_init__(self):
        super().__post_init__()
        if self.api_key is None:
            self.api_key = os.environ.get("AGENTBAY_API_KEY")
            if self.api_key is None:
                logger.error("no AGENTBAY_API_KEY provided")
            else:
                logger.info("AGENTBAY_API_KEY loaded from environ")


class AgentBaySandboxBk(BaseFilesystemBackend):
    def __init__(self, config: AgentBaySandboxConfig):
        self.config = config
        self.agent_bay = None
        self.session = None
        self._build_backend()

    def _build_backend(self):
        self.agent_bay = AgentBay(api_key=self.config.api_key)
        params = CreateSessionParams(image_id=self.config.image_id)
        result = self.agent_bay.create(params)
        if not result.success:
            raise RuntimeError(
                f"Failed to create AgentBay session: {result.error_message}"
            )
        self.session = result.session
        logger.info(f"AgentBay session created: {self.session.session_id}")

        if not self.config.rt_skills_dir:
            self.config.rt_skills_dir = "/skills"

        self._upload_skills()
        self.backend = AgentBayBackend(
            session=self.session, timeout_ms=self.config.timeout_ms
        )

    def _upload_skills(self):
        skills_dir = Path(self.config.skills_dir)
        if not skills_dir.exists():
            logger.warning(f"Skills directory not found: {skills_dir}")
            return

        files_to_upload = []
        for skill_path in skills_dir.rglob("*"):
            if not skill_path.is_file():
                continue
            relative_path = skill_path.relative_to(skills_dir)
            remote_path = f"{self.config.rt_skills_dir}/{relative_path.as_posix()}"
            files_to_upload.append((remote_path, skill_path))

        if not files_to_upload:
            logger.warning("No skill files found to upload")
            return

        unique_dirs = {str(Path(f[0]).parent) for f in files_to_upload}
        for dir_path in sorted(unique_dirs):
            try:
                self.session.file_system.create_directory(dir_path)
            except Exception as e:
                if "permission denied" not in str(e).lower():
                    logger.debug(f"Creating dir {dir_path}: {e}")

        for remote_path, local_path in files_to_upload:
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.session.file_system.write_file(remote_path, content)
            except Exception as e:
                logger.error(f"Failed to upload {local_path}: {e}")

        logger.info(
            f"Uploaded {len(files_to_upload)} skill files to {self.config.rt_skills_dir}/"
        )

    def get_deepagent_params(self):
        return {"skills": [self.config.rt_skills_dir]}

    def stop(self):
        if self.agent_bay is not None and self.session is not None:
            self.agent_bay.delete(self.session)
            logger.info("AgentBay session deleted")
