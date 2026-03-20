import os
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from loguru import logger

try:
    from psycopg_pool import ConnectionPool as PsycopgConnectionPool
except ImportError:  # pragma: no cover - exercised when dependency is absent.
    PsycopgConnectionPool = None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for {}: {!r}; using {}", name, raw, default)
        return default


class DatabasePool:
    """Thin wrapper around psycopg_pool with a direct-connect fallback."""

    def __init__(
        self,
        conn_str: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        timeout: Optional[int] = None,
        max_idle: Optional[int] = None,
    ):
        self.conn_str = conn_str or os.environ.get("CONN_STR")
        if not self.conn_str:
            raise ValueError("CONN_STR is not set")

        self.min_size = min_size if min_size is not None else _env_int("DB_POOL_MIN_SIZE", 1)
        self.max_size = max_size if max_size is not None else _env_int("DB_POOL_MAX_SIZE", 10)
        self.timeout = timeout if timeout is not None else _env_int("DB_POOL_TIMEOUT", 30)
        self.max_idle = max_idle if max_idle is not None else _env_int("DB_POOL_MAX_IDLE", 300)

        self._pool = None
        if PsycopgConnectionPool is not None:
            self._pool = PsycopgConnectionPool(
                conninfo=self.conn_str,
                min_size=self.min_size,
                max_size=self.max_size,
                timeout=self.timeout,
                max_idle=self.max_idle,
                open=False,
            )

    def open(self) -> None:
        if self._pool is None:
            return
        if getattr(self._pool, "closed", False):
            self._pool.open()

    def close(self) -> None:
        if self._pool is None:
            return
        if not getattr(self._pool, "closed", False):
            self._pool.close()

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        if self._pool is None:
            with psycopg.connect(self.conn_str) as conn:
                yield conn
            return

        self.open()
        with self._pool.connection() as conn:
            yield conn


_DB_POOL: Optional[DatabasePool] = None


def init_db_pool(conn_str: Optional[str] = None) -> Optional[DatabasePool]:
    global _DB_POOL
    if _DB_POOL is not None:
        return _DB_POOL

    resolved = conn_str or os.environ.get("CONN_STR")
    if not resolved:
        logger.info("Skipping DB pool initialization because CONN_STR is not set")
        return None

    _DB_POOL = DatabasePool(conn_str=resolved)
    if os.environ.get("DB_POOL_OPEN_ON_STARTUP", "").lower() in {"1", "true", "yes"}:
        _DB_POOL.open()
    return _DB_POOL


def get_db_pool(required: bool = True) -> Optional[DatabasePool]:
    global _DB_POOL
    if _DB_POOL is None:
        _DB_POOL = init_db_pool()

    if _DB_POOL is None and required:
        raise ValueError("CONN_STR is not set")
    return _DB_POOL


def close_db_pool() -> None:
    global _DB_POOL
    if _DB_POOL is not None:
        _DB_POOL.close()
        _DB_POOL = None


@contextmanager
def db_connection(required: bool = True) -> Iterator[psycopg.Connection]:
    pool = get_db_pool(required=required)
    if pool is None:
        if required:
            raise ValueError("CONN_STR is not set")
        yield None
        return

    with pool.connection() as conn:
        yield conn
