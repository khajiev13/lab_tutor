from app.modules.courses.curriculum_service import get_curriculum_service
from main import app


class _FakeCurriculumService:
    def __init__(self) -> None:
        self.updated_payloads: list[dict[str, int]] = []

    def get_curriculum(self, *, course_id: int, teacher):
        return {
            "course_id": course_id,
            "book_title": "Distributed Systems",
            "book_authors": "T. Author",
            "chapters": [],
        }

    def get_skill_banks(self, *, course_id: int, teacher):
        return {
            "course_chapters": [],
            "book_skill_bank": [],
            "market_skill_bank": [],
            "selection_range": {
                "min_skills": 20,
                "max_skills": 35,
                "is_default": True,
            },
        }

    def get_student_insights(self, *, course_id: int, teacher):
        return {
            "summary": {
                "students_with_selections": 1,
                "students_with_learning_paths": 1,
                "avg_selected_skill_count": 2.0,
                "top_selected_skills": [
                    {"name": "Batch Processing", "student_count": 1}
                ],
                "top_interested_postings": [
                    {
                        "url": "https://jobs.example/backend",
                        "title": "Backend Engineer",
                        "company": "Acme",
                        "student_count": 1,
                    }
                ],
            },
            "students": [
                {
                    "id": 11,
                    "full_name": "Dana Demostudent",
                    "email": "dana@example.com",
                    "selected_skill_count": 2,
                    "interested_posting_count": 1,
                    "has_learning_path": True,
                }
            ],
        }

    def get_student_insight_detail(self, *, course_id: int, teacher, student_id: int):
        return {
            "student": {
                "id": student_id,
                "full_name": "Dana Demostudent",
                "email": "dana@example.com",
            },
            "skill_banks": {
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
            "learning_path_summary": {
                "has_learning_path": True,
                "total_selected_skills": 2,
                "skills_with_resources": 1,
                "chapter_status_counts": {
                    "locked": 1,
                    "quiz_required": 1,
                    "learning": 0,
                    "completed": 1,
                },
            },
        }

    def update_skill_selection_range(
        self, *, teacher, course_id: int, min_skills: int, max_skills: int
    ):
        self.updated_payloads.append(
            {
                "course_id": course_id,
                "teacher_id": teacher.id,
                "min_skills": min_skills,
                "max_skills": max_skills,
            }
        )
        return {
            "min_skills": min_skills,
            "max_skills": max_skills,
            "is_default": False,
        }


def test_get_course_curriculum_route_returns_plain_curriculum_without_changelog(
    client, teacher_auth_headers
):
    service = _FakeCurriculumService()
    app.dependency_overrides[get_curriculum_service] = lambda: service

    response = client.get("/courses/2/curriculum", headers=teacher_auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["course_id"] == 2
    assert "changelog" not in payload


def test_get_course_skill_banks_returns_default_selection_range(
    client, teacher_auth_headers
):
    service = _FakeCurriculumService()
    app.dependency_overrides[get_curriculum_service] = lambda: service

    response = client.get("/courses/2/skill-banks", headers=teacher_auth_headers)

    assert response.status_code == 200
    assert response.json()["selection_range"] == {
        "min_skills": 20,
        "max_skills": 35,
        "is_default": True,
    }


def test_update_course_skill_selection_range_route_updates_range(
    client, teacher_auth_headers
):
    service = _FakeCurriculumService()
    app.dependency_overrides[get_curriculum_service] = lambda: service

    response = client.patch(
        "/courses/2/skill-selection-range",
        json={"min_skills": 12, "max_skills": 28},
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "min_skills": 12,
        "max_skills": 28,
        "is_default": False,
    }
    assert len(service.updated_payloads) == 1
    assert service.updated_payloads[0]["course_id"] == 2
    assert service.updated_payloads[0]["min_skills"] == 12
    assert service.updated_payloads[0]["max_skills"] == 28


def test_update_course_skill_selection_range_route_rejects_invalid_payload(
    client,
    teacher_auth_headers,
):
    app.dependency_overrides[get_curriculum_service] = lambda: _FakeCurriculumService()

    too_large = client.patch(
        "/courses/2/skill-selection-range",
        json={"min_skills": 10, "max_skills": 201},
        headers=teacher_auth_headers,
    )
    reversed_range = client.patch(
        "/courses/2/skill-selection-range",
        json={"min_skills": 30, "max_skills": 20},
        headers=teacher_auth_headers,
    )

    assert too_large.status_code == 422
    assert reversed_range.status_code == 422


def test_get_course_student_insights_route_returns_overview(
    client,
    teacher_auth_headers,
):
    service = _FakeCurriculumService()
    app.dependency_overrides[get_curriculum_service] = lambda: service

    response = client.get("/courses/2/student-insights", headers=teacher_auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["students_with_selections"] == 1
    assert payload["students"][0]["full_name"] == "Dana Demostudent"


def test_get_course_student_insight_detail_route_returns_detail(
    client,
    teacher_auth_headers,
):
    service = _FakeCurriculumService()
    app.dependency_overrides[get_curriculum_service] = lambda: service

    response = client.get(
        "/courses/2/student-insights/11",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["student"]["id"] == 11
    assert payload["skill_banks"]["selected_skill_names"] == ["Batch Processing"]
    assert payload["learning_path_summary"]["chapter_status_counts"]["completed"] == 1
