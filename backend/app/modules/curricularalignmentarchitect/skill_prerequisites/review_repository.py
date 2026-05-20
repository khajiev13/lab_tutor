from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from .review_models import PrerequisiteReview
from .schemas import PrerequisiteDraftEdge, PrerequisiteReviewStatus


class PrerequisiteReviewRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, course_id: int) -> PrerequisiteReview | None:
        return self.db.get(PrerequisiteReview, course_id)

    def get_or_create(self, course_id: int) -> PrerequisiteReview:
        review = self.get(course_id)
        if review is not None:
            return review

        review = PrerequisiteReview(course_id=course_id)
        self.db.add(review)
        self.db.flush()
        return review

    def save_draft(
        self,
        course_id: int,
        edges: list[PrerequisiteDraftEdge],
        status: PrerequisiteReviewStatus,
        isolated_skill_count: int,
        generated_edge_count: int | None = None,
        added_edge_count: int | None = None,
        removed_edge_count: int | None = None,
        isolated_skills_viewed: bool | None = None,
    ) -> PrerequisiteReview:
        review = self.get_or_create(course_id)

        review.review_status = status
        review.draft_edges = [edge.model_dump() for edge in edges]
        review.edge_count = len(edges)
        review.isolated_skill_count = isolated_skill_count
        if generated_edge_count is not None:
            review.generated_edge_count = generated_edge_count
        if added_edge_count is not None:
            review.added_edge_count = added_edge_count
        if removed_edge_count is not None:
            review.removed_edge_count = removed_edge_count
        if isolated_skills_viewed is not None:
            review.isolated_skills_viewed = isolated_skills_viewed
        review.updated_at = datetime.now(UTC)

        self._flush_refresh(review)
        return review

    def mark_generated(
        self,
        course_id: int,
        edges: list[PrerequisiteDraftEdge],
        isolated_skill_count: int,
    ) -> PrerequisiteReview:
        review = self.save_draft(
            course_id=course_id,
            edges=edges,
            status=PrerequisiteReviewStatus.NEEDS_REVIEW,
            isolated_skill_count=isolated_skill_count,
            generated_edge_count=len(edges),
            isolated_skills_viewed=False,
        )
        now = datetime.now(UTC)
        review.is_rebuilding = False
        review.last_generated_at = now
        review.approved_at = None
        review.approved_by = None
        review.updated_at = now

        self._flush_refresh(review)
        return review

    def mark_rebuilding(self, course_id: int) -> PrerequisiteReview:
        review = self.get_or_create(course_id)
        review.is_rebuilding = True
        review.updated_at = datetime.now(UTC)

        self._flush_refresh(review)
        return review

    def mark_stale(self, course_id: int) -> PrerequisiteReview:
        review = self.get_or_create(course_id)
        now = datetime.now(UTC)
        if review.review_status == PrerequisiteReviewStatus.APPROVED:
            review.review_status = PrerequisiteReviewStatus.STALE
        review.last_invalidated_at = now
        review.updated_at = now

        self._flush_refresh(review)
        return review

    def mark_approved(
        self,
        course_id: int,
        teacher_id: int,
        added_edge_count: int,
        removed_edge_count: int,
    ) -> PrerequisiteReview:
        review = self.get_or_create(course_id)
        now = datetime.now(UTC)
        review.review_status = PrerequisiteReviewStatus.APPROVED
        review.approved_by = teacher_id
        review.approved_at = now
        review.added_edge_count = added_edge_count
        review.removed_edge_count = removed_edge_count
        review.is_rebuilding = False
        review.updated_at = now

        self._flush_refresh(review)
        return review

    def _flush_refresh(self, review: PrerequisiteReview) -> None:
        self.db.flush()
        self.db.refresh(review)


def draft_edges_from_review(
    review: PrerequisiteReview | None,
) -> list[PrerequisiteDraftEdge]:
    if review is None:
        return []

    edges: list[PrerequisiteDraftEdge] = []
    for raw_edge in review.draft_edges or []:
        if isinstance(raw_edge, dict):
            edges.append(PrerequisiteDraftEdge.model_validate(raw_edge))
    return edges


def skill_names_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({str(row["name"]) for row in rows if row.get("name")})
