"""Tests for TeacherDigitalTwinService (business logic layer)."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.teacher_digital_twin.service import TeacherDigitalTwinService


def _driver_with_session(rows=None):
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    run_result = MagicMock()
    run_result.__iter__ = MagicMock(return_value=iter(rows or []))
    run_result.single.return_value = None
    session.run.return_value = run_result
    return driver, session


class TestGetSkillDifficulty:
    def test_returns_response_when_empty(self):
        driver, session = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_skill_difficulty(course_id=1)
        assert result.course_id == 1
        assert result.skills == []

    def test_maps_rows(self):
        rows = [
            {
                "skill_name": "calculus",
                "student_count": 5,
                "avg_mastery": 0.6,
                "perceived_difficulty": 0.4,
                "prereq_count": 2,
                "downstream_count": 3,
                "pco_risk_ratio": 0.2,
            }
        ]
        driver, session = _driver_with_session(rows)
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_skill_difficulty(course_id=1)
        assert len(result.skills) == 1
        assert result.skills[0].skill_name == "calculus"
        assert result.skills[0].prereq_count == 2
        assert result.skills[0].downstream_count == 3
        assert result.skills[0].pco_risk_ratio == pytest.approx(0.2)


class TestGetSkillPopularity:
    def test_returns_response_when_empty(self):
        driver, session = _driver_with_session([])
        # get_total_students call returns 0
        session.run.return_value.single.return_value = {"total_students": 0}
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_skill_popularity(course_id=1)
        assert result.course_id == 1
        assert result.all_skills == []

    def test_ranks_skills(self):
        rows = [
            {"skill_name": "algebra", "selection_count": 10},
            {"skill_name": "calculus", "selection_count": 5},
        ]
        driver, _ = _driver_with_session(rows)
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_skill_popularity(course_id=1)
        names = [s.skill_name for s in result.all_skills]
        assert "algebra" in names


class TestGetClassMastery:
    def test_returns_empty_class(self):
        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_class_mastery(course_id=1)
        assert result.course_id == 1
        assert result.students == []
        assert result.total_students == 0

    def test_maps_student_rows(self):
        rows = [
            {
                "user_id": 42,
                "full_name": "Alice",
                "email": "alice@test.com",
                "selected_skill_count": 3,
                "avg_mastery": 0.7,
                "mastered_count": 2,
                "struggling_count": 0,
            }
        ]
        driver, _ = _driver_with_session(rows)
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_class_mastery(course_id=1)
        assert result.total_students == 1
        assert result.students[0].full_name == "Alice"


class TestGetStudentGroups:
    def test_empty_class(self):
        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_student_groups(course_id=1)
        assert result.course_id == 1
        assert result.total_groups == 0


class TestRunWhatIf:
    def test_automatic_mode(self):
        from app.modules.teacher_digital_twin.schemas import (
            AutomaticWhatIfPreferences,
            WhatIfRequest,
        )

        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        req = WhatIfRequest(
            mode="automatic",
            preferences=AutomaticWhatIfPreferences(max_skills=3),
        )
        result = svc.run_what_if(course_id=1, req=req)
        assert result.course_id == 1
        assert result.mode == "automatic"

    def test_automatic_mode_uses_llm_selected_target_masteries(self, monkeypatch):
        from app.modules.teacher_digital_twin.schemas import (
            AutomaticWhatIfPreferences,
            WhatIfRequest,
        )

        driver = MagicMock()
        svc = TeacherDigitalTwinService(driver)

        fake_repo = MagicMock()
        fake_repo.get_class_skill_mastery.return_value = [
            {
                "skill_name": "algebra",
                "student_masteries": [
                    {"user_id": 1, "mastery": 0.30},
                    {"user_id": 2, "mastery": 0.50},
                ],
            },
            {
                "skill_name": "calculus",
                "student_masteries": [
                    {"user_id": 1, "mastery": 0.20},
                    {"user_id": 2, "mastery": 0.40},
                ],
            },
        ]
        fake_repo.get_skill_difficulty.return_value = [
            {
                "skill_name": "algebra",
                "student_count": 2,
                "avg_mastery": 0.40,
                "perceived_difficulty": 0.60,
            },
            {
                "skill_name": "calculus",
                "student_count": 2,
                "avg_mastery": 0.30,
                "perceived_difficulty": 0.70,
            },
        ]
        fake_repo.get_skill_planning_context.return_value = [
            {
                "skill_name": "algebra",
                "prereq_count": 1,
                "downstream_count": 2,
                "pco_student_count": 1,
                "pco_risk_ratio": 0.50,
            },
            {
                "skill_name": "calculus",
                "prereq_count": 2,
                "downstream_count": 4,
                "pco_student_count": 1,
                "pco_risk_ratio": 0.50,
            },
        ]
        monkeypatch.setattr(
            TeacherDigitalTwinService, "_repo", lambda self, session: fake_repo
        )

        called = {"value": False}

        def fake_plan(self, course_id, skill_summaries, preferences):
            called["value"] = True
            assert course_id == 1
            assert preferences.max_skills == 2
            assert {row["skill_name"] for row in skill_summaries} == {
                "algebra",
                "calculus",
            }
            return [
                {
                    "skill_name": "calculus",
                    "target_mastery": 0.82,
                    "reason": "largest class-wide weakness",
                },
                {
                    "skill_name": "algebra",
                    "target_mastery": 0.74,
                    "reason": "important prerequisite gap",
                },
            ]

        monkeypatch.setattr(
            TeacherDigitalTwinService,
            "_plan_automatic_skill_targets",
            fake_plan,
            raising=False,
        )

        req = WhatIfRequest(
            mode="automatic",
            preferences=AutomaticWhatIfPreferences(
                intervention_intensity=0.8,
                focus="broad_support",
                max_skills=2,
            ),
        )
        result = svc.run_what_if(course_id=1, req=req)

        assert called["value"] is True
        assert result.simulated_path == ["calculus", "algebra"]
        assert [
            round(item.simulated_avg_mastery, 2) for item in result.skill_impacts[:2]
        ] == [
            0.82,
            0.74,
        ]
        assert "largest class-wide weakness" in result.recommendations[0]
        assert result.automatic_criteria is not None
        assert result.automatic_criteria.max_skills == 2
        assert result.automatic_criteria.focus == "broad_support"

    def test_automatic_mode_passes_teacher_preferences_to_planner(self, monkeypatch):
        from app.modules.teacher_digital_twin.schemas import (
            AutomaticWhatIfPreferences,
            WhatIfRequest,
        )

        driver = MagicMock()
        svc = TeacherDigitalTwinService(driver)

        fake_repo = MagicMock()
        fake_repo.get_class_skill_mastery.return_value = [
            {
                "skill_name": "algebra",
                "student_masteries": [
                    {"user_id": 1, "mastery": 0.30},
                    {"user_id": 2, "mastery": 0.50},
                ],
            }
        ]
        fake_repo.get_skill_difficulty.return_value = [
            {
                "skill_name": "algebra",
                "student_count": 2,
                "avg_mastery": 0.40,
                "perceived_difficulty": 0.60,
            }
        ]
        fake_repo.get_skill_planning_context.return_value = [
            {
                "skill_name": "algebra",
                "prereq_count": 1,
                "downstream_count": 2,
                "pco_student_count": 1,
                "pco_risk_ratio": 0.50,
            }
        ]
        monkeypatch.setattr(
            TeacherDigitalTwinService, "_repo", lambda self, session: fake_repo
        )

        captured = {}

        def fake_plan(self, course_id, skill_summaries, preferences):
            captured["preferences"] = preferences
            return [
                {
                    "skill_name": "algebra",
                    "target_mastery": 0.78,
                    "reason": "highest leverage skill for broad support",
                }
            ]

        monkeypatch.setattr(
            TeacherDigitalTwinService,
            "_plan_automatic_skill_targets",
            fake_plan,
            raising=False,
        )

        req = WhatIfRequest(
            mode="automatic",
            preferences=AutomaticWhatIfPreferences(
                intervention_intensity=0.7,
                focus="prerequisite_bottlenecks",
                max_skills=1,
            ),
        )
        result = svc.run_what_if(course_id=1, req=req)

        assert captured["preferences"].focus == "prerequisite_bottlenecks"
        assert captured["preferences"].intervention_intensity == pytest.approx(0.7)
        assert captured["preferences"].max_skills == 1
        assert result.automatic_criteria is not None
        assert result.automatic_criteria.focus == "prerequisite_bottlenecks"

    def test_manual_mode(self):
        from app.modules.teacher_digital_twin.schemas import WhatIfRequest, WhatIfSkill

        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        req = WhatIfRequest(
            mode="manual",
            skills=[WhatIfSkill(skill_name="algebra", hypothetical_mastery=0.9)],
        )
        result = svc.run_what_if(course_id=1, req=req)
        assert result.mode == "manual"


class TestSimulateSkill:
    def test_returns_response(self):
        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        result = svc.simulate_skill(
            course_id=1, skill_name="algebra", simulated_mastery=0.5
        )
        assert result.skill_name == "algebra"
        assert result.simulated_mastery == pytest.approx(0.5)


class TestSimulateMultipleSkillsAutomatic:
    def test_automatic_mode_uses_llm_selected_masteries(self, monkeypatch):
        from app.modules.teacher_digital_twin.schemas import MultiSkillSimulationRequest

        driver = MagicMock()
        svc = TeacherDigitalTwinService(driver)

        fake_repo = MagicMock()
        fake_repo.get_skill_difficulty.return_value = [
            {
                "skill_name": "calculus",
                "student_count": 10,
                "avg_mastery": 0.22,
                "perceived_difficulty": 0.78,
            },
            {
                "skill_name": "algebra",
                "student_count": 10,
                "avg_mastery": 0.41,
                "perceived_difficulty": 0.59,
            },
        ]
        fake_repo.get_skill_co_selection.return_value = [
            {"skill_name": "calculus", "user_id": 1, "mastery_score": 0.22},
            {"skill_name": "algebra", "user_id": 1, "mastery_score": 0.41},
            {"skill_name": "calculus", "user_id": 2, "mastery_score": 0.18},
            {"skill_name": "algebra", "user_id": 2, "mastery_score": 0.38},
        ]
        monkeypatch.setattr(
            TeacherDigitalTwinService, "_repo", lambda self, session: fake_repo
        )

        called = {"value": False}

        def fake_plan(self, course_id, skill_summaries, preferences):
            called["value"] = True
            assert course_id == 1
            assert preferences.max_skills == 2
            return [
                {
                    "skill_name": "calculus",
                    "target_mastery": 0.81,
                    "reason": "highest impact concept",
                },
                {
                    "skill_name": "algebra",
                    "target_mastery": 0.69,
                    "reason": "supports downstream skills",
                },
            ]

        monkeypatch.setattr(
            TeacherDigitalTwinService,
            "_plan_automatic_skill_targets",
            fake_plan,
            raising=False,
        )
        monkeypatch.setattr(
            TeacherDigitalTwinService,
            "_generate_simulator_insights",
            lambda *args, **kwargs: None,
        )

        from app.modules.cognitive_diagnosis.service import CognitiveDiagnosisService

        monkeypatch.setattr(
            CognitiveDiagnosisService,
            "generate_exercise",
            lambda self, user_id, skill_name, context: SimpleNamespace(
                problem=f"Question for {skill_name}",
                options=["A", "B", "C"],
                correct_answer="A",
                why=f"Reason for {skill_name}",
            ),
        )

        req = MultiSkillSimulationRequest(mode="automatic", top_k=2)
        result = svc.simulate_multiple_skills(course_id=1, req=req)

        assert called["value"] is True
        assert result.auto_selected_skills == ["calculus", "algebra"]
        assert [round(item.simulated_mastery, 2) for item in result.skill_results] == [
            0.81,
            0.69,
        ]


class TestAutomaticPlanningPrompt:
    def test_prompt_mentions_preferences_prerequisites_student_count_and_pco(
        self, monkeypatch
    ):
        captured = {}

        class FakeOpenAI:
            def __init__(self, *args, **kwargs):
                self.chat = SimpleNamespace(
                    completions=SimpleNamespace(create=self._create)
                )

            def _create(self, **kwargs):
                captured["messages"] = kwargs["messages"]
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content='{"skills":[{"skill_name":"algebra","target_mastery":0.78,"reason":"High student count and prerequisite leverage."}]}'
                            )
                        )
                    ]
                )

        monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
        monkeypatch.setitem(
            sys.modules, "httpx", SimpleNamespace(Timeout=lambda *args, **kwargs: None)
        )

        svc = TeacherDigitalTwinService(MagicMock())
        result = svc._plan_automatic_skill_targets(
            course_id=7,
            skill_summaries=[
                {
                    "skill_name": "algebra",
                    "avg_mastery": 0.33,
                    "student_count": 24,
                    "perceived_difficulty": 0.67,
                    "prereq_count": 2,
                    "downstream_count": 5,
                    "pco_student_count": 9,
                    "pco_risk_ratio": 0.375,
                }
            ],
            preferences=SimpleNamespace(
                intervention_intensity=0.75,
                focus="broad_support",
                max_skills=1,
            ),
        )

        assert result[0]["skill_name"] == "algebra"
        system_prompt = captured["messages"][0]["content"]
        user_prompt = captured["messages"][1]["content"]
        assert "teacher hints" in system_prompt.lower()
        assert "prerequisite" in system_prompt.lower()
        assert "student_count impact" in system_prompt.lower()
        assert "pco risk" in system_prompt.lower()
        assert "teacher preferences" in user_prompt.lower()
        assert "intervention_intensity=0.75" in user_prompt
        assert "focus=broad_support" in user_prompt
        assert "prereq_count=2" in user_prompt
        assert "downstream_count=5" in user_prompt
        assert "pco_student_count=9" in user_prompt
        assert "pco_risk_ratio=0.38" in user_prompt


class TestGetStudentPortfolio:
    def test_teacher_without_class_permission(self):
        """Teacher who doesn't teach the class gets 403."""
        driver, session = _driver_with_session()
        session.run.return_value.single.return_value = {"teaches": False}
        svc = TeacherDigitalTwinService(driver)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            svc.get_student_portfolio(teacher_id=1, student_id=10, course_id=99)
        assert exc.value.status_code == 403
