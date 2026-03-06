import json
import time

import pytest
from fastapi import HTTPException

from lang_agent.components.server_pipeline_manager import ServerPipelineManager


class _DummyPipeline:
    def __init__(self, model: str):
        self.model = model


class _DummyConfig:
    def __init__(self, llm_name: str = "qwen-plus"):
        self.llm_name = llm_name

    def setup(self):
        return _DummyPipeline(model=self.llm_name)


def _write_registry(path, pipelines, api_keys=None):
    content = {"pipelines": pipelines, "api_keys": api_keys or {}}
    path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    # Ensure mtime changes reliably on fast CI filesystems.
    time.sleep(0.01)


def test_refresh_registry_picks_up_new_pipeline(tmp_path):
    registry_path = tmp_path / "pipeline_registry.json"
    _write_registry(
        registry_path,
        pipelines={
            "default": {
                "enabled": True,
                "config_file": None,
                "overrides": {"llm_name": "qwen-plus"},
            }
        },
    )
    manager = ServerPipelineManager(
        default_pipeline_id="default",
        default_config=_DummyConfig(),
    )
    manager.load_registry(str(registry_path))

    with pytest.raises(HTTPException) as exc_info:
        manager.resolve_pipeline_id(
            body={"pipeline_id": "blueberry"}, app_id=None, api_key="k1"
        )
    assert exc_info.value.status_code == 404

    _write_registry(
        registry_path,
        pipelines={
            "default": {
                "enabled": True,
                "config_file": None,
                "overrides": {"llm_name": "qwen-plus"},
            },
            "blueberry": {
                "enabled": True,
                "config_file": None,
                "overrides": {"llm_name": "qwen-max"},
            },
        },
    )
    changed = manager.refresh_registry_if_needed()
    assert changed is True

    resolved = manager.resolve_pipeline_id(
        body={"pipeline_id": "blueberry"}, app_id=None, api_key="k1"
    )
    assert resolved == "blueberry"


def test_refresh_registry_invalidates_cache_for_changed_pipeline(tmp_path):
    registry_path = tmp_path / "pipeline_registry.json"
    _write_registry(
        registry_path,
        pipelines={
            "blueberry": {
                "enabled": True,
                "config_file": None,
                "overrides": {"llm_name": "qwen-plus"},
            }
        },
    )
    manager = ServerPipelineManager(
        default_pipeline_id="blueberry",
        default_config=_DummyConfig(),
    )
    manager.load_registry(str(registry_path))

    first_pipeline, first_model = manager.get_pipeline("blueberry")
    assert first_model == "qwen-plus"

    _write_registry(
        registry_path,
        pipelines={
            "blueberry": {
                "enabled": True,
                "config_file": None,
                "overrides": {"llm_name": "qwen-max"},
            }
        },
    )
    changed = manager.refresh_registry_if_needed()
    assert changed is True

    second_pipeline, second_model = manager.get_pipeline("blueberry")
    assert second_model == "qwen-max"
    assert second_pipeline is not first_pipeline


def test_refresh_registry_applies_disabled_state_immediately(tmp_path):
    registry_path = tmp_path / "pipeline_registry.json"
    _write_registry(
        registry_path,
        pipelines={
            "blueberry": {
                "enabled": True,
                "config_file": None,
                "overrides": {"llm_name": "qwen-plus"},
            }
        },
    )
    manager = ServerPipelineManager(
        default_pipeline_id="blueberry",
        default_config=_DummyConfig(),
    )
    manager.load_registry(str(registry_path))
    manager.get_pipeline("blueberry")

    _write_registry(
        registry_path,
        pipelines={
            "blueberry": {
                "enabled": False,
                "config_file": None,
                "overrides": {"llm_name": "qwen-plus"},
            }
        },
    )
    changed = manager.refresh_registry_if_needed()
    assert changed is True

    with pytest.raises(HTTPException) as exc_info:
        manager.get_pipeline("blueberry")
    assert exc_info.value.status_code == 403



