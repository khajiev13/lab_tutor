"""Tests for chapter-level skills extraction schemas.

Covers:
- SkillConcept, Skill, ChapterSkillsResult schema validation
- SkillsJudgeFeedback / SkillsJudgeVerdict
- _sse helper function
"""

from __future__ import annotations

import json

from app.modules.curricularalignmentarchitect.chapter_extraction.schemas import (
    ChapterSkillsResult,
    Skill,
    SkillConcept,
    SkillsJudgeFeedback,
    SkillsJudgeVerdict,
)

# ── SkillConcept ────────────────────────────────────────────────


class TestSkillConcept:
    def test_valid(self):
        c = SkillConcept(name="MapReduce", description="A parallel processing model")
        assert c.name == "MapReduce"
        assert c.description == "A parallel processing model"

    def test_empty_description_defaults(self):
        c = SkillConcept(name="HDFS", description="")
        assert c.description == ""


# ── Skill ───────────────────────────────────────────────────────


class TestSkill:
    def test_valid_with_concepts(self):
        s = Skill(
            name="Design a Hadoop cluster",
            description="Architect and configure HDFS + YARN for a given workload",
            concepts=[
                SkillConcept(name="HDFS", description="Distributed file system"),
                SkillConcept(name="YARN", description="Resource manager"),
            ],
        )
        assert s.name == "Design a Hadoop cluster"
        assert len(s.concepts) == 2
        assert s.concepts[0].name == "HDFS"

    def test_empty_concepts_default(self):
        s = Skill(name="Analyze data streams", description="Apply stream processing")
        assert s.concepts == []


# ── ChapterSkillsResult ─────────────────────────────────────────


class TestChapterSkillsResult:
    def test_empty_skills(self):
        r = ChapterSkillsResult(
            chapter_summary="A purely theoretical chapter",
            skills=[],
        )
        assert r.skills == []
        assert r.chapter_summary == "A purely theoretical chapter"

    def test_with_skills(self):
        r = ChapterSkillsResult(
            chapter_summary="Chapter on NoSQL databases",
            skills=[
                Skill(
                    name="Implement a key-value store",
                    description="Build a simple KV store using Redis",
                    concepts=[
                        SkillConcept(name="Redis", description="In-memory KV store")
                    ],
                ),
            ],
        )
        assert len(r.skills) == 1
        assert r.skills[0].concepts[0].name == "Redis"

    def test_serialisation_round_trip(self):
        r = ChapterSkillsResult(
            chapter_summary="Summary",
            skills=[
                Skill(
                    name="Configure HBase",
                    description="Set up an HBase cluster",
                    concepts=[
                        SkillConcept(name="HBase", description="Column-family store")
                    ],
                )
            ],
        )
        data = r.model_dump()
        restored = ChapterSkillsResult.model_validate(data)
        assert restored.skills[0].name == "Configure HBase"
        assert restored.skills[0].concepts[0].name == "HBase"


# ── SkillsJudgeFeedback ─────────────────────────────────────────


class TestSkillsJudgeFeedback:
    def test_approved(self):
        fb = SkillsJudgeFeedback(
            verdict=SkillsJudgeVerdict.APPROVED,
            reasoning="All skills use action verbs and are well scoped",
        )
        assert fb.verdict == SkillsJudgeVerdict.APPROVED
        assert fb.issues == []

    def test_needs_revision(self):
        fb = SkillsJudgeFeedback(
            verdict=SkillsJudgeVerdict.NEEDS_REVISION,
            issues=[
                "Skill 1 is a concept, not an ability",
                "Missing action verb in skill 3",
            ],
            reasoning="Two skills need to be rewritten",
        )
        assert fb.verdict == SkillsJudgeVerdict.NEEDS_REVISION
        assert len(fb.issues) == 2

    def test_verdict_values(self):
        assert SkillsJudgeVerdict.APPROVED.value == "APPROVED"
        assert SkillsJudgeVerdict.NEEDS_REVISION.value == "NEEDS_REVISION"


# ── _sse helper ─────────────────────────────────────────────────


class TestSseHelper:
    def test_format(self):
        from app.modules.curricularalignmentarchitect.api_routes.agentic_analysis import (
            _sse,
        )

        result = _sse("book_started", {"book_id": 1, "title": "Test"})
        assert result.startswith("event: book_started\n")
        assert "data:" in result
        assert result.endswith("\n\n")

        payload = json.loads(result.split("data: ")[1].strip())
        assert payload["type"] == "book_started"
        assert payload["book_id"] == 1
