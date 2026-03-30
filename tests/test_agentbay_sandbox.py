from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock

from lang_agent.fs_bkends.agentbay_sandbox import (
    AgentBayBackend,
    AgentBaySandboxConfig,
    AgentBaySandboxBk,
)


# ---------------------------------------------------------------------------
# Helpers: build a mock AgentBay session that stubs command / file_system
# ---------------------------------------------------------------------------


def _make_command_result(*, stdout="", stderr="", exit_code=0, success=True):
    """Return a fake CommandResult object."""
    return SimpleNamespace(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        success=success,
    )


def _make_fs_read_result(*, content="", success=True, error_message=None):
    """Return a fake FileContentResult (as returned by file_system.read_file)."""
    return SimpleNamespace(
        content=content,
        success=success,
        error_message=error_message,
    )


def _make_session(*, session_id="s-test123"):
    """Build a mock Session with command + file_system stubs."""
    session = MagicMock()
    session.session_id = session_id

    # command.execute_command
    session.command.execute_command.return_value = _make_command_result(
        stdout="hello\n", exit_code=0
    )

    # file_system
    session.file_system.write_file.return_value = SimpleNamespace(success=True)
    session.file_system.read_file.return_value = _make_fs_read_result(
        content="file content", success=True
    )
    session.file_system.create_directory.return_value = SimpleNamespace(success=True)

    return session


# ===== AgentBayBackend tests =====


class TestAgentBayBackendId:
    def test_id_returns_session_id(self):
        session = _make_session(session_id="s-abc")
        backend = AgentBayBackend(session=session)
        assert backend.id == "s-abc"


class TestAgentBayBackendExecute:
    def test_execute_success(self):
        session = _make_session()
        backend = AgentBayBackend(session=session)
        result = backend.execute("echo hello")
        assert result.output == "hello\n"
        assert result.exit_code == 0
        assert result.truncated is False

    def test_execute_combines_stdout_and_stderr(self):
        session = _make_session()
        session.command.execute_command.return_value = _make_command_result(
            stdout="out", stderr="err", exit_code=0
        )
        backend = AgentBayBackend(session=session)
        result = backend.execute("some_cmd")
        assert result.output == "outerr"

    def test_execute_nonzero_exit(self):
        session = _make_session()
        session.command.execute_command.return_value = _make_command_result(
            stdout="", stderr="not found", exit_code=127, success=False
        )
        backend = AgentBayBackend(session=session)
        result = backend.execute("bad_cmd")
        assert result.exit_code == 127
        assert result.output == "not found"

    def test_execute_uses_default_timeout(self):
        session = _make_session()
        backend = AgentBayBackend(session=session, timeout_ms=60_000)
        backend.execute("echo x")
        session.command.execute_command.assert_called_once_with(
            "echo x", timeout_ms=60_000
        )

    def test_execute_override_timeout(self):
        session = _make_session()
        backend = AgentBayBackend(session=session, timeout_ms=60_000)
        backend.execute("echo x", timeout=5)
        session.command.execute_command.assert_called_once_with(
            "echo x", timeout_ms=5000
        )

    def test_execute_none_timeout_uses_default(self):
        session = _make_session()
        backend = AgentBayBackend(session=session, timeout_ms=120_000)
        backend.execute("echo x", timeout=None)
        session.command.execute_command.assert_called_once_with(
            "echo x", timeout_ms=120_000
        )


class TestAgentBayBackendUploadFiles:
    def test_upload_text_files_success(self):
        session = _make_session()
        backend = AgentBayBackend(session=session)
        files = [("/tmp/a.txt", b"hello"), ("/tmp/b.txt", b"world")]
        responses = backend.upload_files(files)
        assert len(responses) == 2
        assert responses[0].path == "/tmp/a.txt"
        assert responses[0].error is None
        assert responses[1].path == "/tmp/b.txt"
        assert responses[1].error is None
        assert session.file_system.write_file.call_count == 2

    def test_upload_binary_returns_error(self):
        session = _make_session()
        backend = AgentBayBackend(session=session)
        # 0x80 is invalid start byte in UTF-8
        files = [("/tmp/bin.dat", b"\x80\x81\x82")]
        responses = backend.upload_files(files)
        assert len(responses) == 1
        assert responses[0].error == "binary_not_supported"

    def test_upload_sdk_exception_returns_error(self):
        session = _make_session()
        session.file_system.write_file.side_effect = RuntimeError("network down")
        backend = AgentBayBackend(session=session)
        files = [("/tmp/f.txt", b"data")]
        responses = backend.upload_files(files)
        assert len(responses) == 1
        assert "network down" in responses[0].error

    def test_upload_partial_failure(self):
        session = _make_session()
        backend = AgentBayBackend(session=session)
        # First call succeeds, second raises
        session.file_system.write_file.side_effect = [
            SimpleNamespace(success=True),
            RuntimeError("timeout"),
        ]
        files = [("/tmp/a.txt", b"ok"), ("/tmp/b.txt", b"fail")]
        responses = backend.upload_files(files)
        assert responses[0].error is None
        assert "timeout" in responses[1].error


class TestAgentBayBackendDownloadFiles:
    def test_download_success(self):
        session = _make_session()
        session.file_system.read_file.return_value = _make_fs_read_result(
            content="file content", success=True
        )
        backend = AgentBayBackend(session=session)
        responses = backend.download_files(["/tmp/f.txt"])
        assert len(responses) == 1
        assert responses[0].path == "/tmp/f.txt"
        assert responses[0].content == b"file content"
        assert responses[0].error is None

    def test_download_not_found(self):
        session = _make_session()
        session.file_system.read_file.return_value = _make_fs_read_result(
            success=False, error_message="File not found"
        )
        backend = AgentBayBackend(session=session)
        responses = backend.download_files(["/tmp/missing.txt"])
        assert len(responses) == 1
        assert responses[0].content is None
        assert responses[0].error == "File not found"

    def test_download_sdk_exception_returns_error(self):
        session = _make_session()
        session.file_system.read_file.side_effect = RuntimeError("connection lost")
        backend = AgentBayBackend(session=session)
        responses = backend.download_files(["/tmp/f.txt"])
        assert len(responses) == 1
        assert responses[0].content is None
        assert "connection lost" in responses[0].error

    def test_download_partial_failure(self):
        session = _make_session()
        backend = AgentBayBackend(session=session)
        session.file_system.read_file.side_effect = [
            _make_fs_read_result(content="good", success=True),
            RuntimeError("fail"),
        ]
        responses = backend.download_files(["/tmp/a.txt", "/tmp/b.txt"])
        assert responses[0].error is None
        assert responses[0].content == b"good"
        assert responses[1].error is not None


# ===== AgentBaySandboxConfig tests =====


class TestAgentBaySandboxConfig:
    def test_defaults(self):
        config = AgentBaySandboxConfig()
        assert config.image_id == "code_latest"
        assert config.timeout_ms == 300_000
        assert config.skills_dir == "./workspace/skills"
        assert config.rt_skills_dir == ""

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("AGENTBAY_API_KEY", "akm-test-key")
        config = AgentBaySandboxConfig()
        assert config.api_key == "akm-test-key"

    def test_api_key_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("AGENTBAY_API_KEY", "akm-from-env")
        config = AgentBaySandboxConfig(api_key="akm-explicit")
        assert config.api_key == "akm-explicit"

    def test_api_key_missing_logs_error(self, monkeypatch):
        monkeypatch.delenv("AGENTBAY_API_KEY", raising=False)
        config = AgentBaySandboxConfig()
        assert config.api_key is None


# ===== AgentBaySandboxBk tests =====


class TestAgentBaySandboxBk:
    def _patch_agentbay(self, monkeypatch):
        """Patch AgentBay.create and AgentBay.__init__ to avoid real API calls."""
        from lang_agent.fs_bkends import agentbay_sandbox as mod

        fake_session = _make_session(session_id="s-fake")

        class FakeCreateResult:
            success = True
            error_message = None
            session = fake_session

        class FakeAgentBay:
            def __init__(self, api_key=None):
                self.api_key = api_key
                self._deleted = False

            def create(self, params):
                return FakeCreateResult()

            def delete(self, session):
                self._deleted = True

        monkeypatch.setattr(mod, "AgentBay", FakeAgentBay)
        return FakeAgentBay, fake_session

    def test_build_backend_creates_session(self, monkeypatch):
        FakeAgentBay, fake_session = self._patch_agentbay(monkeypatch)
        monkeypatch.delenv("AGENTBAY_API_KEY", raising=False)

        config = AgentBaySandboxConfig(api_key="akm-test")
        backend = AgentBaySandboxBk(config)

        assert backend.session is not None
        assert backend.session.session_id == "s-fake"
        assert backend.backend is not None
        assert isinstance(backend.backend, AgentBayBackend)

    def test_get_deepagent_params(self, monkeypatch):
        self._patch_agentbay(monkeypatch)
        config = AgentBaySandboxConfig(api_key="akm-test")
        bk = AgentBaySandboxBk(config)
        params = bk.get_deepagent_params()
        assert params == {"skills": ["/skills"]}

    def test_rt_skills_dir_default(self, monkeypatch):
        self._patch_agentbay(monkeypatch)
        config = AgentBaySandboxConfig(api_key="akm-test")
        bk = AgentBaySandboxBk(config)
        assert bk.config.rt_skills_dir == "/skills"

    def test_rt_skills_dir_preserved_when_set(self, monkeypatch):
        self._patch_agentbay(monkeypatch)
        config = AgentBaySandboxConfig(api_key="akm-test", rt_skills_dir="/custom")
        bk = AgentBaySandboxBk(config)
        assert bk.config.rt_skills_dir == "/custom"

    def test_upload_skills_skips_empty_dir(self, monkeypatch, tmp_path):
        self._patch_agentbay(monkeypatch)
        # tmp_path exists but contains no files
        config = AgentBaySandboxConfig(
            api_key="akm-test",
            skills_dir=str(tmp_path),
        )
        bk = AgentBaySandboxBk(config)
        # Should not raise — just log a warning
        assert bk.backend is not None

    def test_upload_skills_writes_files(self, monkeypatch, tmp_path):
        self._patch_agentbay(monkeypatch)
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("test skill", encoding="utf-8")

        config = AgentBaySandboxConfig(
            api_key="akm-test",
            skills_dir=str(tmp_path),
        )
        bk = AgentBaySandboxBk(config)
        # Verify write_file was called with the skill content
        bk.session.file_system.write_file.assert_called()
        call_args = bk.session.file_system.write_file.call_args_list
        paths = [c[0][0] for c in call_args]
        assert any("SKILL.md" in p for p in paths)

    def test_upload_skills_nested_dirs(self, monkeypatch, tmp_path):
        self._patch_agentbay(monkeypatch)
        sub = tmp_path / "my-skill"
        sub.mkdir()
        (sub / "SKILL.md").write_text("skill content", encoding="utf-8")
        (sub / "helper.py").write_text("print('hi')", encoding="utf-8")

        config = AgentBaySandboxConfig(
            api_key="akm-test",
            skills_dir=str(tmp_path),
        )
        bk = AgentBaySandboxBk(config)
        # create_directory should be called for the subdirectory
        bk.session.file_system.create_directory.assert_called()
        # write_file should be called for both files
        assert bk.session.file_system.write_file.call_count == 2

    def test_stop_deletes_session(self, monkeypatch):
        self._patch_agentbay(monkeypatch)
        config = AgentBaySandboxConfig(api_key="akm-test")
        bk = AgentBaySandboxBk(config)
        bk.stop()
        # After stop, the agent_bay._deleted should be True
        assert bk.agent_bay._deleted is True

    def test_backend_execute_delegates(self, monkeypatch):
        self._patch_agentbay(monkeypatch)
        config = AgentBaySandboxConfig(api_key="akm-test")
        bk = AgentBaySandboxBk(config)
        result = bk.backend.execute("echo test")
        assert result.output == "hello\n"
        assert result.exit_code == 0


# ===== Registration test =====


class TestRegistration:
    def test_agentbaysandbox_in_statebk_dict(self):
        from lang_agent.fs_bkends import statebk_dict

        assert "agentbaysandbox" in statebk_dict
        assert isinstance(statebk_dict["agentbaysandbox"], AgentBaySandboxConfig)
