import json
import os
from pathlib import Path

from fastapi.testclient import TestClient


os.environ.setdefault("CONN_STR", "postgresql://dummy:dummy@localhost/dummy")

import fastapi_server.front_apis as front_apis


def _fake_build_fn(
    pipeline_id: str,
    prompt_set: str,
    tool_keys,
    api_key: str,
    llm_name: str = "qwen-plus",
    pipeline_config_dir: str = "configs/pipelines",
):
    out_dir = Path(pipeline_config_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{pipeline_id}.yaml"
    out_file.write_text(
        json.dumps(
            {
                "pipeline_id": pipeline_id,
                "prompt_set": prompt_set,
                "tool_keys": tool_keys,
                "api_key": api_key,
                "llm_name": llm_name,
            }
        ),
        encoding="utf-8",
    )
    return {"path": str(out_file)}


def test_registry_route_lifecycle(monkeypatch, tmp_path):
    registry_path = tmp_path / "pipeline_registry.json"
    monkeypatch.setattr(front_apis, "PIPELINE_REGISTRY_PATH", str(registry_path))
    monkeypatch.setitem(front_apis.GRAPH_BUILD_FNCS, "routing", _fake_build_fn)

    client = TestClient(front_apis.app)

    create_resp = client.post(
        "/v1/pipelines",
        json={
            "graph_id": "routing",
            "pipeline_id": "xiaozhan",
            "prompt_set_id": "default",
            "tool_keys": ["weather"],
            "api_key": "sk-test",
            "llm_name": "qwen-plus",
            "enabled": True,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    create_data = create_resp.json()
    assert create_data["pipeline_id"] == "xiaozhan"
    assert create_data["graph_id"] == "routing"
    assert create_data["llm_name"] == "qwen-plus"
    assert create_data["reload_required"] is False

    list_resp = client.get("/v1/pipelines")
    assert list_resp.status_code == 200, list_resp.text
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["pipeline_id"] == "xiaozhan"
    assert items[0]["graph_id"] == "routing"
    assert items[0]["llm_name"] == "qwen-plus"
    assert items[0]["enabled"] is True

    disable_resp = client.delete("/v1/pipelines/xiaozhan")
    assert disable_resp.status_code == 200, disable_resp.text
    disable_data = disable_resp.json()
    assert disable_data["pipeline_id"] == "xiaozhan"
    assert disable_data["enabled"] is False

    list_after = client.get("/v1/pipelines")
    assert list_after.status_code == 200, list_after.text
    items_after = list_after.json()["items"]
    assert len(items_after) == 1
    assert items_after[0]["enabled"] is False

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    pipeline = registry["pipelines"]["xiaozhan"]
    assert pipeline["graph_id"] == "routing"
    assert pipeline["enabled"] is False


def test_registry_api_key_policy_lifecycle(monkeypatch, tmp_path):
    registry_path = tmp_path / "pipeline_registry.json"
    monkeypatch.setattr(front_apis, "PIPELINE_REGISTRY_PATH", str(registry_path))
    monkeypatch.setitem(front_apis.GRAPH_BUILD_FNCS, "routing", _fake_build_fn)

    client = TestClient(front_apis.app)

    create_resp = client.post(
        "/v1/pipelines",
        json={
            "graph_id": "routing",
            "pipeline_id": "blueberry",
            "prompt_set_id": "default",
            "tool_keys": [],
            "api_key": "sk-test",
            "llm_name": "qwen-plus",
            "enabled": True,
        },
    )
    assert create_resp.status_code == 200, create_resp.text

    upsert_resp = client.put(
        "/v1/pipelines/api-keys/sk-test-key",
        json={
            "default_pipeline_id": "blueberry",
            "allowed_pipeline_ids": ["blueberry"],
            "app_id": "blueberry",
        },
    )
    assert upsert_resp.status_code == 200, upsert_resp.text
    upsert_data = upsert_resp.json()
    assert upsert_data["api_key"] == "sk-test-key"
    assert upsert_data["default_pipeline_id"] == "blueberry"
    assert upsert_data["allowed_pipeline_ids"] == ["blueberry"]
    assert upsert_data["app_id"] == "blueberry"

    list_resp = client.get("/v1/pipelines/api-keys")
    assert list_resp.status_code == 200, list_resp.text
    list_data = list_resp.json()
    assert list_data["count"] == 1
    assert list_data["items"][0]["api_key"] == "sk-test-key"

    delete_resp = client.delete("/v1/pipelines/api-keys/sk-test-key")
    assert delete_resp.status_code == 200, delete_resp.text
    delete_data = delete_resp.json()
    assert delete_data["api_key"] == "sk-test-key"
    assert delete_data["status"] == "deleted"
    assert delete_data["reload_required"] is False
