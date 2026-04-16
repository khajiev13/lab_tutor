import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.modules.student_learning_path import neo4j_repository, reader_extractor
from app.modules.student_learning_path.schemas import (
    BuildSelectedSkillRequest,
    QuizSubmitRequest,
    ResourceOpenRequest,
)
from app.modules.student_learning_path.service import StudentLearningPathService


def _build_service(
    monkeypatch,
    *,
    min_skills: int = 20,
    max_skills: int = 35,
    is_default: bool = True,
):
    driver = MagicMock()
    service = StudentLearningPathService(MagicMock(), driver)
    monkeypatch.setattr(
        service,
        "_validate_enrollment",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.modules.student_learning_path.service.CourseGraphRepository",
        lambda session: SimpleNamespace(
            get_skill_selection_range=lambda *, course_id: {
                "min_skills": min_skills,
                "max_skills": max_skills,
                "is_default": is_default,
            }
        ),
    )
    return service


def _stub_background_task(monkeypatch):
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return MagicMock()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)
    return scheduled


def test_build_learning_path_persists_first_time_selected_skills(monkeypatch):
    service = _build_service(monkeypatch)
    scheduled = _stub_background_task(monkeypatch)
    select_calls: list[tuple[list[str], str]] = []

    market_skills = [f"Kafka {index}" for index in range(1, 20)]
    requested_skills = [
        BuildSelectedSkillRequest(name="Batch Processing", source="book"),
        *[
            BuildSelectedSkillRequest(name=skill_name, source="market")
            for skill_name in market_skills
        ],
        BuildSelectedSkillRequest(name=market_skills[0], source="market"),
    ]

    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(
            side_effect=[
                [],
                [{"name": "Batch Processing", "source": "book"}],
            ]
        ),
    )
    monkeypatch.setattr(
        neo4j_repository,
        "select_skills",
        lambda _session, _student_id, _course_id, skill_names, source: (
            select_calls.append((skill_names, source)) or len(skill_names)
        ),
    )

    run_id, queue = asyncio.run(
        service.build_learning_path(
            11,
            2,
            requested_skills,
        )
    )

    assert run_id
    assert queue is not None
    assert select_calls == [
        (["Batch Processing"], "book"),
        (market_skills, "market"),
    ]
    assert len(scheduled) == 1


def test_build_learning_path_reuses_locked_selection_without_rewriting(monkeypatch):
    service = _build_service(monkeypatch)
    scheduled = _stub_background_task(monkeypatch)
    select_skills = MagicMock()

    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(side_effect=[[{"name": "Persisted Skill", "source": "book"}]]),
    )
    monkeypatch.setattr(neo4j_repository, "select_skills", select_skills)

    run_id, queue = asyncio.run(
        service.build_learning_path(
            11,
            2,
            [BuildSelectedSkillRequest(name="Kafka", source="market")],
        )
    )

    assert run_id
    assert queue is not None
    select_skills.assert_not_called()
    assert len(scheduled) == 1


def test_build_learning_path_requires_selection_for_first_time_build(monkeypatch):
    service = _build_service(monkeypatch)
    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(side_effect=[[]]),
    )

    with pytest.raises(ValueError) as exc_info:
        asyncio.run(service.build_learning_path(11, 2, []))

    assert str(exc_info.value) == "Select at least one skill before building"


def test_build_learning_path_rejects_first_time_build_below_course_minimum(monkeypatch):
    service = _build_service(monkeypatch, min_skills=2, max_skills=4, is_default=False)
    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(side_effect=[[]]),
    )

    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            service.build_learning_path(
                11,
                2,
                [BuildSelectedSkillRequest(name="Batch Processing", source="book")],
            )
        )

    assert str(exc_info.value) == "Select between 2 and 4 skills before building"


def test_build_learning_path_rejects_first_time_build_above_course_maximum(monkeypatch):
    service = _build_service(monkeypatch, min_skills=1, max_skills=2, is_default=False)
    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(side_effect=[[]]),
    )

    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            service.build_learning_path(
                11,
                2,
                [
                    BuildSelectedSkillRequest(name="Batch Processing", source="book"),
                    BuildSelectedSkillRequest(name="Kafka", source="market"),
                    BuildSelectedSkillRequest(name="SQL", source="market"),
                ],
            )
        )

    assert str(exc_info.value) == "Select between 1 and 2 skills before building"


def test_validate_enrollment_uses_course_id_then_student_id():
    service = StudentLearningPathService(MagicMock(), MagicMock())
    service._course_repo = MagicMock()
    service._course_repo.get_enrollment.return_value = object()

    service._validate_enrollment(4, 2)

    service._course_repo.get_enrollment.assert_called_once_with(2, 4)


def test_validate_enrollment_raises_403_when_student_is_not_enrolled(caplog):
    service = StudentLearningPathService(MagicMock(), MagicMock())
    service._course_repo = MagicMock()
    service._course_repo.get_enrollment.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        service._validate_enrollment(4, 2)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Student is not enrolled in this course"
    assert "student_id=4 course_id=2" in caplog.text


def test_record_resource_open_delegates_to_neo4j_repository(monkeypatch):
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = False
    service = StudentLearningPathService(MagicMock(), driver)

    validate = MagicMock()
    monkeypatch.setattr(service, "_validate_enrollment", validate)
    record_resource_open = MagicMock()
    monkeypatch.setattr(
        neo4j_repository,
        "record_resource_open",
        record_resource_open,
    )

    payload = ResourceOpenRequest(
        resource_type="reading",
        url="https://example.com/reading",
    )
    service.record_resource_open(11, 2, payload)

    validate.assert_called_once_with(11, 2)
    record_resource_open.assert_called_once_with(
        session,
        student_id=11,
        resource_type="reading",
        url="https://example.com/reading",
    )


def test_record_resource_open_raises_403_when_student_is_not_enrolled(monkeypatch):
    driver = MagicMock()
    service = StudentLearningPathService(MagicMock(), driver)
    service._course_repo = MagicMock()
    service._course_repo.get_enrollment.return_value = None

    record_resource_open = MagicMock()
    monkeypatch.setattr(
        neo4j_repository,
        "record_resource_open",
        record_resource_open,
    )

    with pytest.raises(HTTPException) as exc_info:
        service.record_resource_open(
            11,
            2,
            ResourceOpenRequest(
                resource_type="reading", url="https://example.com/reading"
            ),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    record_resource_open.assert_not_called()
    driver.session.assert_not_called()


def test_get_reading_content_raises_403_when_student_is_not_enrolled(monkeypatch):
    service = StudentLearningPathService(MagicMock(), MagicMock())

    monkeypatch.setattr(
        service,
        "_validate_enrollment",
        MagicMock(side_effect=HTTPException(status.HTTP_403_FORBIDDEN, "nope")),
    )
    get_resource = MagicMock()
    monkeypatch.setattr(
        neo4j_repository,
        "get_accessible_reading_resource",
        get_resource,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.get_reading_content(11, 2, "reading-1"))

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    get_resource.assert_not_called()


def test_get_reading_content_raises_404_for_unknown_resource(monkeypatch):
    service = _build_service(monkeypatch)

    monkeypatch.setattr(
        neo4j_repository,
        "get_accessible_reading_resource",
        MagicMock(return_value=None),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.get_reading_content(11, 2, "reading-1"))

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Reading resource not found"


def test_get_reading_content_stores_successful_extraction_and_reuses_fresh_cache(
    monkeypatch,
):
    service = _build_service(monkeypatch)
    first_resource = {
        "id": "reading-1",
        "title": "Batch Systems Guide",
        "url": "https://example.com/reading",
        "domain": "example.com",
        "snippet": "Learn batch processing.",
        "search_content": "Learn batch processing.",
        "reader_status": "",
        "reader_content_markdown": "",
        "reader_error": "",
        "reader_extracted_at": None,
    }
    cached_resource = {
        **first_resource,
        "reader_status": "ready",
        "reader_content_markdown": "# Batch Systems\n\n" + ("A" * 240),
        "reader_extracted_at": datetime.now(UTC).isoformat(),
    }
    get_resource = MagicMock(side_effect=[first_resource, cached_resource])
    persist_cache = MagicMock(return_value=True)
    extract_reading = AsyncMock(
        return_value=reader_extractor.ReaderExtractionSuccess(
            content_markdown="# Batch Systems\n\n" + ("A" * 240)
        )
    )
    monkeypatch.setattr(
        neo4j_repository,
        "get_accessible_reading_resource",
        get_resource,
    )
    monkeypatch.setattr(
        neo4j_repository,
        "persist_reading_reader_cache",
        persist_cache,
    )
    monkeypatch.setattr(
        reader_extractor,
        "extract_reading_markdown",
        extract_reading,
    )

    first_response = asyncio.run(service.get_reading_content(11, 2, "reading-1"))
    second_response = asyncio.run(service.get_reading_content(11, 2, "reading-1"))

    assert first_response.status == "ready"
    assert second_response.status == "ready"
    assert first_response.content_markdown == second_response.content_markdown
    assert first_response.fallback_summary == "Learn batch processing."
    extract_reading.assert_awaited_once_with("https://example.com/reading")
    persist_cache.assert_called_once()


def test_get_reading_content_reextracts_stale_success_cache(monkeypatch):
    service = _build_service(monkeypatch)
    stale_resource = {
        "id": "reading-1",
        "title": "Batch Systems Guide",
        "url": "https://example.com/reading",
        "domain": "",
        "snippet": "Learn batch processing.",
        "search_content": "Detailed batch primer.",
        "reader_status": "ready",
        "reader_content_markdown": "stale markdown",
        "reader_error": "",
        "reader_extracted_at": (datetime.now(UTC) - timedelta(days=31)).isoformat(),
    }
    persist_cache = MagicMock(return_value=True)
    extract_reading = AsyncMock(
        return_value=reader_extractor.ReaderExtractionSuccess(
            content_markdown="# Refreshed\n\n" + ("A" * 240)
        )
    )
    monkeypatch.setattr(
        neo4j_repository,
        "get_accessible_reading_resource",
        MagicMock(return_value=stale_resource),
    )
    monkeypatch.setattr(
        neo4j_repository,
        "persist_reading_reader_cache",
        persist_cache,
    )
    monkeypatch.setattr(
        reader_extractor,
        "extract_reading_markdown",
        extract_reading,
    )

    response = asyncio.run(service.get_reading_content(11, 2, "reading-1"))

    assert response.status == "ready"
    assert response.content_markdown.startswith("# Refreshed")
    assert (
        response.fallback_summary == "Learn batch processing.\n\nDetailed batch primer."
    )
    extract_reading.assert_awaited_once()
    persist_cache.assert_called_once()


def test_get_reading_content_retries_stale_failed_cache_after_24_hours(monkeypatch):
    service = _build_service(monkeypatch)
    stale_failed_resource = {
        "id": "reading-1",
        "title": "Batch Systems Guide",
        "url": "https://example.com/reading",
        "domain": "example.com",
        "snippet": "",
        "search_content": "",
        "reader_status": "failed",
        "reader_content_markdown": "",
        "reader_error": "This source timed out.",
        "reader_extracted_at": (datetime.now(UTC) - timedelta(hours=25)).isoformat(),
    }
    persist_cache = MagicMock(return_value=True)
    extract_reading = AsyncMock(
        return_value=reader_extractor.ReaderExtractionFailure(
            error_code="timeout",
            error_message="This source took too long to respond.",
        )
    )
    monkeypatch.setattr(
        neo4j_repository,
        "get_accessible_reading_resource",
        MagicMock(return_value=stale_failed_resource),
    )
    monkeypatch.setattr(
        neo4j_repository,
        "persist_reading_reader_cache",
        persist_cache,
    )
    monkeypatch.setattr(
        reader_extractor,
        "extract_reading_markdown",
        extract_reading,
    )

    response = asyncio.run(service.get_reading_content(11, 2, "reading-1"))

    assert response.status == "failed"
    assert response.content_markdown == ""
    assert response.error_message == "This source took too long to respond."
    assert (
        response.fallback_summary
        == "We could not generate an in-app preview for this resource. Open the original source to keep studying."
    )
    extract_reading.assert_awaited_once()
    persist_cache.assert_called_once()


def test_get_chapter_quiz_enforces_enrollment(monkeypatch):
    service = StudentLearningPathService(MagicMock(), MagicMock())

    monkeypatch.setattr(
        service,
        "_validate_enrollment",
        MagicMock(side_effect=HTTPException(status.HTTP_403_FORBIDDEN, "nope")),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.get_chapter_quiz(11, 2, 1)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_submit_chapter_quiz_requires_full_chapter_submission(monkeypatch):
    service = _build_service(monkeypatch)

    monkeypatch.setattr(
        neo4j_repository,
        "get_chapter_quiz_progress",
        lambda _session, _student_id, _course_id: [
            {
                "chapter_index": 1,
                "easy_question_count": 2,
                "answered_count": 0,
                "correct_count": 0,
            }
        ],
    )
    monkeypatch.setattr(
        neo4j_repository,
        "get_chapter_easy_questions",
        lambda _session, _student_id, _course_id, _chapter_index: {
            "chapter_title": "Foundations",
            "questions": [
                {
                    "id": "q-1",
                    "skill_name": "Batch Processing",
                    "text": "Q1",
                    "options": ["A", "B", "C", "D"],
                },
                {
                    "id": "q-2",
                    "skill_name": "Kafka",
                    "text": "Q2",
                    "options": ["A", "B", "C", "D"],
                },
            ],
            "previous_answers": {},
        },
    )

    with pytest.raises(ValueError) as exc_info:
        service.submit_chapter_quiz(
            11,
            2,
            1,
            payload=QuizSubmitRequest(
                answers=[
                    {"question_id": "q-1", "selected_option": "A"},
                ]
            ),
        )

    assert (
        str(exc_info.value)
        == "Quiz submission must include every easy question in the chapter"
    )


def test_get_chapter_quiz_rejects_locked_chapter(monkeypatch):
    service = _build_service(monkeypatch)

    monkeypatch.setattr(
        neo4j_repository,
        "get_chapter_quiz_progress",
        lambda _session, _student_id, _course_id: [
            {
                "chapter_index": 1,
                "easy_question_count": 2,
                "answered_count": 1,
                "correct_count": 1,
            },
            {
                "chapter_index": 2,
                "easy_question_count": 1,
                "answered_count": 0,
                "correct_count": 0,
            },
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        service.get_chapter_quiz(11, 2, 2)

    assert str(exc_info.value) == "Chapter quiz is locked"


def test_submit_chapter_quiz_rejects_locked_future_chapter(monkeypatch):
    service = _build_service(monkeypatch)

    monkeypatch.setattr(
        neo4j_repository,
        "get_chapter_quiz_progress",
        lambda _session, _student_id, _course_id: [
            {
                "chapter_index": 1,
                "easy_question_count": 2,
                "answered_count": 1,
                "correct_count": 1,
            },
            {
                "chapter_index": 2,
                "easy_question_count": 1,
                "answered_count": 0,
                "correct_count": 0,
            },
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        service.submit_chapter_quiz(
            11,
            2,
            2,
            payload=QuizSubmitRequest(
                answers=[{"question_id": "q-1", "selected_option": "A"}]
            ),
        )

    assert str(exc_info.value) == "Chapter quiz is locked"


def test_submit_chapter_quiz_returns_results_and_known_skills(monkeypatch):
    service = _build_service(monkeypatch)

    get_progress = MagicMock(
        side_effect=[
            [
                {
                    "chapter_index": 1,
                    "easy_question_count": 1,
                    "answered_count": 0,
                    "correct_count": 0,
                },
                {
                    "chapter_index": 2,
                    "easy_question_count": 1,
                    "answered_count": 0,
                    "correct_count": 0,
                },
            ],
            [
                {
                    "chapter_index": 1,
                    "easy_question_count": 1,
                    "answered_count": 1,
                    "correct_count": 1,
                },
                {
                    "chapter_index": 2,
                    "easy_question_count": 1,
                    "answered_count": 0,
                    "correct_count": 0,
                },
            ],
        ]
    )
    monkeypatch.setattr(
        neo4j_repository,
        "get_chapter_quiz_progress",
        get_progress,
    )
    monkeypatch.setattr(
        neo4j_repository,
        "get_chapter_easy_questions",
        lambda _session, _student_id, _course_id, _chapter_index: {
            "chapter_title": "Foundations",
            "questions": [
                {
                    "id": "q-1",
                    "skill_name": "Batch Processing",
                    "text": "Q1",
                    "options": ["A", "B", "C", "D"],
                }
            ],
            "previous_answers": {},
        },
    )
    monkeypatch.setattr(
        neo4j_repository,
        "submit_chapter_answers",
        lambda _session, _student_id, _course_id, _chapter_index, _answers: [
            {
                "question_id": "q-1",
                "skill_name": "Batch Processing",
                "selected_option": "A",
                "answered_right": True,
                "correct_option": "A",
            }
        ],
    )

    result = service.submit_chapter_quiz(
        11,
        2,
        1,
        payload=QuizSubmitRequest(
            answers=[{"question_id": "q-1", "selected_option": "A"}]
        ),
    )

    assert result.chapter_index == 1
    assert result.skills_known == ["Batch Processing"]
    assert result.chapter_status_after_submit == "completed"
    assert result.correct_count_after_submit == 1
    assert result.easy_question_count == 1
    assert result.next_chapter_unlocked is True


def test_get_chapter_quiz_allows_completed_chapter_retakes(monkeypatch):
    service = _build_service(monkeypatch)

    monkeypatch.setattr(
        neo4j_repository,
        "get_chapter_quiz_progress",
        lambda _session, _student_id, _course_id: [
            {
                "chapter_index": 1,
                "easy_question_count": 1,
                "answered_count": 1,
                "correct_count": 1,
            }
        ],
    )
    monkeypatch.setattr(
        neo4j_repository,
        "get_chapter_easy_questions",
        lambda _session, _student_id, _course_id, _chapter_index: {
            "chapter_title": "Foundations",
            "questions": [
                {
                    "id": "q-1",
                    "skill_name": "Batch Processing",
                    "text": "Q1",
                    "options": ["A", "B", "C", "D"],
                }
            ],
            "previous_answers": {},
        },
    )

    result = service.get_chapter_quiz(11, 2, 1)

    assert result.chapter_index == 1
