import os

# Force local SQLite for tests BEFORE importing app modules.
# This prevents accidental connections to cloud Postgres in CI/dev envs.
os.environ["LAB_TUTOR_DATABASE_URL"] = "sqlite:///./data/test.db"
# Ensure optional external services don't run in tests.
os.environ.setdefault("LAB_TUTOR_NEO4J_URI", "")
os.environ.setdefault("LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING", "")

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker


from app.core.database import Base, get_db, get_async_db
from app.modules.auth.models import UserRole
from app.providers.storage import BlobService
from main import app

# Use a file-based SQLite DB so BOTH sync + async sessions share the same database.
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/test.db"
ASYNC_SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./data/test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine for FastAPI-Users
async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
AsyncTestingSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture(scope="function")
def db_session():
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
