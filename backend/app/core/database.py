from collections.abc import AsyncGenerator, Generator
from pathlib import Path

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


# Sync Engine
DATABASE_URL, ASYNC_DATABASE_URL = _derive_sync_and_async_urls(RAW_DATABASE_URL)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    connect_args={"check_same_thread": False}
    if ASYNC_DATABASE_URL.startswith("sqlite")
    else {},
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
