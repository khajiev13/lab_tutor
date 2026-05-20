from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.curricularalignmentarchitect.models import (
    BookSelectionSession,
    SessionStatus,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_models import (
    PrerequisiteReview,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.schemas import (
    PrerequisiteReviewStatus,
)

from .models import Course, CourseMarketGateStatus, CoursePublicationStatus
from .schemas import (
    CourseReadinessRead,
    PrerequisiteReviewSummary,
    ReadinessGate,
    ReadinessNextAction,
)

BOOK_BLOCKER = "Complete the book skill bank."
MARKET_BLOCKER = "Complete the market skill bank."
PREREQUISITE_BLOCKER = "Review prerequisites."


class CourseReadinessService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _get_course(self, course_id: int) -> Course:
        course = self._db.get(Course, course_id)
        if course is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )
        return course

    def require_teacher(self, course_id: int, teacher_id: int) -> Course:
        course = self._get_course(course_id)
        if course.teacher_id != teacher_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to manage this course",
            )
        return course

    def get_readiness(self, course_id: int) -> CourseReadinessRead:
        course = self._get_course(course_id)
        book_complete = self._book_gate_complete(course_id)
        market_complete = course.market_gate_status in {
            CourseMarketGateStatus.COMPLETED,
            CourseMarketGateStatus.WAIVED,
        }
        review = self._get_prerequisite_review(course_id)
        prerequisite_complete = (
            review is not None
            and review.review_status == PrerequisiteReviewStatus.APPROVED
            and not review.is_rebuilding
        )

        blockers: list[str] = []
        if not book_complete:
            blockers.append(BOOK_BLOCKER)
        if not market_complete:
            blockers.append(MARKET_BLOCKER)
        if not prerequisite_complete:
            blockers.append(PREREQUISITE_BLOCKER)

        can_publish = not blockers
        availability_status = self._availability_status(course, can_publish)

        gates = [
            self._gate(
                "book",
                "Book skill bank",
                "complete" if book_complete else "ready",
                f"/courses/{course_id}/architect",
                "Book skill bank is complete."
                if book_complete
                else "Complete the book skill bank before publishing.",
            ),
            self._gate(
                "market",
                "Market skill bank",
                "complete"
                if market_complete
                else "ready"
                if book_complete
                else "locked",
                f"/courses/{course_id}/market-analyst",
                "Market skill bank is complete or waived."
                if market_complete
                else "Complete or waive the market skill bank before publishing.",
            ),
            self._gate(
                "prerequisites",
                "Prerequisites",
                "complete"
                if prerequisite_complete
                else "ready"
                if book_complete and market_complete
                else "locked",
                f"/courses/{course_id}/prerequisites",
                "Prerequisites are approved."
                if prerequisite_complete
                else "Review and approve prerequisites before publishing.",
            ),
            self._gate(
                "publish",
                "Publish",
                "complete"
                if course.publication_status == CoursePublicationStatus.PUBLISHED
                and can_publish
                else "ready"
                if can_publish
                else "locked",
                None,
                "Course is ready to publish."
                if can_publish
                else "Resolve readiness blockers before publishing.",
            ),
        ]

        return CourseReadinessRead(
            course_id=course.id,
            publication_status=course.publication_status,
            availability_status=availability_status,
            can_publish=can_publish,
            blockers=blockers,
            next_action=self._next_action(course, course_id, blockers, can_publish),
            gates=gates,
            prerequisite_review=self._prerequisite_summary(review),
        )

    def publish(self, course_id: int, teacher_id: int) -> Course:
        course = self.require_teacher(course_id, teacher_id)
        readiness = self.get_readiness(course_id)
        if not readiness.can_publish:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"blockers": readiness.blockers},
            )

        course.publication_status = CoursePublicationStatus.PUBLISHED
        self._db.add(course)
        self._db.commit()
        self._db.refresh(course)
        return course

    def unpublish(self, course_id: int, teacher_id: int) -> Course:
        course = self.require_teacher(course_id, teacher_id)
        course.publication_status = CoursePublicationStatus.DRAFT
        self._db.add(course)
        self._db.commit()
        self._db.refresh(course)
        return course

    def mark_market_gate_complete(self, course_id: int) -> Course:
        course = self._get_course(course_id)
        course.market_gate_status = CourseMarketGateStatus.COMPLETED
        self._db.add(course)
        self._db.flush()
        return course

    def waive_market_gate(self, course_id: int, teacher_id: int) -> Course:
        course = self.require_teacher(course_id, teacher_id)
        course.market_gate_status = CourseMarketGateStatus.WAIVED
        self._db.add(course)
        self._db.commit()
        self._db.refresh(course)
        return course

    def is_effectively_available(self, course_id: int) -> bool:
        course = self._get_course(course_id)
        if course.publication_status != CoursePublicationStatus.PUBLISHED:
            return False
        return self.get_readiness(course_id).can_publish

    def _book_gate_complete(self, course_id: int) -> bool:
        latest_session = self._db.scalar(
            select(BookSelectionSession)
            .where(BookSelectionSession.course_id == course_id)
            .order_by(BookSelectionSession.created_at.desc())
            .limit(1)
        )
        return (
            latest_session is not None
            and latest_session.status == SessionStatus.COMPLETED
        )

    def _get_prerequisite_review(self, course_id: int) -> PrerequisiteReview | None:
        return self._db.get(PrerequisiteReview, course_id)

    def _availability_status(self, course: Course, can_publish: bool) -> str:
        if course.publication_status == CoursePublicationStatus.DRAFT:
            return "draft"
        if can_publish:
            return "published"
        return "publishing_paused"

    def _next_action(
        self, course: Course, course_id: int, blockers: list[str], can_publish: bool
    ) -> ReadinessNextAction:
        if BOOK_BLOCKER in blockers:
            return ReadinessNextAction(
                id="book",
                label="Complete book skill bank",
                route=f"/courses/{course_id}/architect",
            )
        if MARKET_BLOCKER in blockers:
            return ReadinessNextAction(
                id="market",
                label="Complete market skill bank",
                route=f"/courses/{course_id}/market-analyst",
            )
        if PREREQUISITE_BLOCKER in blockers:
            return ReadinessNextAction(
                id="prerequisites",
                label="Review prerequisites",
                route=f"/courses/{course_id}/prerequisites",
            )
        if (
            can_publish
            and course.publication_status == CoursePublicationStatus.PUBLISHED
        ):
            return ReadinessNextAction(id="none", label="No action needed")
        if can_publish:
            return ReadinessNextAction(id="publish", label="Publish course")
        return ReadinessNextAction(id="none", label="No action needed")

    def _prerequisite_summary(
        self, review: PrerequisiteReview | None
    ) -> PrerequisiteReviewSummary:
        if review is None:
            return PrerequisiteReviewSummary(
                status=PrerequisiteReviewStatus.NOT_STARTED.value,
                edge_count=0,
                isolated_skill_count=0,
                last_generated_at=None,
            )

        return PrerequisiteReviewSummary(
            status=review.review_status.value,
            edge_count=review.edge_count,
            isolated_skill_count=review.isolated_skill_count,
            last_generated_at=review.last_generated_at,
        )

    def _gate(
        self,
        gate_id: str,
        label: str,
        gate_status: str,
        route: str | None,
        detail: str,
    ) -> ReadinessGate:
        return ReadinessGate(
            id=gate_id,
            label=label,
            status=gate_status,
            route=route,
            detail=detail,
        )


def get_course_readiness_service(
    db: Session = Depends(get_db),
) -> CourseReadinessService:
    return CourseReadinessService(db)
