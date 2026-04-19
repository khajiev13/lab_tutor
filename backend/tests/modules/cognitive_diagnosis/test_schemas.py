"""Tests for cognitive_diagnosis Pydantic schemas."""

from app.modules.cognitive_diagnosis.schemas import (
    LogEngagementRequest,
    LogInteractionRequest,
    MasteryResponse,
    PortfolioResponse,
    ReviewRequest,
    SkillMastery,
    StudentEventCreate,
    StudentEventsListResponse,
)


class TestSkillMastery:
    def test_valid(self):
        sm = SkillMastery(skill_name="algebra", mastery=0.8, decay=0.9)
        assert sm.skill_name == "algebra"
        assert sm.status == "not_started"

    def test_mastery_bounds(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillMastery(skill_name="x", mastery=1.5, decay=0.5)


class TestLogInteractionRequest:
    def test_defaults(self):
        req = LogInteractionRequest(question_id="q1", answered_right=True)
        assert req.answered_right is True
        assert req.answered_at is None
        assert req.selected_option is None

    def test_full(self):
        req = LogInteractionRequest(
            question_id="q2",
            answered_right=False,
            answered_at="2026-04-14T16:58:25+00:00",
            selected_option="B",
        )
        assert req.answered_right is False
        assert req.selected_option == "B"


class TestLogEngagementRequest:
    def test_reading(self):
        req = LogEngagementRequest(resource_id="r1", resource_type="reading")
        assert req.opened_at is None

    def test_video(self):
        req = LogEngagementRequest(
            resource_id="v1", resource_type="video", opened_at="2026-04-14T12:00:00+00:00"
        )
        assert req.opened_at == "2026-04-14T12:00:00+00:00"

    def test_invalid_type(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LogEngagementRequest(resource_id="x", resource_type="unknown")


class TestReviewRequest:
    def test_default_top_k(self):
        assert ReviewRequest().top_k == 5

    def test_bounds(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ReviewRequest(top_k=0)


class TestStudentEventCreate:
    def test_valid(self):
        ev = StudentEventCreate(date="2026-01-01", title="Exam", event_type="exam")
        assert ev.notes == ""

    def test_invalid_type(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            StudentEventCreate(date="2026-01-01", title="x", event_type="party")


class TestMasteryResponse:
    def test_empty(self):
        r = MasteryResponse(user_id=1)
        assert r.skills == []
        assert r.total_skills == 0


class TestPortfolioResponse:
    def test_defaults(self):
        r = PortfolioResponse(user_id=1)
        assert r.mastery == []
        assert r.pco_skills == []


class TestStudentEventsListResponse:
    def test_empty(self):
        r = StudentEventsListResponse()
        assert r.events == []
