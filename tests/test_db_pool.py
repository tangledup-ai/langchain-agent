from contextlib import contextmanager

from lang_agent.components import db_pool


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *_args, **_kwargs):
        return None


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor()


def test_init_db_pool_returns_none_when_conn_str_missing(monkeypatch):
    monkeypatch.delenv("CONN_STR", raising=False)
    db_pool.close_db_pool()

    assert db_pool.init_db_pool() is None
    assert db_pool.get_db_pool(required=False) is None


def test_db_connection_falls_back_to_direct_connect(monkeypatch):
    fake_conn = _FakeConnection()

    monkeypatch.setenv("CONN_STR", "postgresql://dummy:dummy@localhost/dummy")
    monkeypatch.setattr(db_pool, "PsycopgConnectionPool", None)
    monkeypatch.setattr(db_pool.psycopg, "connect", lambda _conn_str: fake_conn)
    db_pool.close_db_pool()

    with db_pool.db_connection() as conn:
        assert conn is fake_conn

    db_pool.close_db_pool()
