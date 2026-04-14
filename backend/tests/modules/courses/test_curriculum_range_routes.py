from app.modules.courses.curriculum_service import get_curriculum_service
from main import app


class _FakeCurriculumService:
    def __init__(self) -> None:
        self.updated_payloads: list[dict[str, int]] = []

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
