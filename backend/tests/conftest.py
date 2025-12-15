from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from lab_tutor_backend.database import Base, get_db
from lab_tutor_backend.models import User, UserRole
from lab_tutor_backend.services.blob_service import BlobService
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

    # Patch the instance in the routes module
    monkeypatch.setattr("lab_tutor_backend.routes.courses.blob_service", mock_service)
    return mock_service


@pytest.fixture
def teacher_auth_headers(client, db_session):
    # Create a teacher user
    teacher = User(
        first_name="Teacher",
        last_name="One",
        email="teacher@example.com",
        password_hash="hashed_password",  # In real app use hasher
        role=UserRole.TEACHER,
    )
    db_session.add(teacher)
    db_session.commit()

    # Login to get token
    # Note: We need to mock the password verification or use a known hash
    # For simplicity, let's just mock the get_current_user dependency or use a helper
    # But since we are testing integration, let's try to use the real auth flow if possible
    # or just create a token manually.

    # Actually, let's override get_current_user for simplicity in some tests,
    # but for "all functionalities" we should test auth too.
    # Let's use a simpler approach: create a token using the auth utils.

    from lab_tutor_backend.auth import create_access_token

    token = create_access_token(data={"sub": teacher.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_auth_headers(client, db_session):
    student = User(
        first_name="Student",
        last_name="One",
        email="student@example.com",
        password_hash="hashed_password",
        role=UserRole.STUDENT,
    )
    db_session.add(student)
    db_session.commit()

    from lab_tutor_backend.auth import create_access_token

    token = create_access_token(data={"sub": student.email})
    return {"Authorization": f"Bearer {token}"}
