from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .review_sql_models import ConceptNormalizationReviewItem
from .schemas import MergeProposal, MergeProposalDecision, NormalizationReview


class ConceptNormalizationReviewSqlRepository:
    """SQL-backed staging for normalization review/proposals.

    Important behavior:
    - single pending review per course: creating a new review for a course deletes old rows
    - apply flow deletes rows (for that review/course) only after a fully successful apply
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _dumps_variants(variants: list[str]) -> str:
        return json.dumps([v for v in variants if v], ensure_ascii=False)

    @staticmethod
    def _loads_variants(payload: str) -> list[str]:
        try:
            raw = json.loads(payload or "[]")
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        return [str(v) for v in raw if isinstance(v, str) and v]

    def replace_course_review(
        self,
        *,
        course_id: int,
        review_id: str,
        created_by_user_id: int | None,
        proposals: list[MergeProposal],
        commit: bool = True,
    ) -> None:
        """Replace any existing pending review for a course with a new set of proposals."""
        # Enforce "single pending review per course".
        self._db.execute(
            delete(ConceptNormalizationReviewItem).where(
                ConceptNormalizationReviewItem.course_id == course_id
            )
        )

        created_at = datetime.now(UTC)
        for p in proposals:
            self._db.add(
                ConceptNormalizationReviewItem(
                    course_id=course_id,
                    review_id=review_id,
                    created_by_user_id=created_by_user_id,
                    created_at=created_at,
                    proposal_id=p.id,
                    concept_a=p.concept_a,
                    concept_b=p.concept_b,
                    canonical=p.canonical,
                    variants_json=self._dumps_variants(p.variants),
                    r=p.r or "",
                    decision=p.decision,
                    comment=p.comment or "",
                    decided_at=None,
                    decided_by_user_id=None,
                )
            )

        if commit:
            self._db.commit()
        else:
            self._db.flush()

    def get_review(
        self, *, review_id: str, course_id: int
    ) -> NormalizationReview | None:
        rows = self._db.scalars(
            select(ConceptNormalizationReviewItem)
            .where(
                ConceptNormalizationReviewItem.review_id == review_id,
                ConceptNormalizationReviewItem.course_id == course_id,
            )
            .order_by(
                ConceptNormalizationReviewItem.canonical.asc(),
                ConceptNormalizationReviewItem.concept_a.asc(),
                ConceptNormalizationReviewItem.concept_b.asc(),
            )
        ).all()
        if not rows:
            return None

        first = rows[0]
        proposals: list[MergeProposal] = []
        for r in rows:
            proposals.append(
                MergeProposal(
                    id=r.proposal_id,
                    concept_a=r.concept_a,
                    concept_b=r.concept_b,
                    canonical=r.canonical,
                    variants=self._loads_variants(r.variants_json),
                    r=r.r or "",
                    decision=r.decision or MergeProposalDecision.PENDING,
                    comment=r.comment or "",
                    applied=False,
                )
            )

        return NormalizationReview(
            id=review_id,
            course_id=course_id,
            status="pending",
            created_by_user_id=first.created_by_user_id,
            created_at=first.created_at.isoformat() if first.created_at else None,
            proposals=proposals,
            definitions={},
        )

    def update_decisions(
        self,
        *,
        review_id: str,
        course_id: int,
        user_id: int,
        decisions: list[dict[str, object]],
        commit: bool = True,
    ) -> int:
        if not decisions:
            return 0

        updated_count = 0
        now = datetime.now(UTC)

        for d in decisions:
            proposal_id = str(d.get("proposal_id") or "")
            decision = str(d.get("decision") or "")
            comment = str(d.get("comment") or "")
            if not proposal_id or decision not in {
                MergeProposalDecision.PENDING.value,
                MergeProposalDecision.APPROVED.value,
                MergeProposalDecision.REJECTED.value,
            }:
                continue

            res = self._db.execute(
                update(ConceptNormalizationReviewItem)
                .where(
                    ConceptNormalizationReviewItem.review_id == review_id,
                    ConceptNormalizationReviewItem.course_id == course_id,
                    ConceptNormalizationReviewItem.proposal_id == proposal_id,
                )
                .values(
                    decision=MergeProposalDecision(decision),
                    comment=comment or "",
                    decided_at=now,
                    decided_by_user_id=user_id,
                )
            )
            updated_count += int(res.rowcount or 0)

        if commit:
            self._db.commit()
        else:
            self._db.flush()

        return updated_count

    def list_approved_proposals(
        self, *, review_id: str, course_id: int
    ) -> list[dict[str, object]]:
        rows = self._db.scalars(
            select(ConceptNormalizationReviewItem)
            .where(
                ConceptNormalizationReviewItem.review_id == review_id,
                ConceptNormalizationReviewItem.course_id == course_id,
                ConceptNormalizationReviewItem.decision
                == MergeProposalDecision.APPROVED,
            )
            .order_by(
                ConceptNormalizationReviewItem.canonical.asc(),
                ConceptNormalizationReviewItem.proposal_id.asc(),
            )
        ).all()
        out: list[dict[str, object]] = []
        for r in rows:
            out.append(
                {
                    "proposal_id": r.proposal_id,
                    "canonical": r.canonical,
                    "variants": self._loads_variants(r.variants_json),
                }
            )
        return out

    def delete_review(
        self, *, review_id: str, course_id: int, commit: bool = True
    ) -> int:
        res = self._db.execute(
            delete(ConceptNormalizationReviewItem).where(
                ConceptNormalizationReviewItem.review_id == review_id,
                ConceptNormalizationReviewItem.course_id == course_id,
            )
        )
        deleted = int(res.rowcount or 0)
        if commit:
            self._db.commit()
        else:
            self._db.flush()
        return deleted
