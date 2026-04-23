from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.modules.courses.curriculum_schemas import SkillSelectionRangeUpdate
from app.modules.courses.curriculum_service import CurriculumService


def _build_service(*, owner_id: int = 7) -> CurriculumService:
    repo = MagicMock()
    repo.get_by_id.return_value = SimpleNamespace(id=2, teacher_id=owner_id)
    repo.list_course_students.return_value = []
    repo.get_enrolled_student.return_value = None
    service = CurriculumService(repo, MagicMock())
    service._graph_repo = MagicMock()
    service._course_graph_repo = MagicMock()
    service._graph_repo.get_teacher_transcripts.return_value = []
    service._graph_repo.get_book_skill_bank.return_value = []
    service._graph_repo.get_market_skill_bank.return_value = []
    return service


def test_get_skill_banks_includes_selection_range():
    service = _build_service()
    service._course_graph_repo.get_skill_selection_range.return_value = {
        "min_skills": 12,
        "max_skills": 24,
        "is_default": False,
    }

    result = service.get_skill_banks(
        course_id=2,
        teacher=SimpleNamespace(id=7),
    )

    assert result.selection_range.min_skills == 12
    assert result.selection_range.max_skills == 24
    assert result.selection_range.is_default is False


def test_get_curriculum_falls_back_when_chapter_title_is_missing():
    service = _build_service()
    service._graph_repo.get_curriculum_tree.return_value = {
        "book_title": "Big Data",
        "book_authors": "Example Author",
        "chapters": [
            {
                "chapter_index": 3,
                "chapter_title": None,
                "chapter_summary": "Summary",
                "sections": [],
                "book_skills": [],
                "market_skills": [],
            }
        ],
    }

    result = service.get_curriculum(
        course_id=2,
        teacher=SimpleNamespace(id=7),
    )

    assert result.chapters[0].chapter_index == 3
    assert result.chapters[0].title == "Chapter 3"


def test_get_skill_banks_includes_transcript_mapped_market_postings():
    service = _build_service()
    service._graph_repo.get_market_skill_bank.return_value = [
        {
            "title": "Platform Engineer",
            "company": "Acme",
            "site": "LinkedIn",
            "url": "https://jobs.example/platform",
            "search_term": "platform engineer",
            "skills": [
                {
                    "name": "Kafka",
                    "category": "data",
                    "status": "gap",
                    "priority": "high",
                    "demand_pct": 83,
                }
            ],
        }
    ]
    service._course_graph_repo.get_skill_selection_range.return_value = {
        "min_skills": 20,
        "max_skills": 35,
        "is_default": True,
    }

    result = service.get_skill_banks(
        course_id=2,
        teacher=SimpleNamespace(id=7),
    )

    assert result.market_skill_bank[0].title == "Platform Engineer"
    assert result.market_skill_bank[0].skills[0].name == "Kafka"


def test_update_skill_selection_range_requires_course_owner():
    service = _build_service(owner_id=9)

    with pytest.raises(HTTPException) as exc_info:
        service.update_skill_selection_range(
            teacher=SimpleNamespace(id=7),
            course_id=2,
            min_skills=10,
            max_skills=20,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Not authorized to view this course curriculum"


def test_update_skill_selection_range_writes_and_returns_saved_range():
    service = _build_service()
    service._course_graph_repo.get_skill_selection_range.return_value = {
        "min_skills": 15,
        "max_skills": 25,
        "is_default": False,
    }

    result = service.update_skill_selection_range(
        teacher=SimpleNamespace(id=7),
        course_id=2,
        min_skills=15,
        max_skills=25,
    )

    service._course_graph_repo.set_skill_selection_range.assert_called_once_with(
        course_id=2,
        min_skills=15,
        max_skills=25,
    )
    assert result.min_skills == 15
    assert result.max_skills == 25
    assert result.is_default is False


def test_get_student_insights_aggregates_roster_activity(monkeypatch):
    service = _build_service()
    service._repo.list_course_students.return_value = [
        SimpleNamespace(
            id=11,
            first_name="Dana",
            last_name="Demostudent",
            email="dana@example.com",
        ),
        SimpleNamespace(
            id=12,
            first_name="Alex",
            last_name="Example",
            email="alex@example.com",
        ),
    ]

    selected_maps = {
        11: {"Batch Processing": "book", "Kafka": "market"},
        12: {},
    }
    interested_urls = {
        11: ["https://jobs.example/backend"],
        12: [],
    }

    monkeypatch.setattr(
        "app.modules.courses.curriculum_service.student_path_neo4j.get_selected_skill_sources",
        lambda _session, student_id, _course_id: selected_maps[student_id],
    )
    monkeypatch.setattr(
        "app.modules.courses.curriculum_service.student_path_neo4j.get_interested_posting_urls",
        lambda _session,
        student_id,
        _course_id,
        include_inferred_selected_postings: interested_urls[student_id],
    )
    monkeypatch.setattr(
        "app.modules.courses.curriculum_service.student_path_neo4j.get_job_posting_metadata_by_urls",
        lambda _session, urls: {
            "https://jobs.example/backend": {
                "title": "Backend Engineer",
                "company": "Acme",
            }
        }
        if list(urls)
        else {},
    )

    result = service.get_student_insights(
        course_id=2,
        teacher=SimpleNamespace(id=7),
    )

    assert result.summary.students_with_selections == 1
    assert result.summary.students_with_learning_paths == 1
    assert result.summary.avg_selected_skill_count == 1.0
    assert result.summary.top_selected_skills[0].name == "Batch Processing"
    assert result.summary.top_selected_skills[0].student_count == 1
    assert result.summary.top_interested_postings[0].title == "Backend Engineer"
    assert result.students[0].full_name == "Dana Demostudent"
    assert result.students[0].selected_skill_count == 2


def test_get_student_insight_detail_requires_enrolled_student():
    service = _build_service()
    service._repo.get_enrolled_student.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        service.get_student_insight_detail(
            course_id=2,
            teacher=SimpleNamespace(id=7),
            student_id=11,
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Student is not enrolled in this course"


def test_get_student_insight_detail_returns_overlay_and_learning_path_summary(
    monkeypatch,
):
    service = _build_service()
    service._repo.get_enrolled_student.return_value = SimpleNamespace(
        id=11,
        first_name="Dana",
        last_name="Demostudent",
        email="dana@example.com",
    )

    monkeypatch.setattr(
        "app.modules.courses.curriculum_service.student_path_neo4j.get_student_skill_banks",
        lambda _session, student_id, course_id, include_inferred_selected_postings: {
            "book_skill_banks": [],
            "market_skill_bank": [],
            "selected_skill_names": ["Batch Processing"],
            "interested_posting_urls": ["https://jobs.example/backend"],
            "peer_selection_counts": {"Batch Processing": 3},
            "selection_range": {
                "min_skills": 20,
                "max_skills": 35,
                "is_default": True,
            },
            "prerequisite_edges": [],
        },
    )
    monkeypatch.setattr(
        "app.modules.courses.curriculum_service.student_path_neo4j.get_learning_path",
        lambda _session, student_id, course_id: {
            "course_id": course_id,
            "course_title": "Distributed Systems",
            "total_selected_skills": 2,
            "skills_with_resources": 1,
            "chapters": [
                {"quiz_status": "quiz_required"},
                {"quiz_status": "completed"},
                {"quiz_status": "locked"},
            ],
        },
    )

    result = service.get_student_insight_detail(
        course_id=2,
        teacher=SimpleNamespace(id=7),
        student_id=11,
    )

    assert result.student.full_name == "Dana Demostudent"
    assert result.skill_banks.selected_skill_names == ["Batch Processing"]
    assert result.learning_path_summary.has_learning_path is True
    assert result.learning_path_summary.total_selected_skills == 2
    assert result.learning_path_summary.skills_with_resources == 1
    assert result.learning_path_summary.chapter_status_counts.quiz_required == 1
    assert result.learning_path_summary.chapter_status_counts.completed == 1
    assert result.learning_path_summary.chapter_status_counts.locked == 1


def test_skill_selection_range_update_validates_bounds():
    with pytest.raises(ValidationError):
        SkillSelectionRangeUpdate(min_skills=30, max_skills=20)

    with pytest.raises(ValidationError):
        SkillSelectionRangeUpdate(min_skills=0, max_skills=20)

    with pytest.raises(ValidationError):
        SkillSelectionRangeUpdate(min_skills=10, max_skills=201)
