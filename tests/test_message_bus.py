from types import SimpleNamespace

from lang_agent.components import message_bus


def test_publish_is_noop_when_rabbitmq_unreachable(monkeypatch):
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    monkeypatch.setattr(message_bus, "_check_rabbitmq_alive", lambda url: False)

    bus = message_bus.MessageBus(url=None)

    assert bus.publish("conversation.updated", {"conversation_id": "conv-1"}) is False


def test_auto_resolves_url_in_docker(monkeypatch):
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    monkeypatch.setattr(message_bus, "_is_running_in_docker", lambda: True)

    url = message_bus._resolve_rabbitmq_url()
    assert "rabbitmq" in url


def test_auto_resolves_url_on_localhost(monkeypatch):
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    monkeypatch.setattr(message_bus, "_is_running_in_docker", lambda: False)

    url = message_bus._resolve_rabbitmq_url()
    assert "localhost" in url


def test_publish_uses_configured_exchange(monkeypatch):
    events = []

    class _FakeChannel:
        def exchange_declare(self, **kwargs):
            events.append(("exchange_declare", kwargs))

        def basic_publish(self, **kwargs):
            events.append(("basic_publish", kwargs))

    class _FakeConnection:
        is_open = True

        def __init__(self, _params):
            self.channel_obj = _FakeChannel()

        def channel(self):
            return self.channel_obj

        def close(self):
            events.append(("close", {}))

    fake_pika = SimpleNamespace(
        URLParameters=lambda url: {"url": url},
        BlockingConnection=_FakeConnection,
        BasicProperties=lambda **kwargs: kwargs,
    )

    monkeypatch.setattr(message_bus, "pika", fake_pika)
    monkeypatch.setattr(message_bus, "_check_rabbitmq_alive", lambda url: True)
    bus = message_bus.MessageBus(
        url="amqp://guest:guest@localhost:5672/",
        exchange="lang-agent.test",
    )

    published = bus.publish(
        "conversation.updated",
        {"conversation_id": "conv-1", "message_count": 2},
    )

    assert published is True
    assert events[0][0] == "exchange_declare"
    assert events[1][0] == "basic_publish"
    assert events[1][1]["exchange"] == "lang-agent.test"
    assert events[1][1]["routing_key"] == "conversation.updated"
