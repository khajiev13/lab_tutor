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


DATABASE_URL = settings.database_url
_ensure_sqlite_path(DATABASE_URL)

# Sync Engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async Engine
ASYNC_DATABASE_URL = (
    DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
    if DATABASE_URL.startswith("sqlite")
    else DATABASE_URL
)

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
