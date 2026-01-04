import ssl
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import settings


class Base(DeclarativeBase):
    """Base class for ORM models."""


def _ensure_sqlite_path(url: str) -> None:
    if url.startswith("sqlite"):
        # Handle both sqlite:/// and sqlite+aiosqlite:///
        clean_url = url.replace("sqlite+aiosqlite:///", "sqlite:///").replace(
            "sqlite:///", ""
        )
        db_path = Path(clean_url)
        db_path.parent.mkdir(parents=True, exist_ok=True)


RAW_DATABASE_URL = settings.database_url
_ensure_sqlite_path(RAW_DATABASE_URL)


def _derive_sync_and_async_urls(url: str) -> tuple[str, str]:
    """Derive sync + async SQLAlchemy URLs from a single configured URL.

    - SQLite: keeps current behavior (sync sqlite:///..., async sqlite+aiosqlite:///...)
    - Postgres: converts to sync psycopg + async asyncpg drivers.
    """
    if url.startswith("sqlite"):
        sync_url = url.replace("sqlite+aiosqlite:///", "sqlite:///")
        async_url = sync_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        return sync_url, async_url

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

    # Fallback: assume the URL is usable for both engines.
    return url, url


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

# When using pooled connections against managed Postgres (e.g., Azure), the server
# may close idle SSL sessions. SQLAlchemy can otherwise keep a stale DBAPI
# connection in the pool, leading to:
#   psycopg.OperationalError: SSL error: unexpected eof while reading
# `pool_pre_ping` proactively checks the connection before use.
POOL_PRE_PING = True
POOL_RECYCLE_SECONDS = 1800 if IS_POSTGRES else -1

POSTGRES_CONNECT_ARGS = (
    {
        "connect_timeout": 10,
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
    connect_args={"check_same_thread": False} if IS_SQLITE else POSTGRES_CONNECT_ARGS,
    pool_pre_ping=POOL_PRE_PING,
    pool_recycle=POOL_RECYCLE_SECONDS,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    connect_args={"check_same_thread": False}
    if ASYNC_DATABASE_URL.startswith("sqlite")
    else ASYNC_CONNECT_ARGS,
    pool_pre_ping=POOL_PRE_PING,
    pool_recycle=POOL_RECYCLE_SECONDS,
)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
