import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.modules.auth.models import UserRole
from app.modules.individual_learning import routes
from app.modules.individual_learning.schemas import CVProfileExtraction


def test_individual_learning_router_prefix() -> None:
    assert routes.router.prefix == "/individual-learning"


def test_individual_learning_uses_individual_role() -> None:
    assert routes.INDIVIDUAL_ROLE == UserRole.INDIVIDUAL


def test_service_dependency_constructs_injected_individual_learning_service(
    monkeypatch,
) -> None:
    db = MagicMock()
    driver = MagicMock()
    expected = object()
    constructor = MagicMock(return_value=expected)
    monkeypatch.setattr(routes, "IndividualLearningService", constructor)

    service = routes.get_individual_learning_service(db, driver)

    assert service is expected
    constructor.assert_called_once_with(db, driver)


def test_individual_learning_cv_upload_route_exists() -> None:
    upload_route = next(
        route
        for route in routes.router.routes
        if getattr(route, "path", "").endswith("/cv")
        and "POST" in getattr(route, "methods", set())
    )

    assert upload_route.path == "/individual-learning/cv"
    assert "POST" in upload_route.methods


def test_individual_learning_failed_cv_retry_route_exists_and_delegates() -> None:
    retry_route = next(
        route
        for route in routes.router.routes
        if getattr(route, "path", "").endswith("/cv/{document_id}/retry")
        and "POST" in getattr(route, "methods", set())
    )
    expected = SimpleNamespace(id=9, user_id=7, status="completed")
    service = SimpleNamespace(
        retry_cv_document=AsyncMock(return_value=expected),
    )

    response = asyncio.run(
        routes.retry_cv_document(
            document_id=9,
            user=SimpleNamespace(id=7),
            service=service,
        )
    )

    assert retry_route.path == "/individual-learning/cv/{document_id}/retry"
    assert response is expected
    service.retry_cv_document.assert_awaited_once_with(7, 9)


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
    assert build_route.response_model is routes.IndividualBuildResponse
    assert path_route.path == "/individual-learning/path"


def test_select_individual_skills_route_returns_selected_count() -> None:
    captured: dict[str, object] = {}
    service = SimpleNamespace(
        select_skills=lambda user_id, skill_names: (
            captured.update({"user_id": user_id, "skill_names": skill_names}) or 2
        )
    )

    response = routes.select_skills(
        body=SimpleNamespace(skill_names=["GraphQL", "Docker"]),
        user=SimpleNamespace(id=7),
        service=service,
    )

    assert response == {"selected": 2}
    assert captured == {
        "user_id": 7,
        "skill_names": ["GraphQL", "Docker"],
    }


def test_select_individual_skills_route_returns_400_on_validation_error() -> None:
    service = SimpleNamespace(
        select_skills=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("Select at least one market skill before building")
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.select_skills(
            body=SimpleNamespace(skill_names=[]),
            user=SimpleNamespace(id=7),
            service=service,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Select at least one market skill before building"


def test_deselect_individual_skills_route_returns_deleted_count() -> None:
    service = SimpleNamespace(deselect_skills=lambda user_id, skill_names: 1)

    response = routes.deselect_skills(
        body=SimpleNamespace(skill_names=["GraphQL"]),
        user=SimpleNamespace(id=7),
        service=service,
    )

    assert response == {"deselected": 1}


def test_select_interested_jobs_route_returns_400_for_non_candidate() -> None:
    service = SimpleNamespace(
        select_interested_jobs=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("Select only jobs from your latest candidate search")
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.select_interested_jobs(
            body=SimpleNamespace(posting_urls=["https://jobs.example/injected"]),
            user=SimpleNamespace(id=7),
            service=service,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Select only jobs from your latest candidate search"


def test_build_individual_learning_path_route_returns_completed_status() -> None:
    service = SimpleNamespace(
        build_learning_path=lambda user_id, skill_names: {
            "status": "completed",
            "run_id": "build-run-7",
        }
    )

    response = routes.build_learning_path(
        body=SimpleNamespace(skill_names=["GraphQL"]),
        user=SimpleNamespace(id=7),
        service=service,
    )

    assert response == {"status": "completed", "run_id": "build-run-7"}


def test_build_individual_learning_path_route_returns_400_on_validation_error() -> None:
    service = SimpleNamespace(
        build_learning_path=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("Select at least one market skill before building")
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.build_learning_path(
            body=SimpleNamespace(skill_names=[]),
            user=SimpleNamespace(id=7),
            service=service,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Select at least one market skill before building"


def test_build_individual_learning_path_route_returns_400_for_non_market_request() -> (
    None
):
    service = SimpleNamespace(
        build_learning_path=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("Select only valid market skills before building")
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.build_learning_path(
            body=SimpleNamespace(skill_names=["CV-only"]),
            user=SimpleNamespace(id=7),
            service=service,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Select only valid market skills before building"


def test_get_individual_learning_path_route_returns_projection() -> None:
    service = SimpleNamespace(
        get_learning_path=lambda user_id: {
            "user_id": user_id,
            "selected_skills": [],
            "total_selected_skills": 0,
            "skills_with_resources": 0,
        }
    )

    response = routes.get_learning_path(
        user=SimpleNamespace(id=7),
        service=service,
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
    monkeypatch.setattr(
        "app.modules.individual_learning.service.StructuredCVProfileExtractor",
        lambda: SimpleNamespace(
            model_provider="test-provider",
            model_name="test-model",
            extract=lambda _text: CVProfileExtraction(
                summary="Backend engineer",
                skills=[{"name": "Python", "confidence": 0.9}],
                target_title_suggestions=["Backend Engineer"],
                confidence_summary={"skills": 0.9},
            ),
        ),
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
        "status": "completed",
    }
