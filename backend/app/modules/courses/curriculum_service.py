from __future__ import annotations

from fastapi import Depends, HTTPException, status
from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import require_neo4j_session
from app.modules.auth.models import User
from app.modules.student_learning_path import neo4j_repository as student_path_neo4j

from .curriculum_neo4j_repository import CurriculumNeo4jRepository
from .curriculum_schemas import (
    BookSkillBankBook,
    BookSkillBankChapter,
    BookSkillBankSkill,
    ChapterRead,
    ConceptRead,
    CourseChapterRead,
    CurriculumResponse,
    JobPostingRead,
    LearningPathChapterStatusCounts,
    LearningPathSummary,
    MarketSkillBankJobPosting,
    MarketSkillBankSkill,
    SectionRead,
    SkillBanksResponse,
    SkillRead,
    SkillSelectionRange,
    SkillSource,
    StudentInsightDetailResponse,
    StudentInsightProfile,
    StudentInsightsOverviewResponse,
    StudentInsightsSummary,
    StudentInsightStudent,
    StudentInsightTopPosting,
    StudentInsightTopSkill,
    TranscriptDocumentRead,
)
from .neo4j_repository import CourseGraphRepository
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


def _safe_text(val: object, *, fallback: str = "") -> str:
    text = _first_str(val)
    return text if text else fallback


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
        self._neo4j_session = neo4j_session
        self._graph_repo = CurriculumNeo4jRepository(neo4j_session)
        self._course_graph_repo = CourseGraphRepository(neo4j_session)

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

    @staticmethod
    def _format_student_name(student: object) -> str:
        first_name = getattr(student, "first_name", "") or ""
        last_name = getattr(student, "last_name", "") or ""
        full_name = f"{first_name} {last_name}".strip()
        return full_name or getattr(student, "email", "Student")

    def _build_student_summary(
        self,
        *,
        student: User,
        selected_skill_count: int,
        interested_posting_count: int,
    ) -> StudentInsightStudent:
        return StudentInsightStudent(
            id=student.id,
            full_name=self._format_student_name(student),
            email=student.email,
            selected_skill_count=selected_skill_count,
            interested_posting_count=interested_posting_count,
            has_learning_path=selected_skill_count > 0,
        )

    @staticmethod
    def _summarize_learning_path(learning_path: dict) -> LearningPathSummary:
        chapter_status_counts = LearningPathChapterStatusCounts()
        for chapter in learning_path.get("chapters", []):
            status_name = chapter.get("quiz_status")
            if status_name == "quiz_required":
                chapter_status_counts.quiz_required += 1
            elif status_name == "learning":
                chapter_status_counts.learning += 1
            elif status_name == "completed":
                chapter_status_counts.completed += 1
            else:
                chapter_status_counts.locked += 1

        total_selected_skills = int(learning_path.get("total_selected_skills", 0) or 0)
        skills_with_resources = int(learning_path.get("skills_with_resources", 0) or 0)

        return LearningPathSummary(
            has_learning_path=total_selected_skills > 0,
            total_selected_skills=total_selected_skills,
            skills_with_resources=skills_with_resources,
            chapter_status_counts=chapter_status_counts,
        )

    def get_curriculum(self, *, course_id: int, teacher: User) -> CurriculumResponse:
        self._require_teacher_owns_course(course_id=course_id, teacher=teacher)

        raw = self._graph_repo.get_curriculum_tree(course_id)
        if raw is None:
            return CurriculumResponse(course_id=course_id)

        chapters: list[ChapterRead] = []
        for rec in raw["chapters"]:
            chapter_index = _safe_int(rec.get("chapter_index"))
            chapters.append(
                ChapterRead(
                    chapter_index=chapter_index,
                    title=_safe_text(
                        rec.get("chapter_title"),
                        fallback=f"Chapter {chapter_index}"
                        if chapter_index > 0
                        else "Untitled chapter",
                    ),
                    summary=rec.get("chapter_summary"),
                    sections=_parse_sections(rec.get("sections")),
                    skills=_parse_skills(
                        rec.get("book_skills", []),
                        rec.get("market_skills", []),
                    ),
                )
            )

        return CurriculumResponse(
            course_id=course_id,
            book_title=raw.get("book_title"),
            book_authors=raw.get("book_authors"),
            chapters=sorted(chapters, key=lambda c: c.chapter_index),
        )

    def get_skill_banks(self, *, course_id: int, teacher: User) -> SkillBanksResponse:
        self._require_teacher_owns_course(course_id=course_id, teacher=teacher)

        # ── Teacher transcripts ──
        raw_transcripts = self._graph_repo.get_teacher_transcripts(course_id)
        course_chapters = [
            CourseChapterRead(
                chapter_index=_safe_int(ch.get("chapter_index")),
                title=ch.get("title", ""),
                description=ch.get("description"),
                learning_objectives=ch.get("learning_objectives") or [],
                documents=[
                    TranscriptDocumentRead(
                        topic=doc.get("topic", ""),
                        source_filename=doc.get("source_filename"),
                    )
                    for doc in (ch.get("documents") or [])
                    if doc.get("topic")
                ],
            )
            for ch in raw_transcripts
            if ch.get("title")
        ]

        # ── Book skill bank ──
        raw_books = self._graph_repo.get_book_skill_bank(course_id)
        book_skill_bank = [
            BookSkillBankBook(
                book_id=b.get("book_id", ""),
                title=b.get("title", ""),
                authors=b.get("authors"),
                chapters=[
                    BookSkillBankChapter(
                        chapter_index=_safe_int(ch.get("chapter_index")),
                        chapter_id=ch.get("chapter_id", ""),
                        title=ch.get("title"),
                        skills=[
                            BookSkillBankSkill(
                                name=sk.get("name", ""),
                                description=sk.get("description"),
                            )
                            for sk in (ch.get("skills") or [])
                            if sk and sk.get("name")
                        ],
                    )
                    for ch in (b.get("chapters") or [])
                ],
            )
            for b in raw_books
            if b.get("title")
        ]

        # ── Market skill bank ──
        raw_jobs = self._graph_repo.get_market_skill_bank(course_id)
        market_skill_bank = [
            MarketSkillBankJobPosting(
                title=jp.get("title", ""),
                company=jp.get("company"),
                site=jp.get("site"),
                url=jp.get("url", ""),
                search_term=jp.get("search_term"),
                skills=[
                    MarketSkillBankSkill(
                        name=sk.get("name", ""),
                        category=sk.get("category"),
                        status=sk.get("status"),
                        priority=sk.get("priority"),
                        demand_pct=_safe_float(sk.get("demand_pct")),
                    )
                    for sk in (jp.get("skills") or [])
                    if sk and sk.get("name")
                ],
            )
            for jp in raw_jobs
            if jp.get("url")
        ]

        selection_range = SkillSelectionRange.model_validate(
            self._course_graph_repo.get_skill_selection_range(course_id=course_id)
        )

        return SkillBanksResponse(
            course_chapters=course_chapters,
            book_skill_bank=book_skill_bank,
            market_skill_bank=market_skill_bank,
            selection_range=selection_range,
        )

    def get_student_insights(
        self,
        *,
        course_id: int,
        teacher: User,
    ) -> StudentInsightsOverviewResponse:
        self._require_teacher_owns_course(course_id=course_id, teacher=teacher)

        enrolled_students = list(self._repo.list_course_students(course_id))
        if not enrolled_students:
            return StudentInsightsOverviewResponse(
                summary=StudentInsightsSummary(),
                students=[],
            )

        selected_skill_counter: dict[str, int] = {}
        interested_posting_counter: dict[str, int] = {}
        selected_skill_counts_by_student: dict[int, int] = {}
        interested_posting_counts_by_student: dict[int, int] = {}

        student_ids = [student.id for student in enrolled_students]
        posting_metadata: dict[str, dict[str, str | None]] = {}

        for student in enrolled_students:
            selected_map = student_path_neo4j.get_selected_skill_sources(
                self._neo4j_session,
                student.id,
                course_id,
            )
            interested_urls = student_path_neo4j.get_interested_posting_urls(
                self._neo4j_session,
                student.id,
                course_id,
                include_inferred_selected_postings=True,
            )

            selected_skill_counts_by_student[student.id] = len(selected_map)
            interested_posting_counts_by_student[student.id] = len(interested_urls)

            for skill_name in selected_map:
                selected_skill_counter[skill_name] = (
                    selected_skill_counter.get(skill_name, 0) + 1
                )

            if interested_urls:
                posting_metadata = {
                    **posting_metadata,
                    **student_path_neo4j.get_job_posting_metadata_by_urls(
                        self._neo4j_session,
                        interested_urls,
                    ),
                }

            for posting_url in interested_urls:
                interested_posting_counter[posting_url] = (
                    interested_posting_counter.get(posting_url, 0) + 1
                )

        students = [
            self._build_student_summary(
                student=student,
                selected_skill_count=selected_skill_counts_by_student.get(
                    student.id, 0
                ),
                interested_posting_count=interested_posting_counts_by_student.get(
                    student.id, 0
                ),
            )
            for student in enrolled_students
        ]

        top_selected_skills = [
            StudentInsightTopSkill(name=name, student_count=count)
            for name, count in sorted(
                selected_skill_counter.items(),
                key=lambda item: (-item[1], item[0].casefold()),
            )[:5]
        ]
        top_interested_postings = [
            StudentInsightTopPosting(
                url=url,
                title=posting_metadata.get(url, {}).get("title"),
                company=posting_metadata.get(url, {}).get("company"),
                student_count=count,
            )
            for url, count in sorted(
                interested_posting_counter.items(),
                key=lambda item: (
                    -item[1],
                    (
                        posting_metadata.get(item[0], {}).get("title") or item[0]
                    ).casefold(),
                ),
            )[:5]
        ]

        total_selected_skills = sum(selected_skill_counts_by_student.values())
        summary = StudentInsightsSummary(
            students_with_selections=sum(
                1
                for student_id in student_ids
                if selected_skill_counts_by_student.get(student_id, 0) > 0
            ),
            students_with_learning_paths=sum(
                1
                for student_id in student_ids
                if selected_skill_counts_by_student.get(student_id, 0) > 0
            ),
            avg_selected_skill_count=(
                round(total_selected_skills / len(enrolled_students), 1)
                if enrolled_students
                else 0.0
            ),
            top_selected_skills=top_selected_skills,
            top_interested_postings=top_interested_postings,
        )

        return StudentInsightsOverviewResponse(summary=summary, students=students)

    def get_student_insight_detail(
        self,
        *,
        course_id: int,
        teacher: User,
        student_id: int,
    ) -> StudentInsightDetailResponse:
        self._require_teacher_owns_course(course_id=course_id, teacher=teacher)

        student = self._repo.get_enrolled_student(course_id, student_id)
        if student is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student is not enrolled in this course",
            )

        skill_banks = student_path_neo4j.get_student_skill_banks(
            self._neo4j_session,
            student.id,
            course_id,
            include_inferred_selected_postings=True,
        )
        learning_path = student_path_neo4j.get_learning_path(
            self._neo4j_session,
            student.id,
            course_id,
        )

        return StudentInsightDetailResponse(
            student=StudentInsightProfile(
                id=student.id,
                full_name=self._format_student_name(student),
                email=student.email,
            ),
            skill_banks=skill_banks,
            learning_path_summary=self._summarize_learning_path(learning_path),
        )

    def update_skill_selection_range(
        self,
        *,
        teacher: User,
        course_id: int,
        min_skills: int,
        max_skills: int,
    ) -> SkillSelectionRange:
        self._require_teacher_owns_course(course_id=course_id, teacher=teacher)
        self._course_graph_repo.set_skill_selection_range(
            course_id=course_id,
            min_skills=min_skills,
            max_skills=max_skills,
        )
        return SkillSelectionRange.model_validate(
            self._course_graph_repo.get_skill_selection_range(course_id=course_id)
        )


def _get_course_repository(db: Session = Depends(get_db)) -> CourseRepository:
    return CourseRepository(db)


def get_curriculum_service(
    repo: CourseRepository = Depends(_get_course_repository),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
) -> CurriculumService:
    return CurriculumService(repo, neo4j_session)
