"""Teacher-owned review decisions and immutable agent advice."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException

from .models import MarketAnalysisRun
from .repository import InvalidCandidateIds, MarketReviewRepository, RevisionConflict
from .schemas import (
    RecommendationProposal,
    SkillCandidate,
    SkillReview,
    SkillReviewDraft,
    SkillReviewRevision,
)
from .service import available_evidence_omissions


class SkillReviewService:
    def __init__(self, repository: MarketReviewRepository):
        self._repo = repository

    @staticmethod
    def thread_id(course_id: int, teacher_id: int) -> str:
        return f"mda-{teacher_id}-course-{course_id}"

    def require_teacher(self, course_id: int, teacher_id: int) -> None:
        if not self._repo.owns_course(course_id, teacher_id):
            raise HTTPException(404, "Course not found")

    @staticmethod
    def review_from_run(run: MarketAnalysisRun) -> SkillReview:
        manifest = run.candidate_manifest
        records = []
        for record in manifest.get("reconciliations", []):
            records.append(
                {
                    **{
                        key: record[key]
                        for key in (
                            "reconciliation_id",
                            "candidate_id",
                            "previous_candidate_ids",
                            "reason",
                            "previous_selected_candidate_ids",
                            "previous_excluded_candidate_ids",
                            "resolved",
                        )
                        if key in record
                    },
                    "previous_candidates": [
                        {
                            "candidate_id": item["candidate_id"],
                            "display_name": item.get("display_name")
                            or "Unknown candidate",
                        }
                        for item in record.get("historical_candidates", [])
                    ],
                }
            )
        omissions = available_evidence_omissions(run)
        return SkillReview(
            run_id=run.id,
            candidate_revision=run.candidate_revision,
            selection_revision=run.selection_revision,
            categories=manifest.get("categories", []),
            candidates=manifest.get("candidates", []),
            selected_candidate_ids=run.selected_candidate_ids,
            excluded_candidate_ids=run.excluded_candidate_ids,
            recommendations=run.recommendations,
            reconciliations=records,
            source_outcomes=run.source_outcomes,
            extraction_coverage={
                **deepcopy(run.extraction_coverage),
                "acknowledged": manifest.get("acknowledged_omissions", []) == omissions,
            },
            integration_review=run.integration_review,
            publication_revision=run.publication_revision,
            approved_references=run.approved_references,
        )

    def get_review(self, course_id: int, teacher_id: int) -> SkillReview:
        self.require_teacher(course_id, teacher_id)
        snapshot = (
            self._repo.load_active_snapshot(self.thread_id(course_id, teacher_id)) or {}
        )
        if not snapshot.get("run_id"):
            return SkillReview()
        run = self._repo.get_run(UUID(snapshot["run_id"]), course_id, teacher_id)
        return self.review_from_run(run) if run else SkillReview()

    def _active_run(
        self, course_id: int, teacher_id: int, body: SkillReviewRevision
    ) -> tuple[MarketAnalysisRun, dict]:
        self.require_teacher(course_id, teacher_id)
        run = self._repo.get_run(body.run_id, course_id, teacher_id, for_update=True)
        if run is None:
            raise HTTPException(422, "Analysis run does not belong to this course")
        snapshot = self._repo.load_active_snapshot(
            self.thread_id(course_id, teacher_id)
        )
        if not snapshot or snapshot.get("run_id") != str(run.id):
            raise HTTPException(409, "Review must belong to the active analysis")
        if (
            run.candidate_revision != body.expected_candidate_revision
            or run.selection_revision != body.expected_selection_revision
        ):
            raise HTTPException(
                409, "Analysis review has changed; reload before saving"
            )
        return run, snapshot

    @staticmethod
    def _confirmed(run: MarketAnalysisRun) -> bool:
        confirmation = run.selection_confirmation or {}
        omissions = available_evidence_omissions(run)
        return bool(run.selected_candidate_ids) and (
            confirmation.get("candidate_revision") == run.candidate_revision
            and confirmation.get("selection_revision") == run.selection_revision
            and confirmation.get("selected_candidate_ids") == run.selected_candidate_ids
            and confirmation.get("excluded_candidate_ids") == run.excluded_candidate_ids
            and confirmation.get("teacher_id") == run.teacher_id
            and not any(
                not r.get("resolved")
                for r in run.candidate_manifest.get("reconciliations", [])
            )
            and (
                not omissions
                or run.candidate_manifest.get("acknowledged_omissions") == omissions
            )
        )

    @classmethod
    def state_fields(cls, run: MarketAnalysisRun) -> dict:
        confirmed = cls._confirmed(run)
        lookup = {
            c["candidate_id"]: c for c in run.candidate_manifest.get("candidates", [])
        }
        curated = (
            [
                {
                    **SkillCandidate.model_validate(lookup[candidate_id]).model_dump(
                        mode="json"
                    ),
                    "name": lookup[candidate_id]["display_name"],
                    "category": lookup[candidate_id]["category_id"],
                }
                for candidate_id in run.selected_candidate_ids
                if candidate_id in lookup
            ]
            if confirmed
            else []
        )
        return {
            "run_id": str(run.id),
            "candidate_revision": run.candidate_revision,
            "selection_revision": run.selection_revision,
            "publication_revision": run.publication_revision,
            "selected_candidate_ids": deepcopy(run.selected_candidate_ids),
            "excluded_candidate_ids": deepcopy(run.excluded_candidate_ids),
            "selection_confirmation": deepcopy(run.selection_confirmation)
            if confirmed
            else None,
            "review_stage": "selection_confirmed" if confirmed else "draft",
            "curated_skills": curated,
        }

    def _commit_snapshot(
        self,
        run: MarketAnalysisRun,
        snapshot: dict,
        *,
        reset_mapping: bool = False,
        change_id: str | None = None,
    ) -> tuple[SkillReview, dict]:
        fields = self.state_fields(run)
        if reset_mapping:
            fields.update(
                {
                    key: None
                    for key in (
                        "curriculum_mapping",
                        "mapped_skills",
                        "final_skills",
                        "selected_for_insertion",
                        "skill_concepts",
                        "_cleaned_results",
                    )
                }
            )
        fields["skill_review_change_id"] = change_id or str(uuid4())
        updated = {**deepcopy(snapshot), **fields}
        review = self.review_from_run(run)
        try:
            self._repo.save_active_snapshot(
                self.thread_id(run.course_id, run.teacher_id), run.id, updated
            )
            self._repo.commit()
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return review, fields

    def save_draft(
        self, course_id: int, teacher_id: int, body: SkillReviewDraft
    ) -> SkillReview:
        _, snapshot = self._active_run(course_id, teacher_id, body)
        try:
            run = self._repo.save_draft(
                body.run_id,
                course_id,
                teacher_id,
                expected_candidate_revision=body.expected_candidate_revision,
                expected_selection_revision=body.expected_selection_revision,
                selected_candidate_ids=[
                    str(value) for value in body.selected_candidate_ids
                ],
                excluded_candidate_ids=[
                    str(value) for value in body.excluded_candidate_ids
                ],
                resolved_reconciliation_ids=[
                    str(value) for value in body.resolved_reconciliation_ids
                ],
            )
        except InvalidCandidateIds as exc:
            raise HTTPException(422, str(exc)) from exc
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        review, _ = self._commit_snapshot(run, snapshot, reset_mapping=True)
        return review

    def confirm_selection(
        self, course_id: int, teacher_id: int, body: SkillReviewRevision
    ) -> SkillReview:
        run, snapshot = self._active_run(course_id, teacher_id, body)
        if any(
            not r.get("resolved")
            for r in run.candidate_manifest.get("reconciliations", [])
        ):
            raise HTTPException(409, {"code": "reconciliation_required"})
        if not run.selected_candidate_ids:
            raise HTTPException(
                422, "Choose at least one candidate before confirmation"
            )
        candidate_ids = {
            c["candidate_id"] for c in run.candidate_manifest.get("candidates", [])
        }
        if set(run.selected_candidate_ids) - candidate_ids:
            raise HTTPException(409, {"code": "reconciliation_required"})
        omissions = available_evidence_omissions(run)
        if (
            omissions
            and run.candidate_manifest.get("acknowledged_omissions") != omissions
        ):
            raise HTTPException(
                409,
                {"code": "omissions_acknowledgement_required", "omissions": omissions},
            )
        self._repo.save_confirmation(
            run,
            {
                "teacher_id": teacher_id,
                "candidate_revision": run.candidate_revision,
                "selection_revision": run.selection_revision,
                "selected_candidate_ids": deepcopy(run.selected_candidate_ids),
                "excluded_candidate_ids": deepcopy(run.excluded_candidate_ids),
                "acknowledged_omissions": omissions,
                "confirmed_at": datetime.now(UTC).isoformat(),
            },
        )
        review, _ = self._commit_snapshot(run, snapshot)
        return review

    def continue_with_available_evidence(
        self, course_id: int, teacher_id: int, body: SkillReviewRevision
    ) -> SkillReview:
        run, snapshot = self._active_run(course_id, teacher_id, body)
        self._repo.acknowledge_omissions(run, available_evidence_omissions(run))
        review, _ = self._commit_snapshot(run, snapshot, reset_mapping=True)
        return review

    def create_recommendation(
        self,
        course_id: int,
        teacher_id: int,
        body: SkillReviewRevision,
        changes: list[dict],
    ) -> tuple[SkillReview, dict]:
        run, snapshot = self._active_run(course_id, teacher_id, body)
        proposal = RecommendationProposal(
            id=uuid4(),
            candidate_revision=run.candidate_revision,
            base_selection_revision=run.selection_revision,
            changes=changes,
        )
        ids = [str(c.candidate_id) for c in proposal.changes]
        current = {
            c["candidate_id"] for c in run.candidate_manifest.get("candidates", [])
        }
        if (
            not ids
            or len(set(ids)) != len(ids)
            or set(ids) - current
            or any(not c.reason.strip() for c in proposal.changes)
        ):
            raise HTTPException(
                422, "Proposal changes require current unique IDs and concrete reasons"
            )
        self._repo.append_recommendation(run, proposal.model_dump(mode="json"))
        return self._commit_snapshot(run, snapshot, change_id=str(proposal.id))

    def load_confirmed_selection(
        self, course_id: int, teacher_id: int, body: SkillReviewRevision
    ) -> dict:
        run, snapshot = self._active_run(course_id, teacher_id, body)
        if not self._confirmed(run):
            raise HTTPException(
                409, "Teacher must confirm the exact current draft before mapping"
            )
        _, fields = self._commit_snapshot(run, snapshot)
        return fields

    def rollback(self) -> None:
        self._repo.rollback()
