# ruff: noqa: E402

import asyncio
import getpass
import os


def _default_test_database_url() -> str:
    configured_url = os.getenv("LAB_TUTOR_TEST_DATABASE_URL")
    if configured_url:
        return configured_url

    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
        return "postgresql://postgres:postgres@localhost:5432/lab_tutor_test"

    return f"postgresql://{getpass.getuser()}@localhost:5432/lab_tutor_test"


# Point tests at a local/CI PostgreSQL instance BEFORE importing app modules.
# CI provides this via a PostgreSQL service container; locally you can override it.
os.environ.setdefault(
    "LAB_TUTOR_DATABASE_URL",
    _default_test_database_url(),
)
# Ensure optional external services don't run in tests.
os.environ.setdefault("LAB_TUTOR_NEO4J_URI", "")
os.environ.setdefault("LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING", "")

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import app.modules.cognitive_diagnosis.service as _cd_service_module
from app.core.database import (
    ASYNC_CONNECT_ARGS,
    ASYNC_DATABASE_URL,
    DATABASE_URL,
    Base,
    get_async_db,
    get_db,
)
from app.core.database import (
    async_engine as app_async_engine,
)
from app.core.database import (
    engine as app_engine,
)
from app.core.neo4j import get_neo4j_driver
from app.modules.auth.models import User, UserRole
from app.providers.storage import BlobService
from main import app

# ---------------------------------------------------------------------------
# Stub LLM chains for ALL tests so exercise-generation endpoints return fast.
# Without this, every test that hits /exercise or /simulate-skill waits for
# an 8-second network timeout per LLM call, making the full suite very slow.
# ---------------------------------------------------------------------------
_STUB_EXERCISE = {
    "problem": "What is 2 + 2?",
    "format": "multiple_choice",
    "options": ["1", "2", "3", "4"],
    "correct_answer": "4",
    "solution_steps": ["Add 2 and 2"],
    "hints": ["Think about counting"],
    "concepts_tested": ["arithmetic"],
    "estimated_time_seconds": 30,
    "difficulty_generated": 0.1,
}
_STUB_EVAL = {"score": 0.9, "feedback": "Good exercise."}


def _stub_llm_chain():
    def chain(_inputs: dict) -> dict:
        return _STUB_EXERCISE.copy()

    return chain


def _stub_eval_chain():
    def chain(_inputs: dict) -> dict:
        return _STUB_EVAL.copy()

    return chain


_cd_service_module._build_llm_chain = _stub_llm_chain  # type: ignore[attr-defined]
_cd_service_module._build_eval_chain = _stub_eval_chain  # type: ignore[attr-defined]

# Re-use the URLs the app already derived from LAB_TUTOR_DATABASE_URL so
# the test engines connect with the same credentials (works on CI with
# postgres:postgres and locally with the OS user).
SQLALCHEMY_DATABASE_URL = DATABASE_URL
ASYNC_SQLALCHEMY_DATABASE_URL = ASYNC_DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    poolclass=NullPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# NullPool prevents asyncpg connection-pool conflicts with TestClient's
# internal event loop ("another operation is in progress" errors).
async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    connect_args=ASYNC_CONNECT_ARGS,
    poolclass=NullPool,
)
AsyncTestingSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture(scope="function")
def db_session():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db() -> Generator:
        yield db_session

    async def override_get_async_db() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncTestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    asyncio.run(async_engine.dispose())
    # Dispose all pooled connections so the next test's drop_all() is not
    # blocked by connections the lifespan left open in the app engine pools.
    app_engine.dispose()
    # Also dispose the async engine's underlying pool (sync call on the
    # wrapped sync_engine is sufficient; no await needed here).
    app_async_engine.sync_engine.dispose()


@pytest.fixture
def mock_blob_service(monkeypatch):
    mock_service = MagicMock(spec=BlobService)
    mock_service.upload_bytes = AsyncMock(return_value="http://mock-url/file.pdf")
    mock_service.upload_file = AsyncMock(return_value="http://mock-url/file.pdf")
    mock_service.list_files = AsyncMock(return_value=["file1.pdf", "file2.pdf"])
    mock_service.delete_file = AsyncMock(return_value=None)
    mock_service.delete_folder = AsyncMock(return_value=None)
    mock_service.download_file = MagicMock(return_value=b"mock-bytes")
    mock_service.sha256_hex = BlobService.sha256_hex
    mock_service.get_blob_info = MagicMock(
        return_value={
            "name": "mock",
            "url": "http://mock-url/blob",
            "size_bytes": 9,
            "content_type": "application/pdf",
            "etag": "etag",
            "last_modified": "2025-12-20T00:00:00Z",
            "creation_time": "2025-12-20T00:00:00Z",
            "metadata": {},
        }
    )

    # Patch the instance in the service module
    monkeypatch.setattr("app.modules.courses.service.blob_service", mock_service)
    return mock_service


@pytest.fixture
def teacher_auth_headers(client):
    email = "teacher@example.com"
    password = "password"

    # Register
    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Teacher",
            "last_name": "One",
            "role": UserRole.TEACHER.value,
        },
    )

    # Login
    response = client.post(
        "/auth/jwt/login",
        data={"username": email, "password": password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def get_teacher_id(db_session) -> int:
    """Return the id of the teacher registered via teacher_auth_headers."""

    user = db_session.query(User).filter(User.email == "teacher@example.com").first()
    return user.id if user else 0


@pytest.fixture
def student_auth_headers(client):
    email = "student@example.com"
    password = "password"

    # Register
    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Student",
            "last_name": "One",
            "role": UserRole.STUDENT.value,
        },
    )

    # Login
    response = client.post(
        "/auth/jwt/login",
        data={"username": email, "password": password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark tests as 'integration' when they use DB-backed fixtures.

    Integration tests (those that need a live PostgreSQL database) use the
    ``db_session`` or ``client`` fixtures.  All other tests are effectively
    unit tests and can run without any database connection.

    Usage:
        pytest -m "not integration"   # fast unit-only pass (local pre-push)
        pytest                         # full suite (CI)
    """
    for item in items:
        if "db_session" in item.fixturenames or "client" in item.fixturenames:
            item.add_marker(pytest.mark.integration)
        else:
            item.add_marker(pytest.mark.unit)


@pytest.fixture
def mock_neo4j():
    """Override get_neo4j_driver with a MagicMock; yield the session mock.

    Tests can configure ``session.run.return_value = [...]`` to shape responses.
    """
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    session.run.return_value = []  # safe default: empty result set
    app.dependency_overrides[get_neo4j_driver] = lambda: driver
    yield session
    app.dependency_overrides.pop(get_neo4j_driver, None)
