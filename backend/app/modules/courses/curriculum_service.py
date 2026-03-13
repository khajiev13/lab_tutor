from __future__ import annotations

from fastapi import Depends, HTTPException, status
from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import require_neo4j_session
from app.modules.auth.models import User

from .curriculum_neo4j_repository import CurriculumNeo4jRepository
from .curriculum_schemas import (
    ChangelogEntry,
    ChapterRead,
    ConceptRead,
    CurriculumResponse,
    CurriculumWithChangelog,
    JobPostingRead,
    SectionRead,
    SkillRead,
    SkillSource,
)
from .repository import CourseRepository


def _safe_int(val: object) -> int:
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _safe_float(val: object) -> float | None:
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _first_str(val: object) -> str | None:
    """Extract a string from a value that may be a list (merged concepts)."""
    if isinstance(val, list):
        return val[0] if val else None
    return val if isinstance(val, str) else None


def _parse_concepts(raw: list[dict] | None) -> list[ConceptRead]:
    if not raw:
        return []
    out: list[ConceptRead] = []
    for c in raw:
        name = _first_str(c.get("name"))
        if not name:
            continue
        out.append(ConceptRead(name=name, description=_first_str(c.get("description"))))
    return out


def _parse_job_postings(raw: list[dict] | None) -> list[JobPostingRead]:
    if not raw:
        return []
    return [
        JobPostingRead(
            url=jp["url"],
            title=jp.get("title"),
            company=jp.get("company"),
            site=jp.get("site"),
        )
        for jp in raw
        if jp.get("url")
    ]


def _parse_skills(book_raw: list, market_raw: list) -> list[SkillRead]:
    skills: list[SkillRead] = []
    for s in book_raw:
        if s is None:
            continue
        skills.append(
            SkillRead(
                name=s["name"],
                source=SkillSource.BOOK,
                description=s.get("description"),
                concepts=_parse_concepts(s.get("concepts")),
            )
        )
    for s in market_raw:
        if s is None:
            continue
        skills.append(
            SkillRead(
                name=s["name"],
                source=SkillSource.MARKET_DEMAND,
                category=s.get("category"),
                frequency=_safe_int(s.get("frequency")),
                demand_pct=_safe_float(s.get("demand_pct")),
                priority=s.get("priority"),
                status=s.get("status"),
                reasoning=s.get("reasoning"),
                rationale=s.get("rationale"),
                created_at=s.get("created_at"),
                concepts=_parse_concepts(s.get("concepts")),
                job_postings=_parse_job_postings(s.get("job_postings")),
            )
        )
    return skills


def _parse_sections(raw: list[dict] | None) -> list[SectionRead]:
    if not raw:
        return []
    sections: list[SectionRead] = []
    for s in raw:
        if not s.get("title"):
            continue
        sections.append(
            SectionRead(
                section_index=_safe_int(s.get("section_index")),
                title=s["title"],
                concepts=_parse_concepts(s.get("concepts")),
            )
        )
    return sorted(sections, key=lambda x: x.section_index)


class CurriculumService:
    def __init__(self, repo: CourseRepository, neo4j_session: Neo4jSession) -> None:
        self._repo = repo
        self._graph_repo = CurriculumNeo4jRepository(neo4j_session)

    def _require_teacher_owns_course(self, *, course_id: int, teacher: User) -> None:
        course = self._repo.get_by_id(course_id)
        if course is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        if course.teacher_id != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this course curriculum",
            )

    def get_curriculum(
        self, *, course_id: int, teacher: User
    ) -> CurriculumWithChangelog:
        self._require_teacher_owns_course(course_id=course_id, teacher=teacher)

        raw = self._graph_repo.get_curriculum_tree(course_id)
        if raw is None:
            return CurriculumWithChangelog(
                curriculum=CurriculumResponse(course_id=course_id)
            )

        chapters: list[ChapterRead] = []
        for rec in raw["chapters"]:
            chapters.append(
                ChapterRead(
                    chapter_index=_safe_int(rec.get("chapter_index")),
                    title=rec.get("chapter_title", ""),
                    summary=rec.get("chapter_summary"),
                    sections=_parse_sections(rec.get("sections")),
                    skills=_parse_skills(
                        rec.get("book_skills", []),
                        rec.get("market_skills", []),
                    ),
                )
            )

        curriculum = CurriculumResponse(
            course_id=course_id,
            book_title=raw.get("book_title"),
            book_authors=raw.get("book_authors"),
            chapters=sorted(chapters, key=lambda c: c.chapter_index),
        )

        # Build changelog from market-skill insertions
        raw_log = self._graph_repo.get_changelog(course_id)
        changelog: list[ChangelogEntry] = []
        for entry in raw_log:
            skill_status = entry.get("skill_status", "")
            action = {
                "gap": "Added skill to fill gap",
                "new_topic_needed": "Added new topic skill",
                "covered": "Confirmed skill coverage",
            }.get(skill_status, "Inserted skill")

            changelog.append(
                ChangelogEntry(
                    timestamp=entry.get("timestamp", ""),
                    agent="Market Demand Analyst",
                    action=action,
                    details=f"{entry.get('skill_name', '')} ({entry.get('category', '')})",
                    chapter=entry.get("chapter"),
                    skill_name=entry.get("skill_name"),
                )
            )

        return CurriculumWithChangelog(curriculum=curriculum, changelog=changelog)


def _get_course_repository(db: Session = Depends(get_db)) -> CourseRepository:
    return CourseRepository(db)


def get_curriculum_service(
    repo: CourseRepository = Depends(_get_course_repository),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
) -> CurriculumService:
    return CurriculumService(repo, neo4j_session)
