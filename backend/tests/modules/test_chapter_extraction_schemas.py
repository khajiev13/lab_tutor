"""Tests for chapter extraction schemas and node helper functions.

Covers:
- Pydantic schema validation (Concept, ChapterConceptsResult, etc.)
- _safe_parse_chapter_concepts fallback parser
- _format_section_list helper
- _format_concepts_for_eval helper
- _sse helper function
"""

from __future__ import annotations

import json

from app.modules.curricularalignmentarchitect.chapter_extraction.nodes import (
    _format_concepts_for_eval,
    _format_section_list,
    _safe_parse_chapter_concepts,
)
from app.modules.curricularalignmentarchitect.chapter_extraction.schemas import (
    ChapterConceptsResult,
    ChapterExtraction,
    ChapterSkillsResult,
    Concept,
    ConceptRelevance,
    EvaluationVerdict,
    ExtractionFeedback,
    SectionExtraction,
    Skill,
)

# ── Concept schema ──────────────────────────────────────────────


class TestConceptSchema:
    def test_valid_concept(self):
        c = Concept(
            name="Distributed Systems",
            description="Systems spread across multiple machines",
            relevance=ConceptRelevance.CORE,
            text_evidence="Quote from text",
            source_section=1,
        )
        assert c.name == "Distributed Systems"
        assert c.relevance == ConceptRelevance.CORE
        assert c.name_embedding is None
        assert c.evidence_embedding is None

    def test_concept_relevance_values(self):
        assert ConceptRelevance.CORE.value == "core"
        assert ConceptRelevance.SUPPLEMENTARY.value == "supplementary"
        assert ConceptRelevance.TANGENTIAL.value == "tangential"


# ── ChapterConceptsResult ──────────────────────────────────────


class TestChapterConceptsResult:
    def test_empty_concepts_default(self):
        result = ChapterConceptsResult(chapter_title="Ch 1")
        assert result.concepts == []

    def test_with_concepts(self):
        c = Concept(
            name="A",
            description="desc",
            relevance=ConceptRelevance.CORE,
            text_evidence="ev",
            source_section=1,
        )
        result = ChapterConceptsResult(chapter_title="Ch 1", concepts=[c])
        assert len(result.concepts) == 1


# ── ChapterExtraction ──────────────────────────────────────────


class TestChapterExtraction:
    def test_all_concepts_property(self):
        c1 = Concept(
            name="A",
            description="d",
            relevance=ConceptRelevance.CORE,
            text_evidence="e",
            source_section=1,
        )
        c2 = Concept(
            name="B",
            description="d",
            relevance=ConceptRelevance.SUPPLEMENTARY,
            text_evidence="e",
            source_section=2,
        )
        extraction = ChapterExtraction(
            chapter_title="Ch 1",
            chapter_summary="Summary",
            sections=[
                SectionExtraction(section_title="S1", concepts=[c1]),
                SectionExtraction(section_title="S2", concepts=[c2]),
            ],
        )
        assert extraction.total_concept_count == 2
        assert [c.name for c in extraction.all_concepts] == ["A", "B"]

    def test_empty_sections(self):
        extraction = ChapterExtraction(
            chapter_title="Ch 1",
            chapter_summary="Summary",
            sections=[],
        )
        assert extraction.total_concept_count == 0
        assert extraction.all_concepts == []


# ── ExtractionFeedback ──────────────────────────────────────────


class TestExtractionFeedback:
    def test_approved_verdict(self):
        fb = ExtractionFeedback(
            verdict=EvaluationVerdict.APPROVED, reasoning="Looks good"
        )
        assert fb.verdict == EvaluationVerdict.APPROVED
        assert fb.strengths == []
        assert fb.reasoning == "Looks good"

    def test_needs_revision(self):
        fb = ExtractionFeedback(
            verdict=EvaluationVerdict.NEEDS_REVISION,
            strengths=["Good coverage"],
            reasoning="Missing key concepts",
        )
        assert fb.verdict == EvaluationVerdict.NEEDS_REVISION
        assert len(fb.strengths) == 1
        assert fb.reasoning == "Missing key concepts"


# ── Skill / ChapterSkillsResult ────────────────────────────────


class TestSkillSchema:
    def test_skill(self):
        s = Skill(
            name="SQL Querying",
            description="Write complex SQL",
            concept_names=["Joins", "Subqueries"],
        )
        assert s.name == "SQL Querying"
        assert len(s.concept_names) == 2

    def test_chapter_skills_result(self):
        r = ChapterSkillsResult(
            chapter_summary="A chapter about databases",
            skills=[
                Skill(name="S1", description="D1", concept_names=[]),
            ],
        )
        assert len(r.skills) == 1


# ── _safe_parse_chapter_concepts ────────────────────────────────


class TestSafeParseChapterConcepts:
    def test_valid_json(self):
        data = {
            "chapter_title": "Ch 1",
            "concepts": [
                {
                    "name": "A",
                    "description": "desc",
                    "relevance": "core",
                    "text_evidence": "ev",
                    "source_section": 1,
                }
            ],
        }
        result = _safe_parse_chapter_concepts(json.dumps(data), "Ch 1")
        assert len(result.concepts) == 1
        assert result.concepts[0].name == "A"

    def test_drops_malformed_concepts(self):
        data = {
            "chapter_title": "Ch 1",
            "concepts": [
                {
                    "name": "Good",
                    "description": "d",
                    "relevance": "core",
                    "text_evidence": "e",
                    "source_section": 1,
                },
                {"name": "Bad"},  # missing fields
                "not a dict",  # wrong type
            ],
        }
        result = _safe_parse_chapter_concepts(json.dumps(data), "Ch 1")
        assert len(result.concepts) == 1
        assert result.concepts[0].name == "Good"

    def test_empty_concepts(self):
        data = {"chapter_title": "Ch 1", "concepts": []}
        result = _safe_parse_chapter_concepts(json.dumps(data), "Ch 1")
        assert result.concepts == []

    def test_uses_fallback_title(self):
        data = {"concepts": []}
        result = _safe_parse_chapter_concepts(json.dumps(data), "Fallback Title")
        assert result.chapter_title == "Fallback Title"


# ── _format_section_list ────────────────────────────────────────


class TestFormatSectionList:
    def test_with_sections(self):
        result = _format_section_list(["Intro", "Methods", "Results"])
        assert "1. Intro" in result
        assert "2. Methods" in result
        assert "3. Results" in result

    def test_empty(self):
        result = _format_section_list([])
        assert "no sections" in result.lower()


# ── _format_concepts_for_eval ───────────────────────────────────


class TestFormatConceptsForEval:
    def test_with_concepts(self):
        extraction = ChapterConceptsResult(
            chapter_title="Ch 1",
            concepts=[
                Concept(
                    name="A",
                    description="desc A",
                    relevance=ConceptRelevance.CORE,
                    text_evidence="evidence text here",
                    source_section=1,
                ),
            ],
        )
        result = _format_concepts_for_eval(extraction)
        assert "core" in result
        assert "A" in result
        assert "#1" in result

    def test_empty_concepts(self):
        extraction = ChapterConceptsResult(chapter_title="Ch 1", concepts=[])
        result = _format_concepts_for_eval(extraction)
        assert "no concepts" in result.lower()


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
