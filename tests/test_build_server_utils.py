import json
from pathlib import Path
from types import SimpleNamespace

from lang_agent.front_api import build_server_utils


class _ReactGraphConfig:
    pass


class _RoutingConfig:
    pass


def test_sync_pipeline_registry_from_configs_registers_yaml_files(monkeypatch, tmp_path):
    registry_path = tmp_path / "configs" / "pipeline_registry.json"
    pipeline_dir = tmp_path / "configs" / "pipelines"
    pipeline_dir.mkdir(parents=True)

    (pipeline_dir / "bayer_simple.yaml").write_text("stub", encoding="utf-8")
    (pipeline_dir / "rt2.yaml").write_text("stub", encoding="utf-8")

    registry_path.write_text(
        json.dumps(
            {
                "pipelines": {
                    "bayer_simple": {
                        "enabled": False,
                        "config_file": "configs/pipelines/old.yaml",
                        "graph_id": "react",
                        "llm_name": "old-model",
                    }
                },
                "api_keys": {},
            }
        ),
        encoding="utf-8",
    )

    def _fake_load(path: str):
        name = Path(path).stem
        if name == "bayer_simple":
            return SimpleNamespace(
                pipeline_id="bayer_simple",
                llm_name="gemini-3-flash",
                graph_config=_ReactGraphConfig(),
            )
        if name == "rt2":
            return SimpleNamespace(
                pipeline_id="rt2",
                llm_name="qwen-plus",
                graph_config=_RoutingConfig(),
            )
        raise AssertionError(path)

    monkeypatch.setattr(build_server_utils, "load_tyro_conf", _fake_load)
    monkeypatch.setattr(build_server_utils, "_PROJECT_ROOT", str(tmp_path))

    changed = build_server_utils.sync_pipeline_registry_from_configs(
        registry_f=str(registry_path)
    )

    assert changed is True

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert data["pipelines"]["bayer_simple"] == {
        "enabled": False,
        "config_file": "configs/pipelines/bayer_simple.yaml",
        "graph_id": "react",
        "llm_name": "gemini-3-flash",
    }
    assert data["pipelines"]["rt2"] == {
        "enabled": True,
        "config_file": "configs/pipelines/rt2.yaml",
        "graph_id": "routing",
        "llm_name": "qwen-plus",
    }
