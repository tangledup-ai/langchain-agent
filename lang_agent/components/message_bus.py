import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from loguru import logger

try:
    import pika
except ImportError:  # pragma: no cover - exercised when dependency is absent.
    pika = None


def _is_running_in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _resolve_rabbitmq_url() -> Optional[str]:
    """Return an explicit RABBITMQ_URL or auto-detect based on runtime."""
    if explicit := os.environ.get("RABBITMQ_URL"):
        return explicit
    host = "rabbitmq" if _is_running_in_docker() else "localhost"
    user = os.environ.get("RABBITMQ_USER", "guest")
    password = os.environ.get("RABBITMQ_PASSWORD", "guest")
    port = os.environ.get("RABBITMQ_PORT", "5672")
    return f"amqp://{user}:{password}@{host}:{port}/"


def _check_rabbitmq_alive(url: str, timeout: float = 2.0) -> bool:
    """Quick probe to see if RabbitMQ is reachable."""
    if pika is None:
        return False
    try:
        params = pika.URLParameters(url)
        params.socket_timeout = timeout
        params.connection_attempts = 1
        conn = pika.BlockingConnection(params)
        conn.close()
        return True
    except Exception:
        return False


class MessageBus:
    """RabbitMQ publisher/consumer wrapper with a no-op fallback."""

    def __init__(
        self,
        url: Optional[str] = None,
        exchange: Optional[str] = None,
    ):
        self.url = url or _resolve_rabbitmq_url()
        self.exchange = exchange or os.environ.get(
            "RABBITMQ_EXCHANGE", "lang-agent.events"
        )
        self._enabled = bool(self.url and _check_rabbitmq_alive(self.url))

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _open_channel(self):
        if not self.enabled:
            return None, None

        params = pika.URLParameters(self.url)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.exchange_declare(
            exchange=self.exchange, exchange_type="topic", durable=True
        )
        return connection, channel

    def publish(
        self,
        event_type: str,
        payload: Dict[str, Any],
        routing_key: Optional[str] = None,
    ) -> bool:
        if not self.enabled:
            logger.debug(
                "Skipping message bus publish because RabbitMQ is not configured"
            )
            return False

        body = json.dumps({"event_type": event_type, "payload": payload})
        connection, channel = self._open_channel()
        try:
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key or event_type,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                ),
            )
            return True
        finally:
            if connection is not None:
                connection.close()

    def consume(
        self,
        queue_name: str,
        routing_keys: Iterable[str],
        handler: Callable[[Dict[str, Any]], None],
        prefetch_count: int = 10,
    ) -> None:
        if not self.enabled:
            logger.info(
                "Message bus consumer not started because RabbitMQ is not configured"
            )
            return

        connection, channel = self._open_channel()
        try:
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=prefetch_count)
            for routing_key in routing_keys:
                channel.queue_bind(
                    exchange=self.exchange,
                    queue=queue_name,
                    routing_key=routing_key,
                )

            def _on_message(ch, method, _properties, body):
                payload = json.loads(body.decode("utf-8"))
                try:
                    handler(payload)
                except Exception as exc:
                    logger.exception(
                        "Message handler failed for {}: {}", method.routing_key, exc
                    )
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    return
                ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue=queue_name, on_message_callback=_on_message)
            channel.start_consuming()
        finally:
            if connection is not None and connection.is_open:
                connection.close()


_MESSAGE_BUS: Optional[MessageBus] = None


def init_message_bus(url: Optional[str] = None) -> MessageBus:
    global _MESSAGE_BUS
    if _MESSAGE_BUS is None:
        _MESSAGE_BUS = MessageBus(url=url)
    return _MESSAGE_BUS


def get_message_bus() -> MessageBus:
    global _MESSAGE_BUS
    if _MESSAGE_BUS is None:
        _MESSAGE_BUS = init_message_bus()
    return _MESSAGE_BUS


def close_message_bus() -> None:
    global _MESSAGE_BUS
    _MESSAGE_BUS = None
