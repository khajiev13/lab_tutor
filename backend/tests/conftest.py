from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.modules.auth.models import UserRole
from app.providers.storage import BlobService
from main import app

# Setup in-memory SQLite database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def mock_blob_service(monkeypatch):
    mock_service = MagicMock(spec=BlobService)
    mock_service.upload_file = AsyncMock(return_value="http://mock-url/file.pdf")
    mock_service.list_files = AsyncMock(return_value=["file1.pdf", "file2.pdf"])
    mock_service.delete_file = AsyncMock(return_value=None)
    mock_service.delete_folder = AsyncMock(return_value=None)

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

