from __future__ import annotations

from fastapi import HTTPException
from langgraph.types import Command

from app.modules.individual_learning.service import IndividualLearningService


def test_get_profile_returns_default_onboarding_state() -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)
    profile = service.get_profile(user_id=42)

    assert profile.user_id == 42
    assert profile.onboarding_status == "needs_cv"
    assert profile.target_titles == []


def test_resume_individual_graph_rejects_malformed_thread_id(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))),
    )

    try:
        service.resume_individual_graph(
            user_id=7,
            thread_id="individual-7-cv-3-extra",
            payload={},
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "Thread does not belong to the current user"
    else:
        raise AssertionError("Expected HTTPException for malformed thread_id")


def test_resume_individual_graph_rejects_foreign_thread_id(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))),
    )

    try:
        service.resume_individual_graph(
            user_id=7,
            thread_id="individual-999-cv-12",
            payload={},
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "Thread does not belong to the current user"
    else:
        raise AssertionError("Expected HTTPException for foreign thread_id")


def test_resume_individual_graph_rejects_missing_cv_for_owned_thread(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    def fake_load_profile_payload(user_id: int, cv_document_id: int) -> dict[str, object]:
        assert user_id == 7
        assert cv_document_id == 3
        raise HTTPException(status_code=404, detail="CV document not found")

    monkeypatch.setattr(service, "_load_profile_payload", fake_load_profile_payload)
    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))),
    )

    try:
        service.resume_individual_graph(
            user_id=7,
            thread_id="individual-7-cv-3",
            payload={},
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "Thread does not belong to the current user"
    else:
        raise AssertionError("Expected HTTPException when CV ownership cannot be proven")


def test_resume_individual_graph_allows_owned_thread_and_invokes_graph(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)
    resume_payload = {"approved": True}
    captured: dict[str, object] = {}

    class DummyGraph:
        def invoke(self, command: Command, config: dict[str, object]) -> dict[str, object]:
            captured["command"] = command
            captured["config"] = config
            return {
                "target_titles": ["Data Analyst"],
                "selected_posting_urls": [],
                "selected_skill_names": [],
            }

    monkeypatch.setattr(
        service,
        "_load_profile_payload",
        lambda user_id, cv_document_id: {"target_title_suggestions": ["Data Analyst"]},
    )
    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: DummyGraph()),
    )

    response = service.resume_individual_graph(
        user_id=7,
        thread_id="individual-7-cv-3",
        payload=resume_payload,
    )

    assert captured["config"] == {"configurable": {"thread_id": "individual-7-cv-3"}}
    assert isinstance(captured["command"], Command)
    assert captured["command"].resume == resume_payload
    assert response.status == "completed"
