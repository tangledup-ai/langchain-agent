from typing import Any, Dict, Optional

from loguru import logger

from lang_agent.components.message_bus import get_message_bus
from lang_agent.components.runtime_services import get_runtime_services


def handle_event(event: Dict[str, Any], services=None) -> None:
    """
    Handle secondary event-bus tasks.

    This worker intentionally performs idempotent, cache-oriented side effects
    so retries are safe.
    """
    services = services or get_runtime_services()
    event_type = event.get("event_type")
    payload = event.get("payload", {}) or {}

    if event_type == "pipeline_registry.changed":
        services.cache.delete("pipeline-registry")
        return

    if event_type == "prompt_set.updated":
        pipeline_id = payload.get("pipeline_id")
        prompt_set_id = payload.get("prompt_set_id")
        if pipeline_id:
            services.cache.invalidate_prompt_cache(pipeline_id, prompt_set_id)
            services.cache.invalidate_prompt_cache(pipeline_id, None)
        return

    if event_type == "conversation.updated":
        pipeline_id = payload.get("pipeline_id")
        conversation_id = payload.get("conversation_id")
        if pipeline_id and conversation_id:
            services.cache.delete(
                services.cache.conversation_messages_key(
                    pipeline_id=pipeline_id,
                    conversation_id=conversation_id,
                )
            )
            for limit in (50, 100, 500):
                services.cache.delete(
                    services.cache.conversation_list_key(
                        pipeline_id=pipeline_id, limit=limit
                    )
                )
        return

    logger.debug("Ignoring unsupported event type: {}", event_type)


def run_event_worker(
    queue_name: str = "lang-agent.events.worker",
    routing_keys: Optional[list[str]] = None,
) -> None:
    keys = routing_keys or [
        "pipeline_registry.changed",
        "prompt_set.updated",
        "conversation.updated",
    ]
    bus = get_message_bus()
    bus.consume(queue_name=queue_name, routing_keys=keys, handler=handle_event)
