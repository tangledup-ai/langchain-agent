from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional

from lang_agent.components.db_pool import close_db_pool, init_db_pool
from lang_agent.components.message_bus import (
    MessageBus,
    close_message_bus,
    get_message_bus,
    init_message_bus,
)
from lang_agent.components.redis_client import (
    CacheClient,
    close_cache_client,
    get_cache_client,
    init_cache_client,
)


@dataclass
class RuntimeServices:
    db_pool: Optional[object]
    cache: CacheClient
    message_bus: MessageBus


_RUNTIME_SERVICES: Optional[RuntimeServices] = None


def init_runtime_services() -> RuntimeServices:
    global _RUNTIME_SERVICES
    if _RUNTIME_SERVICES is None:
        _RUNTIME_SERVICES = RuntimeServices(
            db_pool=init_db_pool(),
            cache=init_cache_client(),
            message_bus=init_message_bus(),
        )
    return _RUNTIME_SERVICES


def get_runtime_services() -> RuntimeServices:
    global _RUNTIME_SERVICES
    if _RUNTIME_SERVICES is None:
        _RUNTIME_SERVICES = RuntimeServices(
            db_pool=init_db_pool(),
            cache=get_cache_client(),
            message_bus=get_message_bus(),
        )
    return _RUNTIME_SERVICES


def close_runtime_services() -> None:
    global _RUNTIME_SERVICES
    close_message_bus()
    close_cache_client()
    close_db_pool()
    _RUNTIME_SERVICES = None


@asynccontextmanager
async def runtime_services_lifespan(_app):
    init_runtime_services()
    try:
        yield
    finally:
        close_runtime_services()
