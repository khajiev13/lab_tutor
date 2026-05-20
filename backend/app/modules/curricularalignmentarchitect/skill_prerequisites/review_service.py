from __future__ import annotations

from typing import Protocol

from fastapi import HTTPException
from neo4j import Driver

from app.modules.courses.repository import CourseRepository

from .repository import (
    get_skill_prerequisites,
    load_review_skills_for_course,
    replace_skill_prerequisites,
)
from .review_repository import (
    PrerequisiteReviewRepository,
    draft_edges_from_review,
    skill_names_from_rows,
)
from .schemas import (
    PrerequisiteDraftEdge,
    PrerequisiteReviewMetadata,
    PrerequisiteReviewRead,
    PrerequisiteReviewStatus,
    PrerequisiteSkillRead,
)
from .validation import compute_isolated_skills, validate_prerequisite_edges


class PrerequisiteReviewGraphRepository(Protocol):
    def load_skills(self, course_id: int) -> list[dict]: ...

    def load_prerequisites(self, course_id: int) -> list[dict]: ...

    def replace_approved_edges(self, course_id: int, edges: list[dict]) -> int: ...


class Neo4jPrerequisiteReviewRepository:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def load_skills(self, course_id: int) -> list[dict]:
        return load_review_skills_for_course(self._driver, course_id)

    def load_prerequisites(self, course_id: int) -> list[dict]:
        return get_skill_prerequisites(self._driver, course_id)

    def replace_approved_edges(self, course_id: int, edges: list[dict]) -> int:
        return replace_skill_prerequisites(self._driver, course_id, edges)

    def close(self) -> None:
        self._driver.close()


class PrerequisiteReviewService:
    def __init__(
        self,
        course_repo: CourseRepository,
        review_repo: PrerequisiteReviewRepository,
        graph_repo: PrerequisiteReviewGraphRepository,
    ) -> None:
        self._course_repo = course_repo
        self._review_repo = review_repo
        self._graph_repo = graph_repo

    def close(self) -> None:
        close = getattr(self._graph_repo, "close", None)
        if close is not None:
            close()

    def _load_course(self, course_id: int):
        course = self._course_repo.get_by_id(course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        return course

    def require_teacher(self, course_id: int, teacher_id: int) -> None:
        course = self._load_course(course_id)
        if course.teacher_id != teacher_id:
            raise HTTPException(status_code=403, detail="Course access denied")

    def get_review(self, course_id: int) -> PrerequisiteReviewRead:
        self._load_course(course_id)
        review = self._review_repo.get(course_id)
        skills = self._graph_repo.load_skills(course_id)
        skill_names = skill_names_from_rows(skills)
        draft_edges = draft_edges_from_review(review)
        if self._should_seed_existing_graph_edges(review, draft_edges):
            existing_edges = self._draft_edges_from_existing_graph(
                course_id,
                set(skill_names),
            )
            if existing_edges:
                isolated_skills = compute_isolated_skills(skill_names, existing_edges)
                review = self._review_repo.save_draft(
                    course_id=course_id,
                    edges=existing_edges,
                    status=PrerequisiteReviewStatus.NEEDS_REVIEW,
                    isolated_skill_count=len(isolated_skills),
                    generated_edge_count=len(existing_edges),
                    isolated_skills_viewed=False,
                )
                draft_edges = draft_edges_from_review(review)
        isolated_skills = compute_isolated_skills(skill_names, draft_edges)
        validation = validate_prerequisite_edges(
            skill_names=skill_names,
            edges=draft_edges,
        )

        return PrerequisiteReviewRead(
            course_id=course_id,
            status=(
                review.review_status
                if review is not None
                else PrerequisiteReviewStatus.NOT_STARTED
            ),
            is_rebuilding=bool(review.is_rebuilding) if review is not None else False,
            skills=[PrerequisiteSkillRead.model_validate(skill) for skill in skills],
            draft_edges=draft_edges,
            isolated_skills=isolated_skills,
            validation=validation,
            metadata=PrerequisiteReviewMetadata(
                edge_count=len(draft_edges),
                generated_edge_count=(
                    review.generated_edge_count if review is not None else 0
                ),
                added_edge_count=review.added_edge_count if review is not None else 0,
                removed_edge_count=(
                    review.removed_edge_count if review is not None else 0
                ),
                isolated_skill_count=len(isolated_skills),
                last_generated_at=review.last_generated_at
                if review is not None
                else None,
                last_invalidated_at=(
                    review.last_invalidated_at if review is not None else None
                ),
                approved_at=review.approved_at if review is not None else None,
            ),
        )

    def _should_seed_existing_graph_edges(
        self,
        review,
        draft_edges: list[PrerequisiteDraftEdge],
    ) -> bool:
        if draft_edges:
            return False
        if review is None:
            return True
        return (
            review.review_status == PrerequisiteReviewStatus.NOT_STARTED
            and not review.is_rebuilding
        )

    def _draft_edges_from_existing_graph(
        self,
        course_id: int,
        skill_names: set[str],
    ) -> list[PrerequisiteDraftEdge]:
        edges: list[PrerequisiteDraftEdge] = []
        seen: set[tuple[str, str]] = set()
        for row in self._graph_repo.load_prerequisites(course_id):
            prereq_name = str(row.get("from_skill") or "").strip()
            dependent_name = str(row.get("to_skill") or "").strip()
            if (
                not prereq_name
                or not dependent_name
                or prereq_name not in skill_names
                or dependent_name not in skill_names
            ):
                continue

            key = (prereq_name, dependent_name)
            if key in seen:
                continue
            seen.add(key)

            confidence = row.get("confidence")
            if confidence not in {"high", "medium", "low"}:
                confidence = "medium"
            reasoning = str(
                row.get("reasoning")
                or "Imported from the existing course prerequisite graph."
            )
            edges.append(
                PrerequisiteDraftEdge(
                    prerequisite_name=prereq_name,
                    dependent_name=dependent_name,
                    confidence=confidence,
                    reasoning=reasoning,
                    source="ai",
                )
            )
        return edges

    def save_generated_draft(
        self, course_id: int, edges: list[PrerequisiteDraftEdge]
    ) -> PrerequisiteReviewRead:
        self._load_course(course_id)
        skill_names = skill_names_from_rows(self._graph_repo.load_skills(course_id))
        isolated_skills = compute_isolated_skills(skill_names, edges)
        self._review_repo.mark_generated(
            course_id=course_id,
            edges=edges,
            isolated_skill_count=len(isolated_skills),
        )
        return self.get_review(course_id)

    def save_teacher_draft(
        self,
        course_id: int,
        edges: list[PrerequisiteDraftEdge],
        isolated_skills_viewed: bool,
    ) -> PrerequisiteReviewRead:
        self._load_course(course_id)
        review = self._review_repo.get(course_id)
        generated_edge_count = review.generated_edge_count if review is not None else 0
        skill_names = skill_names_from_rows(self._graph_repo.load_skills(course_id))
        isolated_skills = compute_isolated_skills(skill_names, edges)
        added_edge_count = max(len(edges) - generated_edge_count, 0)
        removed_edge_count = max(generated_edge_count - len(edges), 0)
        teacher_edges = [
            edge.model_copy(update={"source": "teacher"}) for edge in edges
        ]

        self._review_repo.save_draft(
            course_id=course_id,
            edges=teacher_edges,
            status=PrerequisiteReviewStatus.NEEDS_REVIEW,
            isolated_skill_count=len(isolated_skills),
            added_edge_count=added_edge_count,
            removed_edge_count=removed_edge_count,
            isolated_skills_viewed=isolated_skills_viewed,
        )
        return self.get_review(course_id)

    def approve(self, course_id: int, teacher_id: int) -> PrerequisiteReviewRead:
        self.require_teacher(course_id, teacher_id)
        review = self._review_repo.get(course_id)
        if review is None:
            raise HTTPException(
                status_code=400,
                detail="Prerequisite review draft is missing",
            )
        if review.is_rebuilding:
            raise HTTPException(
                status_code=409,
                detail="Prerequisite generation is still rebuilding",
            )

        skills = self._graph_repo.load_skills(course_id)
        skill_names = skill_names_from_rows(skills)
        draft_edges = draft_edges_from_review(review)
        validation = validate_prerequisite_edges(
            skill_names=skill_names,
            edges=draft_edges,
        )
        if not validation.is_valid:
            raise HTTPException(
                status_code=400,
                detail=validation.model_dump(),
            )

        isolated_skills = compute_isolated_skills(skill_names, draft_edges)
        if isolated_skills and not review.isolated_skills_viewed:
            raise HTTPException(
                status_code=400,
                detail="Isolated skills must be reviewed before approval",
            )

        normalized_edges = [
            {
                "prereq_name": edge.prerequisite_name,
                "dependent_name": edge.dependent_name,
                "confidence": edge.confidence,
                "reasoning": edge.reasoning,
            }
            for edge in draft_edges
        ]
        self._graph_repo.replace_approved_edges(course_id, normalized_edges)
        self._review_repo.mark_approved(
            course_id=course_id,
            teacher_id=teacher_id,
            added_edge_count=review.added_edge_count,
            removed_edge_count=review.removed_edge_count,
        )
        return self.get_review(course_id)

    def invalidate(self, course_id: int) -> None:
        self._review_repo.mark_stale(course_id)
