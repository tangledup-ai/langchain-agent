import json
import os
from typing import Any, Dict, Optional

from loguru import logger

try:
    import redis
except ImportError:  # pragma: no cover - exercised when dependency is absent.
    redis = None


class CacheClient:
    """Redis-backed cache with an in-process fallback for local development/tests."""

    def __init__(self, url: Optional[str] = None, prefix: str = "lang-agent"):
        self.url = url or os.environ.get("REDIS_URL")
        self.prefix = prefix
        self._local: Dict[str, str] = {}
        self._client = None

        if self.url and redis is not None:
            try:
                self._client = redis.Redis.from_url(self.url, decode_responses=True)
            except Exception as exc:
                logger.warning("Failed to initialize Redis client: {}", exc)
                self._client = None

    def close(self) -> None:
        if self._client is None:
            return
        try:
            self._client.close()
        except Exception as exc:
            logger.warning("Failed to close Redis client cleanly: {}", exc)

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Optional[str]:
        full_key = self._key(key)
        if self._client is not None:
            return self._client.get(full_key)
        return self._local.get(full_key)

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        full_key = self._key(key)
        if self._client is not None:
            self._client.set(full_key, value, ex=ttl_seconds)
            return
        self._local[full_key] = value

    def delete(self, key: str) -> None:
        full_key = self._key(key)
        if self._client is not None:
            self._client.delete(full_key)
            return
        self._local.pop(full_key, None)

    def get_json(self, key: str) -> Optional[Any]:
        raw = self.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set_json(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        self.set(key, json.dumps(value), ttl_seconds=ttl_seconds)

    def get_int(self, key: str, default: int = 0) -> int:
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    def increment(self, key: str) -> int:
        full_key = self._key(key)
        if self._client is not None:
            return int(self._client.incr(full_key))

        current = int(self._local.get(full_key, "0"))
        current += 1
        self._local[full_key] = str(current)
        return current

    def prompt_cache_key(self, pipeline_id: str, prompt_set_id: Optional[str]) -> str:
        target = prompt_set_id or "active"
        return f"prompt-cache:{pipeline_id}:{target}"

    def prompt_version_key(self, pipeline_id: str, prompt_set_id: Optional[str]) -> str:
        target = prompt_set_id or "active"
        return f"prompt-version:{pipeline_id}:{target}"

    def get_prompt_version(self, pipeline_id: str, prompt_set_id: Optional[str]) -> int:
        return self.get_int(self.prompt_version_key(pipeline_id, prompt_set_id), default=0)

    def invalidate_prompt_cache(
        self, pipeline_id: str, prompt_set_id: Optional[str] = None
    ) -> int:
        self.delete(self.prompt_cache_key(pipeline_id, prompt_set_id))
        return self.increment(self.prompt_version_key(pipeline_id, prompt_set_id))

    def conversation_list_key(self, pipeline_id: str, limit: int) -> str:
        return f"conversation-list:{pipeline_id}:{limit}"

    def conversation_messages_key(self, pipeline_id: str, conversation_id: str) -> str:
        return f"conversation-messages:{pipeline_id}:{conversation_id}"


_CACHE_CLIENT: Optional[CacheClient] = None


def init_cache_client(url: Optional[str] = None) -> CacheClient:
    global _CACHE_CLIENT
    if _CACHE_CLIENT is None:
        _CACHE_CLIENT = CacheClient(url=url)
    return _CACHE_CLIENT


def get_cache_client() -> CacheClient:
    global _CACHE_CLIENT
    if _CACHE_CLIENT is None:
        _CACHE_CLIENT = init_cache_client()
    return _CACHE_CLIENT


def close_cache_client() -> None:
    global _CACHE_CLIENT
    if _CACHE_CLIENT is not None:
        _CACHE_CLIENT.close()
        _CACHE_CLIENT = None
