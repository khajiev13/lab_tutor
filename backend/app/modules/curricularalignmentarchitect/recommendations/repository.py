"""Data fetching for recommendation agents.

Pulls pre-computed analysis data from PostgreSQL (ChapterAnalysisSummary)
and teacher document context from Neo4j.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from app.core.settings import settings

from ..models import ChapterAnalysisSummary

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────

NOVEL_THRESHOLD = 0.35
OVERLAP_THRESHOLD = 0.55

# ── Data containers ───────────────────────────────────────────


@dataclass
class NovelConcept:
    """A book concept not covered by the teacher's materials."""

    name: str
    chapter_title: str | None = None
    section_title: str | None = None
    sim_max: float = 0.0
    best_course_match: str | None = None
    description: str | None = None
    text_evidence: str | None = None
    relevance: str | None = None


@dataclass
class WeakCourseConcept:
    """A course concept with weak book support."""

    concept_name: str
    sim_max: float = 0.0
    doc_topic: str | None = None
    best_match: str | None = None


@dataclass
class ChapterSkillInfo:
    """Skill extracted from a book chapter."""

    name: str
    description: str
    chapter_title: str | None = None
    concept_names: list[str] = field(default_factory=list)


@dataclass
class TeacherDocument:
    """A teacher-uploaded document with its mentioned concepts."""

    doc_id: str
    topic: str | None = None
    summary: str | None = None
    keywords: str | None = None
    source_filename: str | None = None
    concept_names: list[str] = field(default_factory=list)


@dataclass
class RecommendationData:
    """All data needed by recommendation agents, fetched in one pass."""

    book_title: str
    novel_concepts: list[NovelConcept] = field(default_factory=list)
    overlap_concepts: list[NovelConcept] = field(default_factory=list)
    weak_course_concepts: list[WeakCourseConcept] = field(default_factory=list)
    skills: list[ChapterSkillInfo] = field(default_factory=list)
    teacher_documents: list[TeacherDocument] = field(default_factory=list)


# ── Repository ────────────────────────────────────────────────


class RecommendationRepository:
    """Fetches pre-computed analysis data and teacher document context."""

    def __init__(self, db: Session, neo4j_session: Neo4jSession | None = None):
        self.db = db
        self.neo4j_session = neo4j_session

    def get_chapter_summary(
        self, run_id: int, selected_book_id: int
    ) -> ChapterAnalysisSummary | None:
        """Load the pre-computed ChapterAnalysisSummary row."""
        return (
            self.db.query(ChapterAnalysisSummary)
            .filter(
                ChapterAnalysisSummary.run_id == run_id,
                ChapterAnalysisSummary.selected_book_id == selected_book_id,
            )
            .first()
        )

    def extract_novel_and_overlap_concepts(
        self, summary: ChapterAnalysisSummary
    ) -> tuple[list[NovelConcept], list[NovelConcept]]:
        """Parse ``book_unique_concepts_json`` into novel + overlap buckets."""
        raw = summary.book_unique_concepts_json
        if not raw:
            return [], []

        items = json.loads(raw) if isinstance(raw, str) else raw
        novel: list[NovelConcept] = []
        overlap: list[NovelConcept] = []

        for item in items:
            sim = item.get("sim_max", 1.0)
            concept = NovelConcept(
                name=item.get("name", ""),
                chapter_title=item.get("chapter_title"),
                section_title=item.get("section_title"),
                sim_max=sim,
                best_course_match=item.get("best_course_match"),
                description=item.get("description"),
                text_evidence=item.get("text_evidence"),
                relevance=item.get("relevance"),
            )
            if sim < NOVEL_THRESHOLD:
                novel.append(concept)
            elif sim < OVERLAP_THRESHOLD:
                overlap.append(concept)

        return novel, overlap

    def extract_weak_course_concepts(
        self, summary: ChapterAnalysisSummary
    ) -> list[WeakCourseConcept]:
        """Parse ``course_coverage_json`` for weakly-covered course concepts."""
        raw = summary.course_coverage_json
        if not raw:
            return []

        items = json.loads(raw) if isinstance(raw, str) else raw
        weak: list[WeakCourseConcept] = []

        for item in items:
            sim = item.get("sim_max", 1.0)
            if sim < OVERLAP_THRESHOLD:
                weak.append(
                    WeakCourseConcept(
                        concept_name=item.get("concept_name", ""),
                        sim_max=sim,
                        doc_topic=item.get("doc_topic"),
                        best_match=item.get("best_match"),
                    )
                )

        return weak

    def extract_skills(self, summary: ChapterAnalysisSummary) -> list[ChapterSkillInfo]:
        """Pull skills from ``chapter_details_json``."""
        raw = summary.chapter_details_json
        if not raw:
            return []

        chapters = json.loads(raw) if isinstance(raw, str) else raw
        skills: list[ChapterSkillInfo] = []

        for ch in chapters:
            chapter_title = ch.get("chapter_title", "")
            for sk in ch.get("skills", []):
                skills.append(
                    ChapterSkillInfo(
                        name=sk.get("name", ""),
                        description=sk.get("description", ""),
                        chapter_title=chapter_title,
                        concept_names=sk.get("concept_names", []),
                    )
                )

        return skills

    def fetch_teacher_documents(self, course_id: int) -> list[TeacherDocument]:
        """Fetch teacher-uploaded documents and their concepts from Neo4j."""
        if self.neo4j_session is None:
            logger.warning("Neo4j not available — skipping teacher document fetch")
            return []

        query = """
        MATCH (c:CLASS {id: $course_id})-[:HAS_DOCUMENT]->(d:TEACHER_UPLOADED_DOCUMENT)
        OPTIONAL MATCH (d)-[m:MENTIONS]->(concept:CONCEPT)
        RETURN d.id AS doc_id,
               d.topic AS topic,
               d.summary AS summary,
               d.keywords AS keywords,
               d.source_filename AS source_filename,
               collect(concept.name) AS concept_names
        ORDER BY d.topic
        """
        result = self.neo4j_session.run(
            query,
            course_id=course_id,
            database_=settings.neo4j_database,
        )

        documents: list[TeacherDocument] = []
        for record in result:
            documents.append(
                TeacherDocument(
                    doc_id=record["doc_id"],
                    topic=record["topic"],
                    summary=record["summary"],
                    keywords=record["keywords"],
                    source_filename=record["source_filename"],
                    concept_names=[c for c in record["concept_names"] if c],
                )
            )

        return documents

    def gather_recommendation_data(
        self,
        course_id: int,
        run_id: int,
        selected_book_id: int,
    ) -> RecommendationData | None:
        """One-shot fetch of all data needed for recommendation agents.

        Returns None if the ChapterAnalysisSummary doesn't exist yet.
        """
        summary = self.get_chapter_summary(run_id, selected_book_id)
        if summary is None:
            return None

        novel, overlap = self.extract_novel_and_overlap_concepts(summary)
        weak = self.extract_weak_course_concepts(summary)
        skills = self.extract_skills(summary)
        teacher_docs = self.fetch_teacher_documents(course_id)

        return RecommendationData(
            book_title=summary.book_title,
            novel_concepts=novel,
            overlap_concepts=overlap,
            weak_course_concepts=weak,
            skills=skills,
            teacher_documents=teacher_docs,
        )
