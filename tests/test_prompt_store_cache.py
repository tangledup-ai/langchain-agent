from contextlib import contextmanager

from lang_agent.components import prompt_store
from lang_agent.components.redis_client import CacheClient


class _FakeCursor:
    def __init__(self, rows, call_counter):
        self._rows = rows
        self._call_counter = call_counter

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql, _params):
        self._call_counter["count"] += 1

    def fetchall(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self, rows, call_counter):
        self._rows = rows
        self._call_counter = call_counter

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self._rows, self._call_counter)


def test_db_prompt_store_uses_cache_and_invalidates(monkeypatch):
    cache = CacheClient(url=None, prefix="prompt-store-test")
    rows = [("sys_prompt", "hello"), ("tool_prompt", "use tool")]
    call_counter = {"count": 0}

    @contextmanager
    def _fake_db_connection():
        yield _FakeConnection(rows, call_counter)

    monkeypatch.setenv("CONN_STR", "postgresql://dummy:dummy@localhost/dummy")
    monkeypatch.setattr(prompt_store, "get_cache_client", lambda: cache)
    monkeypatch.setattr(prompt_store, "db_connection", _fake_db_connection)

    store = prompt_store.DBPromptStore("agent-a", prompt_set_id="default")

    assert store.get("sys_prompt") == "hello"
    assert call_counter["count"] == 1

    assert store.get_all()["tool_prompt"] == "use tool"
    assert call_counter["count"] == 1

    store.invalidate_cache()
    assert store.get("sys_prompt") == "hello"
    assert call_counter["count"] == 2
