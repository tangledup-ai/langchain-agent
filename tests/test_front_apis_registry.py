import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
import importlib
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient


os.environ.setdefault("CONN_STR", "postgresql://dummy:dummy@localhost/dummy")

try:
    front_apis = importlib.import_module("lang_agent.fastapi_server.front_apis")
except ModuleNotFoundError:
    front_apis = importlib.import_module("fastapi_server.front_apis")


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


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self._result = []
        self._last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self._last_sql = sql
        query = " ".join(sql.split()).lower()
        params = params or ()

        if "group by conversation_id, pipeline_id" in query:
            pipeline_id = params[0]
            limit = int(params[1])
            grouped = {}
            for row in self._rows:
                if row["pipeline_id"] != pipeline_id:
                    continue
                conv_id = row["conversation_id"]
                if conv_id not in grouped:
                    grouped[conv_id] = {
                        "conversation_id": conv_id,
                        "pipeline_id": row["pipeline_id"],
                        "message_count": 0,
                        "last_updated": row["created_at"],
                    }
                grouped[conv_id]["message_count"] += 1
                if row["created_at"] > grouped[conv_id]["last_updated"]:
                    grouped[conv_id]["last_updated"] = row["created_at"]
            values = sorted(grouped.values(), key=lambda x: x["last_updated"], reverse=True)
            self._result = values[:limit]
            return

        if "select 1 from messages" in query:
            pipeline_id, conversation_id = params
            found = any(
                row["pipeline_id"] == pipeline_id
                and row["conversation_id"] == conversation_id
                for row in self._rows
            )
            self._result = [{"exists": 1}] if found else []
            return

        if "order by sequence_number asc" in query:
            pipeline_id, conversation_id = params
            self._result = sorted(
                [
                    {
                        "message_type": row["message_type"],
                        "content": row["content"],
                        "sequence_number": row["sequence_number"],
                        "created_at": row["created_at"],
                    }
                    for row in self._rows
                    if row["pipeline_id"] == pipeline_id
                    and row["conversation_id"] == conversation_id
                ],
                key=lambda x: x["sequence_number"],
            )
            return

        raise AssertionError(f"Unsupported SQL in test fake: {self._last_sql}")

    def fetchall(self):
        return self._result

    def fetchone(self):
        if not self._result:
            return None
        return self._result[0]


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, row_factory=None):
        return _FakeCursor(self._rows)


@contextmanager
def _fake_db_connection(rows):
    yield _FakeConnection(rows)


def _fake_services():
    cache_data = {}

    class _Cache:
        def get_json(self, key):
            return cache_data.get(key)

        def set_json(self, key, value, ttl_seconds=None):
            cache_data[key] = value

        def delete(self, key):
            cache_data.pop(key, None)

        def conversation_list_key(self, pipeline_id, limit):
            return f"conversation-list:{pipeline_id}:{limit}"

        def conversation_messages_key(self, pipeline_id, conversation_id):
            return f"conversation-messages:{pipeline_id}:{conversation_id}"

    return SimpleNamespace(
        cache=_Cache(),
        message_bus=SimpleNamespace(publish=lambda *_args, **_kwargs: False),
    )


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


def test_pipeline_conversation_routes(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        {
            "conversation_id": "agent-a:conv-1",
            "pipeline_id": "agent-a",
            "message_type": "human",
            "content": "hello",
            "sequence_number": 1,
            "created_at": now - timedelta(seconds=30),
        },
        {
            "conversation_id": "agent-a:conv-1",
            "pipeline_id": "agent-a",
            "message_type": "ai",
            "content": "hi there",
            "sequence_number": 2,
            "created_at": now - timedelta(seconds=20),
        },
        {
            "conversation_id": "agent-a:conv-2",
            "pipeline_id": "agent-a",
            "message_type": "human",
            "content": "second thread",
            "sequence_number": 1,
            "created_at": now - timedelta(seconds=10),
        },
        {
            "conversation_id": "agent-b:conv-9",
            "pipeline_id": "agent-b",
            "message_type": "human",
            "content": "other pipeline",
            "sequence_number": 1,
            "created_at": now - timedelta(seconds=5),
        },
    ]

    monkeypatch.setenv("CONN_STR", "postgresql://dummy:dummy@localhost/dummy")
    monkeypatch.setattr(front_apis, "get_runtime_services", _fake_services)
    monkeypatch.setattr(
        front_apis,
        "db_connection",
        lambda: _fake_db_connection(rows),
    )

    client = TestClient(front_apis.app)

    list_resp = client.get("/v1/pipelines/agent-a/conversations")
    assert list_resp.status_code == 200, list_resp.text
    list_data = list_resp.json()
    assert list_data["pipeline_id"] == "agent-a"
    assert list_data["count"] == 2
    assert [item["conversation_id"] for item in list_data["items"]] == [
        "agent-a:conv-2",
        "agent-a:conv-1",
    ]
    assert all(item["pipeline_id"] == "agent-a" for item in list_data["items"])

    msg_resp = client.get("/v1/pipelines/agent-a/conversations/agent-a:conv-1/messages")
    assert msg_resp.status_code == 200, msg_resp.text
    msg_data = msg_resp.json()
    assert msg_data["pipeline_id"] == "agent-a"
    assert msg_data["conversation_id"] == "agent-a:conv-1"
    assert msg_data["count"] == 2
    assert [item["message_type"] for item in msg_data["items"]] == ["human", "ai"]
    assert [item["sequence_number"] for item in msg_data["items"]] == [1, 2]


def test_pipeline_conversation_messages_404(monkeypatch):
    rows = [
        {
            "conversation_id": "agent-b:conv-9",
            "pipeline_id": "agent-b",
            "message_type": "human",
            "content": "other pipeline",
            "sequence_number": 1,
            "created_at": datetime.now(timezone.utc),
        },
    ]
    monkeypatch.setenv("CONN_STR", "postgresql://dummy:dummy@localhost/dummy")
    monkeypatch.setattr(front_apis, "get_runtime_services", _fake_services)
    monkeypatch.setattr(
        front_apis,
        "db_connection",
        lambda: _fake_db_connection(rows),
    )

    client = TestClient(front_apis.app)
    resp = client.get("/v1/pipelines/agent-a/conversations/agent-b:conv-9/messages")
    assert resp.status_code == 404, resp.text
    assert "not found for pipeline 'agent-a'" in resp.json()["detail"]


def test_runtime_auth_info_prefers_registry_then_env(monkeypatch, tmp_path):
    registry_path = tmp_path / "pipeline_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "pipelines": {},
                "api_keys": {
                    "sk-from-registry": {"default_pipeline_id": "blueberry"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(front_apis, "PIPELINE_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("FAST_AUTH_KEYS", "sk-from-env,other")

    client = TestClient(front_apis.app)
    resp = client.get("/v1/runtime-auth")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["fast_api_key"] == "sk-from-registry"
    assert data["source"] == "pipeline_registry"
