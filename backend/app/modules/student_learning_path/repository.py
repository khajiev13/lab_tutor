"""SQL course catalog identities and immutable approved publication context."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.marketdemandanalyst.models import (
    CourseSkillReference,
    MarketAnalysisRun,
    MarketSkillApproval,
)
from app.modules.marketdemandanalyst.repository import MarketReviewRepository


class SkillCatalogRepository:
    def __init__(self, db: Session):
        self._db = db
        self.review = MarketReviewRepository(db)

    def references(self, course_id: int) -> list[CourseSkillReference]:
        return list(
            self._db.scalars(
                select(CourseSkillReference)
                .where(CourseSkillReference.course_id == course_id)
                .execution_options(populate_existing=True)
            )
        )

    def approved_items(self, course_id: int) -> tuple[list, dict[str, list[dict]]]:
        approvals = list(
            self._db.scalars(
                select(MarketSkillApproval)
                .where(MarketSkillApproval.course_id == course_id)
                .execution_options(populate_existing=True)
            )
        )
        historical = {}
        for approval in approvals:
            for item in approval.items:
                historical.setdefault(item["skill_reference_id"], []).append(item)
        active = [
            (approval, item)
            for approval in approvals
            if approval.is_active
            for item in approval.items
        ]
        return active, historical

    def run(self, run_id: UUID) -> MarketAnalysisRun | None:
        return self._db.get(MarketAnalysisRun, run_id, populate_existing=True)

    def legacy_reference(self, course_id: int, target: dict) -> None:
        self._db.execute(
            insert(CourseSkillReference)
            .values(
                course_id=course_id,
                target_identity=target["target_identity"],
                label=target["name"],
                source=target["source"],
                origin=target["origin"],
                projection_status="projected",
                available_for_new_selection=True,
            )
            .on_conflict_do_nothing(index_elements=["course_id", "target_identity"])
        )

    def commit(self) -> None:
        self._db.commit()
