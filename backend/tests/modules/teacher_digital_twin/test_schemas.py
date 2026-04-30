"""Tests for teacher_digital_twin Pydantic schemas."""

from app.modules.teacher_digital_twin.schemas import (
    AutomaticWhatIfCriteria,
    AutomaticWhatIfPreferences,
    ClassMasteryResponse,
    MultiSkillSimulationRequest,
    SkillDifficultyItem,
    SkillDifficultyResponse,
    SkillPopularityItem,
    SkillPopularityResponse,
    SkillSimulationRequest,
    StudentGroup,
    StudentGroupMember,
    StudentGroupsResponse,
    StudentMasterySummary,
    WhatIfRequest,
    WhatIfResponse,
)


class TestSkillDifficultySchemas:
    def test_item(self):
        item = SkillDifficultyItem(
            skill_name="calculus",
            student_count=5,
            avg_mastery=0.6,
            perceived_difficulty=0.4,
        )
        assert item.skill_name == "calculus"

    def test_response(self):
        item = SkillDifficultyItem(
            skill_name="x", student_count=1, avg_mastery=0.5, perceived_difficulty=0.5
        )
        r = SkillDifficultyResponse(course_id=1, skills=[item], total_skills=1)
        assert r.total_skills == 1


class TestSkillPopularitySchemas:
    def test_item(self):
        item = SkillPopularityItem(skill_name="algebra", selection_count=10, rank=1)
        assert item.rank == 1

    def test_response(self):
        item = SkillPopularityItem(skill_name="x", selection_count=1, rank=1)
        r = SkillPopularityResponse(
            course_id=1,
            all_skills=[item],
            most_popular=[item],
            least_popular=[item],
            total_students=5,
        )
        assert r.total_students == 5


class TestClassMasterySchemas:
    def test_summary(self):
        s = StudentMasterySummary(
            user_id=1,
            full_name="Alice",
            email="alice@test.com",
            selected_skill_count=3,
            avg_mastery=0.7,
            mastered_count=2,
            struggling_count=1,
            pco_count=0,
            at_risk=False,
        )
        assert s.at_risk is False

    def test_response_defaults(self):
        r = ClassMasteryResponse(
            course_id=1,
            students=[],
            class_avg_mastery=0.0,
            at_risk_count=0,
            total_students=0,
        )
        assert r.students == []


class TestStudentGroupSchemas:
    def test_group(self):
        member = StudentGroupMember(user_id=1, full_name="Alice", avg_mastery=0.7)
        group = StudentGroup(
            group_id="g1",
            skill_set=["algebra"],
            member_count=1,
            members=[member],
            group_avg_mastery=0.7,
            suggested_path=["calculus"],
        )
        assert group.performance_tier == "developing"

    def test_response(self):
        r = StudentGroupsResponse(
            course_id=1, groups=[], ungrouped_students=[], total_groups=0
        )
        assert r.total_groups == 0


class TestWhatIfSchemas:
    def test_request_defaults(self):
        r = WhatIfRequest()
        assert r.mode == "automatic"
        assert r.preferences == AutomaticWhatIfPreferences()

    def test_response(self):
        r = WhatIfResponse(
            mode="automatic",
            course_id=1,
            simulated_path=[],
            pco_analysis=[],
            recommendations=[],
            skill_impacts=[],
            summary="ok",
            automatic_criteria=AutomaticWhatIfCriteria(
                intervention_intensity=0.7,
                focus="broad_support",
                max_skills=4,
                llm_decision_summary="LLM selected broad-support targets.",
            ),
        )
        assert r.llm_recommendation is None
        assert r.automatic_criteria.focus == "broad_support"


class TestSkillSimulationSchemas:
    def test_request_defaults(self):
        r = SkillSimulationRequest(skill_name="algebra")
        assert r.simulated_mastery == 0.5

    def test_multi_request_empty_skills(self):
        r = MultiSkillSimulationRequest(skills=[])
        assert r.skills == []
