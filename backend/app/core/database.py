import contextlib
import logging
import ssl
from collections.abc import AsyncGenerator, Generator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import settings


class Base(DeclarativeBase):
    """Base class for ORM models."""


RAW_DATABASE_URL = settings.database_url


def _derive_sync_and_async_urls(url: str) -> tuple[str, str]:
    """Derive sync + async SQLAlchemy URLs from a configured Postgres URL."""

    # Accept common Postgres URL prefixes and normalize them.
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")

    if url.startswith("postgresql://"):
        sync_url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
        async_url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
        return sync_url, async_url

    if url.startswith("postgresql+psycopg://"):
        return url, url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1), url

    raise ValueError(
        "LAB_TUTOR_DATABASE_URL must be a PostgreSQL URL "
        "(postgresql://, postgresql+psycopg://, or postgresql+asyncpg://)."
    )


def _asyncpg_connect_args_from_url(async_url: str) -> tuple[str, dict]:
    """asyncpg doesn't understand libpq-style `sslmode=...` query params.

    Azure Postgres commonly provides URLs like:
      postgresql://.../db?sslmode=require

    SQLAlchemy's asyncpg dialect passes unknown query params as keyword args, so `sslmode`
    causes a runtime TypeError. We:
    - remove `sslmode` from the async URL
    - translate it into `connect_args={"ssl": ...}` for asyncpg.
    """
    if not async_url.startswith("postgresql+asyncpg://"):
        return async_url, {}

    parts = urlsplit(async_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))

    sslmode = (query.pop("sslmode", "") or "").lower()
    connect_args: dict = {}

    # asyncpg uses the stdlib `ssl` module, not libpq.
    # libpq semantics:
    # - require: encrypt, no certificate verification
    # - verify-ca: verify certificate chain, no hostname verification
    # - verify-full: verify chain + hostname
    # Azure Postgres commonly provides `sslmode=require`.
    if sslmode in {"require", "prefer"}:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx
    elif sslmode == "verify-ca":
        ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        ctx.check_hostname = False
        connect_args["ssl"] = ctx
    elif sslmode == "verify-full":
        ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        ctx.check_hostname = True
        connect_args["ssl"] = ctx
    elif sslmode == "disable":
        connect_args["ssl"] = False

    new_query = urlencode(query, doseq=True)
    cleaned_url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )
    return cleaned_url, connect_args


# Sync Engine
DATABASE_URL, ASYNC_DATABASE_URL = _derive_sync_and_async_urls(RAW_DATABASE_URL)
ASYNC_DATABASE_URL, ASYNC_CONNECT_ARGS = _asyncpg_connect_args_from_url(
    ASYNC_DATABASE_URL
)

IS_SQLITE = DATABASE_URL.startswith("sqlite")
IS_POSTGRES = DATABASE_URL.startswith("postgresql")

# Azure Postgres closes idle SSL connections after ~90s.
# Recycle connections before that to avoid stale-connection errors
# (psycopg.OperationalError: SSL error: unexpected eof while reading).
# pool_pre_ping adds a lightweight "SELECT 1" probe before reuse; combined
# with a short recycle it eliminates cold-reconnect latency on requests.
POOL_PRE_PING = True
POOL_RECYCLE_SECONDS = 60 if IS_POSTGRES else -1
ASYNC_POOL_RECYCLE_SECONDS = 60 if IS_POSTGRES else -1

# Azure Postgres allows ~50 connections on Basic tier.  We need headroom for
# the ThreadPoolExecutor embedding workers (up to 10 concurrent sessions) plus
# FastAPI request handlers and SSE polling.
POOL_SIZE = 10
MAX_OVERFLOW = 5

POSTGRES_CONNECT_ARGS = (
    {
        "connect_timeout": 30,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
    if IS_POSTGRES
    else {}
)

engine = create_engine(
    DATABASE_URL,
    connect_args=POSTGRES_CONNECT_ARGS,
    pool_pre_ping=POOL_PRE_PING,
    pool_recycle=POOL_RECYCLE_SECONDS,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    connect_args=ASYNC_CONNECT_ARGS,
    pool_pre_ping=POOL_PRE_PING,
    pool_recycle=ASYNC_POOL_RECYCLE_SECONDS,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


_db_logger = logging.getLogger(__name__)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        with contextlib.suppress(Exception):
            db.rollback()
        raise
    finally:
        try:
            db.close()
        except Exception:
            _db_logger.debug(
                "Suppressed error closing DB session (stale connection)", exc_info=True
            )


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        with contextlib.suppress(Exception):
            await session.rollback()
        raise
    finally:
        try:
            await session.close()
        except Exception:
            _db_logger.debug(
                "Suppressed error closing async DB session (stale connection)",
                exc_info=True,
            )
