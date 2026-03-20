from contextlib import contextmanager
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from lang_agent.components import conv_store


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        query = " ".join(sql.split()).lower()
        if "pg_advisory_xact_lock" in query:
            self._result = [(None,)]
            return
        if "select coalesce(max(sequence_number), 0)" in query:
            conversation_id = params[0]
            current = 0
            for row in self._rows:
                if row["conversation_id"] == conversation_id:
                    current = max(current, row["sequence_number"])
            self._result = [(current,)]
            return
        raise AssertionError(f"Unsupported SQL in test fake: {sql}")

    def executemany(self, _sql, values):
        for value in values:
            self._rows.append(
                {
                    "conversation_id": value[0],
                    "pipeline_id": value[1],
                    "message_type": value[2],
                    "content": value[3],
                    "sequence_number": value[4],
                }
            )

    def fetchone(self):
        return self._result[0]


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, row_factory=None):
        return _FakeCursor(self._rows)

    def commit(self):
        self.committed = True


def test_record_message_list_appends_only_new_messages(monkeypatch):
    rows = [
        {
            "conversation_id": "conv-1",
            "pipeline_id": "agent-a",
            "message_type": "human",
            "content": "hello",
            "sequence_number": 1,
        }
    ]
    cache_events = []
    bus_events = []

    @contextmanager
    def _fake_db_connection():
        yield _FakeConnection(rows)

    services = SimpleNamespace(
        cache=SimpleNamespace(
            delete=lambda key: cache_events.append(("delete", key)),
            conversation_messages_key=lambda pipeline_id, conversation_id: f"{pipeline_id}:{conversation_id}",
            conversation_list_key=lambda pipeline_id, limit: f"{pipeline_id}:{limit}",
        ),
        message_bus=SimpleNamespace(
            publish=lambda event_type, payload: bus_events.append((event_type, payload))
        ),
    )

    monkeypatch.setattr(conv_store, "db_connection", _fake_db_connection)
    monkeypatch.setattr(conv_store, "get_runtime_services", lambda: services)
    monkeypatch.setenv("CONN_STR", "postgresql://dummy:dummy@localhost/dummy")

    store = conv_store.ConversationStore()
    count = store.record_message_list(
        "conv-1",
        [HumanMessage("hello"), AIMessage("hi there")],
        pipeline_id="agent-a",
    )

    assert count == 2
    assert rows[-1]["sequence_number"] == 2
    assert rows[-1]["content"] == "hi there"
    assert bus_events[0][0] == "conversation.updated"
    assert cache_events
