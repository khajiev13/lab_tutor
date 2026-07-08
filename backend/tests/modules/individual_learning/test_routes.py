from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

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


def test_individual_learning_skill_selection_routes_exist() -> None:
    select_route = next(
        route
        for route in routes.router.routes
        if getattr(route, "path", "").endswith("/select-skills")
        and "POST" in getattr(route, "methods", set())
    )
    deselect_route = next(
        route
        for route in routes.router.routes
        if getattr(route, "path", "").endswith("/select-skills")
        and "DELETE" in getattr(route, "methods", set())
    )
    build_route = next(
        route
        for route in routes.router.routes
        if getattr(route, "path", "").endswith("/build")
        and "POST" in getattr(route, "methods", set())
    )
    path_route = next(
        route
        for route in routes.router.routes
        if getattr(route, "path", "").endswith("/path")
        and "GET" in getattr(route, "methods", set())
    )

    assert select_route.path == "/individual-learning/select-skills"
    assert deselect_route.path == "/individual-learning/select-skills"
    assert build_route.path == "/individual-learning/build"
    assert path_route.path == "/individual-learning/path"


def test_select_individual_skills_route_returns_selected_count(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        routes,
        "_get_service",
        lambda _db, _driver: SimpleNamespace(
            select_skills=lambda user_id, skill_names: (
                captured.update({"user_id": user_id, "skill_names": skill_names}) or 2
            )
        ),
    )

    response = routes.select_skills(
        body=SimpleNamespace(skill_names=["GraphQL", "Docker"]),
        user=SimpleNamespace(id=7),
        db=MagicMock(),
        driver=MagicMock(),
    )

    assert response == {"selected": 2}
    assert captured == {
        "user_id": 7,
        "skill_names": ["GraphQL", "Docker"],
    }


def test_select_individual_skills_route_returns_400_on_validation_error(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "_get_service",
        lambda _db, _driver: SimpleNamespace(
            select_skills=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ValueError("Select at least one market skill before building")
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.select_skills(
            body=SimpleNamespace(skill_names=[]),
            user=SimpleNamespace(id=7),
            db=MagicMock(),
            driver=MagicMock(),
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Select at least one market skill before building"


def test_deselect_individual_skills_route_returns_deleted_count(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "_get_service",
        lambda _db, _driver: SimpleNamespace(
            deselect_skills=lambda user_id, skill_names: 1
        ),
    )

    response = routes.deselect_skills(
        body=SimpleNamespace(skill_names=["GraphQL"]),
        user=SimpleNamespace(id=7),
        db=MagicMock(),
        driver=MagicMock(),
    )

    assert response == {"deselected": 1}


def test_build_individual_learning_path_route_returns_completed_status(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "_get_service",
        lambda _db, _driver: SimpleNamespace(
            build_learning_path=lambda user_id, skill_names: {"status": "completed"}
        ),
    )

    response = routes.build_learning_path(
        body=SimpleNamespace(skill_names=["GraphQL"]),
        user=SimpleNamespace(id=7),
        db=MagicMock(),
        driver=MagicMock(),
    )

    assert response == {"status": "completed"}


def test_build_individual_learning_path_route_returns_400_on_validation_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "_get_service",
        lambda _db, _driver: SimpleNamespace(
            build_learning_path=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ValueError("Select at least one market skill before building")
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.build_learning_path(
            body=SimpleNamespace(skill_names=[]),
            user=SimpleNamespace(id=7),
            db=MagicMock(),
            driver=MagicMock(),
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Select at least one market skill before building"


def test_get_individual_learning_path_route_returns_projection(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "_get_service",
        lambda _db, _driver: SimpleNamespace(
            get_learning_path=lambda user_id: {
                "user_id": user_id,
                "selected_skills": [],
                "total_selected_skills": 0,
                "skills_with_resources": 0,
            }
        ),
    )

    response = routes.get_learning_path(
        user=SimpleNamespace(id=7),
        db=MagicMock(),
        driver=MagicMock(),
    )

    assert response.user_id == 7
    assert response.selected_skills == []


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
