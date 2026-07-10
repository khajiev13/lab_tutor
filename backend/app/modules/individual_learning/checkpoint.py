from __future__ import annotations

from threading import RLock

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.settings import settings

_LOCK = RLock()
_POOL: ConnectionPool | None = None
_CHECKPOINTER: PostgresSaver | None = None


def _get_checkpoint_db_url() -> str:
    url = settings.database_url
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url.removeprefix(prefix)
    return url


def get_individual_learning_checkpointer() -> PostgresSaver:
    """Lazily build the shared synchronous production checkpointer."""

    global _CHECKPOINTER, _POOL  # noqa: PLW0603
    with _LOCK:
        if _CHECKPOINTER is not None:
            return _CHECKPOINTER
        pool = ConnectionPool(
            conninfo=_get_checkpoint_db_url(),
            min_size=1,
            max_size=3,
            max_idle=120,
            check=ConnectionPool.check_connection,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            open=False,
        )
        try:
            pool.open(wait=True)
            checkpointer = PostgresSaver(conn=pool)
            checkpointer.setup()
        except BaseException:
            pool.close()
            raise
        _POOL = pool
        _CHECKPOINTER = checkpointer
        return checkpointer


def close_individual_learning_checkpointer() -> None:
    """Close only the pool owned by this module and reset lazy state."""

    global _CHECKPOINTER, _POOL  # noqa: PLW0603
    with _LOCK:
        pool = _POOL
        _CHECKPOINTER = None
        _POOL = None
    if pool is not None:
        pool.close()
