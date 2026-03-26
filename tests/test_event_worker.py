from types import SimpleNamespace

from lang_agent.components.event_worker import handle_event


def _fake_services():
    events = []

    class _Cache:
        def delete(self, key):
            events.append(("delete", key))

        def invalidate_prompt_cache(self, pipeline_id, prompt_set_id):
            events.append(("invalidate_prompt_cache", pipeline_id, prompt_set_id))

        def conversation_messages_key(self, pipeline_id, conversation_id):
            return f"conversation-messages:{pipeline_id}:{conversation_id}"

        def conversation_list_key(self, pipeline_id, limit):
            return f"conversation-list:{pipeline_id}:{limit}"

    return SimpleNamespace(cache=_Cache()), events


def test_handle_prompt_set_updated_invalidates_prompt_cache():
    services, events = _fake_services()
    handle_event(
        {
            "event_type": "prompt_set.updated",
            "payload": {"pipeline_id": "agent-a", "prompt_set_id": "default"},
        },
        services=services,
    )

    assert ("invalidate_prompt_cache", "agent-a", "default") in events
    assert ("invalidate_prompt_cache", "agent-a", None) in events


def test_handle_conversation_updated_invalidates_conversation_cache():
    services, events = _fake_services()
    handle_event(
        {
            "event_type": "conversation.updated",
            "payload": {"pipeline_id": "agent-a", "conversation_id": "conv-1"},
        },
        services=services,
    )

    assert ("delete", "conversation-messages:agent-a:conv-1") in events
    assert ("delete", "conversation-list:agent-a:50") in events
    assert ("delete", "conversation-list:agent-a:100") in events
    assert ("delete", "conversation-list:agent-a:500") in events


def test_handle_unknown_event_is_noop():
    services, events = _fake_services()
    handle_event({"event_type": "unknown.event", "payload": {}}, services=services)
    assert events == []
