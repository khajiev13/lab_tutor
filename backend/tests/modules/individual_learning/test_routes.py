from unittest.mock import AsyncMock, MagicMock

from app.modules.auth.models import UserRole
from app.modules.individual_learning import routes


def test_individual_learning_router_prefix() -> None:
    assert routes.router.prefix == "/individual-learning"


def test_individual_learning_uses_individual_role() -> None:
    assert routes.INDIVIDUAL_ROLE == UserRole.INDIVIDUAL


def test_individual_learning_cv_upload_route_exists() -> None:
    upload_route = next(
        route
        for route in routes.router.routes
        if getattr(route, "path", "").endswith("/cv")
        and "POST" in getattr(route, "methods", set())
    )

    assert upload_route.path == "/individual-learning/cv"
    assert "POST" in upload_route.methods


def test_individual_learning_cv_upload_endpoint_returns_created(
    client, monkeypatch
) -> None:
    email = "individual@example.com"
    password = "password"

    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Roma",
            "last_name": "K",
            "role": UserRole.INDIVIDUAL.value,
        },
    )
    login_response = client.post(
        "/auth/jwt/login",
        data={"username": email, "password": password},
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    mock_blob_service = MagicMock()
    mock_blob_service.upload_bytes = AsyncMock(return_value="http://mock-url/cv.docx")
    mock_blob_service.sha256_hex.return_value = "a" * 64
    monkeypatch.setattr(
        "app.modules.individual_learning.service.blob_service",
        mock_blob_service,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.extract_cv_text",
        lambda **_: "Python SQL Azure FastAPI PostgreSQL Docker React TypeScript "
        "data analysis machine learning dashboards APIs cloud deployment testing "
        "architecture collaboration documentation monitoring orchestration pipelines",
    )

    response = client.post(
        "/individual-learning/cv",
        files={
            "file": (
                "roma-cv.docx",
                b"fake-docx-content-for-routing-test",
                (
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                ),
            )
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "user_id": 1,
        "original_filename": "roma-cv.docx",
        "content_type": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        "status": "uploaded",
    }
