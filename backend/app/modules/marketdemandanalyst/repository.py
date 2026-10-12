"""SQL persistence for disposable conversations and durable analysis runs."""

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from .evidence import redact_snapshot_content, snapshot_ids
from .models import (
    CourseSkillEvidence,
    CourseSkillReference,
    MarketAnalysisRun,
    MarketEvidenceRedaction,
    MarketSkillApproval,
    MarketVacancySnapshot,
    MDAThreadState,
)
from .schemas import ExecutionStatus, ProviderVacancy, safe_provider_payload


class RevisionConflict(ValueError):
    """The teacher or producer attempted to write an outdated revision."""


class InvalidCandidateIds(ValueError):
    """The selection contains foreign, duplicate, or overlapping candidate IDs."""


class MarketReviewRepository:
    def __init__(self, db: Session):
        self._db = db

    def owns_course(self, course_id: int, teacher_id: int) -> bool:
        from app.modules.courses.models import Course

        return (
            self._db.scalar(
                select(Course.id).where(
                    Course.id == course_id, Course.teacher_id == teacher_id
                )
            )
            is not None
        )

    def load_active_snapshot(self, thread_id: str) -> dict | None:
        return self.sanitize_source_content(
            self._db.scalar(
                select(MDAThreadState.state_json).where(
                    MDAThreadState.thread_id == thread_id
                )
            )
        )

    def save_active_snapshot(
        self, thread_id: str, run_id: UUID, snapshot: dict
    ) -> None:
        result = self._db.execute(
            update(MDAThreadState)
            .where(
                MDAThreadState.thread_id == thread_id,
                MDAThreadState.state_json["run_id"].astext == str(run_id),
            )
            .values(
                state_json=self.sanitize_source_content(snapshot), updated_at=func.now()
            )
        )
        if result.rowcount != 1:
            raise RevisionConflict("Review must belong to the active analysis")

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def save_confirmation(self, run: MarketAnalysisRun, confirmation: dict) -> None:
        run.selection_confirmation = deepcopy(confirmation)
        run.integration_review = None
        self._db.flush()

    def acknowledge_omissions(
        self, run: MarketAnalysisRun, omissions: list[str]
    ) -> None:
        run.candidate_manifest = {
            **deepcopy(run.candidate_manifest),
            "acknowledged_omissions": omissions,
        }
        run.selection_confirmation = None
        run.integration_review = None
        self._db.flush()

    def append_recommendation(self, run: MarketAnalysisRun, proposal: dict) -> None:
        run.recommendations = [*deepcopy(run.recommendations), deepcopy(proposal)]
        self._db.flush()

    def create_run(
        self, course_id: int, teacher_id: int, config: dict
    ) -> MarketAnalysisRun:
        run = MarketAnalysisRun(
            course_id=course_id,
            teacher_id=teacher_id,
            approval_contract_version=1,
            config=deepcopy(config),
        )
        self._db.add(run)
        self._db.flush()
        return run

    def update_configuration(self, run: MarketAnalysisRun, config: dict) -> None:
        run.config = deepcopy(config)
        self._db.flush()

    def save_configuration_snapshot(self, thread_id: str, snapshot: dict) -> None:
        """Save the active run pointer/state in the configuration transaction."""
        snapshot = self.sanitize_source_content(snapshot)
        self._db.execute(
            insert(MDAThreadState)
            .values(thread_id=thread_id, state_json=deepcopy(snapshot))
            .on_conflict_do_update(
                index_elements=["thread_id"],
                set_={"state_json": deepcopy(snapshot), "updated_at": func.now()},
            )
        )

    def get_run(
        self, run_id: UUID, course_id: int, teacher_id: int, *, for_update: bool = False
    ) -> MarketAnalysisRun | None:
        query = (
            select(MarketAnalysisRun)
            .where(
                MarketAnalysisRun.id == run_id,
                MarketAnalysisRun.course_id == course_id,
                MarketAnalysisRun.teacher_id == teacher_id,
            )
            .execution_options(populate_existing=True)
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self._db.scalar(query)

    def lock_vacancy_lifecycle(self) -> None:
        """Serialize short evidence write/purge transactions until commit/rollback.

        Acquire before run row locks when combining snapshot and manifest writes.
        Provider, LLM and embedding work must stay outside this transaction.
        """
        self._db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": "marketdemandanalyst:vacancy_lifecycle"},
        )

    def upsert_vacancy_snapshot(
        self, run_id: UUID, record: ProviderVacancy
    ) -> MarketVacancySnapshot:
        from .job_sources import vacancy_content_hash, vacancy_identity

        # One lifecycle lock remains held across every snapshot in this batch.
        self.lock_vacancy_lifecycle()
        identity = vacancy_identity(record)
        run = self._db.scalar(
            select(MarketAnalysisRun)
            .where(MarketAnalysisRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise LookupError("Analysis run not found")
        if "jobs" not in run.config.get(
            "evidence_sources", ["jobs"]
        ) or record.provider not in run.config.get("sources", ["indeed", "linkedin"]):
            raise ValueError("Vacancy provider was not selected for this analysis")
        digest = vacancy_content_hash(record)
        snapshot = self._db.scalar(
            select(MarketVacancySnapshot)
            .where(
                MarketVacancySnapshot.run_id == run_id,
                MarketVacancySnapshot.provider == record.provider,
                MarketVacancySnapshot.identity == identity,
                MarketVacancySnapshot.content_hash == digest,
            )
            .execution_options(populate_existing=True)
        )
        tombstone = self._db.scalar(
            select(MarketVacancySnapshot)
            .where(
                MarketVacancySnapshot.provider == record.provider,
                MarketVacancySnapshot.identity == identity,
                MarketVacancySnapshot.purged_at.is_not(None),
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if snapshot is not None:
            snapshot.query_membership = list(
                dict.fromkeys([*snapshot.query_membership, *record.query_membership])
            )
            snapshot.source_urls = list(
                dict.fromkeys(
                    [*snapshot.source_urls, *record.source_urls, record.original_url]
                )
            )
            snapshot.last_observed_at = record.retrieved_at
            self._db.flush()
            return snapshot
        snapshot = MarketVacancySnapshot(
            run_id=run_id,
            provider=record.provider,
            native_id=record.native_id,
            identity=identity,
            content_hash=digest,
            original_url=record.original_url,
            source_urls=list(dict.fromkeys([*record.source_urls, record.original_url])),
            title=record.title,
            company=record.company,
            raw_payload={} if tombstone else safe_provider_payload(record.raw_payload),
            original_description=None if tombstone else record.original_description,
            description_text=None if tombstone else record.description_text,
            skill_tags=[] if tombstone else record.skill_tags,
            returned_dates=record.returned_dates,
            status="purged" if tombstone else record.status,
            retrieved_at=record.retrieved_at,
            last_observed_at=record.retrieved_at,
            query_membership=record.query_membership,
            demand_identity=record.demand_identity or f"{record.provider}:{identity}",
            purged_at=tombstone.purged_at if tombstone else None,
            purge_reason=tombstone.purge_reason if tombstone else None,
        )
        self._db.add(snapshot)
        run.integration_review = None
        self._db.flush()
        return snapshot

    def get_vacancy_snapshot(
        self, snapshot_id: UUID, course_id: int, teacher_id: int
    ) -> MarketVacancySnapshot | None:
        return self._db.scalar(
            select(MarketVacancySnapshot)
            .join(MarketAnalysisRun)
            .where(
                MarketVacancySnapshot.id == snapshot_id,
                MarketAnalysisRun.course_id == course_id,
                MarketAnalysisRun.teacher_id == teacher_id,
            )
            .execution_options(populate_existing=True)
        )

    def purge_vacancy_content(self, snapshot_id: UUID, *, reason: str) -> int:
        if not reason.strip():
            raise ValueError("A provider lifecycle removal reason is required")
        self.lock_vacancy_lifecycle()
        snapshot = self._db.get(
            MarketVacancySnapshot, snapshot_id, populate_existing=True
        )
        if snapshot is None:
            raise LookupError("Vacancy snapshot not found")
        copies = list(
            self._db.scalars(
                select(MarketVacancySnapshot)
                .where(
                    MarketVacancySnapshot.provider == snapshot.provider,
                    MarketVacancySnapshot.identity == snapshot.identity,
                )
                .execution_options(populate_existing=True)
            )
        )
        run_ids = sorted({item.run_id for item in copies})
        runs = list(
            self._db.scalars(
                select(MarketAnalysisRun)
                .where(MarketAnalysisRun.id.in_(run_ids))
                .order_by(MarketAnalysisRun.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        for run in runs:
            run.integration_review = None
        affected_references = set(
            self._db.scalars(
                select(CourseSkillEvidence.skill_reference_id).where(
                    CourseSkillEvidence.vacancy_snapshot_id.in_(
                        [item.id for item in copies]
                    )
                )
            )
        )
        now = datetime.now(UTC)
        for item in copies:
            item.raw_payload = {}
            item.original_description = None
            item.description_text = None
            item.skill_tags = []
            item.status = "purged"
            item.purged_at = item.purged_at or now
            item.purge_reason = reason
        removed_ids = {str(item.id) for item in copies}
        for run in runs:
            run.candidate_manifest = redact_snapshot_content(
                run.candidate_manifest, removed_ids
            )
        bindings = list(
            self._db.scalars(
                select(CourseSkillEvidence).where(
                    CourseSkillEvidence.skill_reference_id.in_(affected_references)
                )
            )
        )
        for binding in bindings:
            binding.provenance = redact_snapshot_content(
                binding.provenance, removed_ids
            )
        approvals = list(
            self._db.scalars(
                select(MarketSkillApproval).where(
                    MarketSkillApproval.id.in_(
                        {binding.approval_id for binding in bindings}
                    )
                )
            )
        )
        for approval in approvals:
            approval.items = redact_snapshot_content(approval.items, removed_ids)
        for thread in self._db.scalars(select(MDAThreadState)):
            if snapshot_ids(thread.state_json) & removed_ids:
                thread.state_json = redact_snapshot_content(
                    thread.state_json, removed_ids
                )
        # Sessions disable autoflush. Persist tombstones before freshness reads
        # with populate_existing can reload the old retained source content.
        self._db.flush()
        # Availability follows surviving specific evidence, rather than whether
        # an unrelated run sharing this reference lost one source.
        from .review_service import qualifying_vacancy_bindings

        eligible = set()
        available = set()
        for approval in approvals:
            if not approval.is_active:
                continue
            run = self._db.get(MarketAnalysisRun, approval.run_id)
            for item in approval.items:
                refs = self.vacancy_snapshots_by_ids(
                    [r["snapshot_id"] for r in item["vacancy_bindings"]]
                )
                candidate = {
                    **item["candidate"],
                    "identity_key": item.get("identity_key"),
                }
                if qualifying_vacancy_bindings(
                    run,
                    candidate,
                    item["target"],
                    refs,
                    trusted_observations=item.get("validated_observations", []),
                ):
                    eligible.add((approval.id, item["candidate_id"]))
                    available.add(item["skill_reference_id"])
        references = list(
            self._db.scalars(
                select(CourseSkillReference)
                .where(CourseSkillReference.id.in_(affected_references))
                .with_for_update()
            )
        )
        for reference in references:
            reference.display_data = redact_snapshot_content(
                reference.display_data, removed_ids
            )
            reference.available_for_new_selection = (
                reference.projection_status == "projected"
                and str(reference.id) in available
            )
        for run in self._db.scalars(
            select(MarketAnalysisRun).where(
                MarketAnalysisRun.course_id.in_({row.course_id for row in references})
            )
        ):
            summaries = deepcopy(run.approved_references)
            for summary in summaries:
                reference = next(
                    (r for r in references if str(r.id) == summary["reference_id"]),
                    None,
                )
                if reference is not None:
                    summary["available_for_new_selection"] = (
                        reference.available_for_new_selection
                    )
            run.approved_references = summaries
        run_map = {run.id: run for run in runs}
        for snapshot in copies:
            course_id = run_map[snapshot.run_id].course_id
            job = self._db.get(MarketEvidenceRedaction, snapshot.id)
            if job is None:
                job = MarketEvidenceRedaction(
                    snapshot_id=snapshot.id, course_id=course_id
                )
                self._db.add(job)
            job.evidence_payload = {
                "snapshot_id": str(snapshot.id),
                "provider": snapshot.provider,
                "original_url": snapshot.original_url,
                "retrieved_at": snapshot.retrieved_at.isoformat(),
                "status": "purged",
                "content_removed": True,
                "content_hash": snapshot.content_hash,
            }
            job.reference_states = [
                {"reference_id": str(r.id), "available": r.available_for_new_selection}
                for r in references
                if r.course_id == course_id
            ]
            job.inactive_binding_ids = [
                str(b.id)
                for b in bindings
                if b.course_id == course_id
                and (
                    str(b.vacancy_snapshot_id) in removed_ids
                    or (b.approval_id, str(b.candidate_id)) not in eligible
                )
            ]
            job.projection_status = "pending"
            job.projection_error = None
        self._db.flush()
        return len(copies)

    def sanitize_source_content(self, value):
        ids = []
        for value_id in snapshot_ids(value):
            try:
                ids.append(UUID(value_id))
            except ValueError:
                continue
        removed = (
            {
                str(row)
                for row in self._db.scalars(
                    select(MarketVacancySnapshot.id).where(
                        MarketVacancySnapshot.id.in_(ids),
                        MarketVacancySnapshot.purged_at.is_not(None),
                    )
                )
            }
            if ids
            else set()
        )
        return redact_snapshot_content(value, removed)

    def pending_redactions(self, course_id: int) -> list[MarketEvidenceRedaction]:
        return list(
            self._db.scalars(
                select(MarketEvidenceRedaction)
                .where(
                    MarketEvidenceRedaction.course_id == course_id,
                    MarketEvidenceRedaction.projection_status != "projected",
                )
                .execution_options(populate_existing=True)
            )
        )

    def finish_redactions(
        self, snapshot_ids: list[UUID], status: str, *, error: str | None = None
    ) -> None:
        for job in self._db.scalars(
            select(MarketEvidenceRedaction)
            .where(MarketEvidenceRedaction.snapshot_id.in_(snapshot_ids))
            .with_for_update()
        ):
            job.projection_status = status
            job.projection_error = error
        self._db.flush()

    def update_manifest(
        self,
        run_id: UUID,
        course_id: int,
        teacher_id: int,
        *,
        expected_candidate_revision: int,
        candidates: list[dict],
        categories: list[dict] | None = None,
    ) -> MarketAnalysisRun:
        run = self._locked_run(
            run_id, course_id, teacher_id, expected_candidate_revision
        )
        ids = [str(item["candidate_id"]) for item in candidates]
        if len(set(ids)) != len(ids):
            raise InvalidCandidateIds("Duplicate candidate IDs")
        for candidate_id in ids:
            UUID(candidate_id)
        run.candidate_manifest = deepcopy(
            {"candidates": candidates, "categories": categories or []}
        )
        run.candidate_revision += 1
        run.selection_confirmation = None
        run.integration_review = None
        self._db.flush()
        return run

    def save_draft(
        self,
        run_id: UUID,
        course_id: int,
        teacher_id: int,
        *,
        expected_candidate_revision: int,
        expected_selection_revision: int,
        selected_candidate_ids: list[str],
        excluded_candidate_ids: list[str],
        resolved_reconciliation_ids: list[str] | None = None,
    ) -> MarketAnalysisRun:
        run = self._locked_run(
            run_id,
            course_id,
            teacher_id,
            expected_candidate_revision,
            expected_selection_revision,
        )
        selected = [str(value) for value in selected_candidate_ids]
        excluded = [str(value) for value in excluded_candidate_ids]
        candidates = {
            str(item["candidate_id"])
            for item in run.candidate_manifest.get("candidates", [])
        }
        if (
            len(set(selected)) != len(selected)
            or len(set(excluded)) != len(excluded)
            or set(selected) & set(excluded)
            or (set(selected) | set(excluded)) - candidates
        ):
            raise InvalidCandidateIds(
                "Selection IDs must be current, unique, and disjoint"
            )
        resolved_ids = [str(value) for value in resolved_reconciliation_ids or []]
        manifest = deepcopy(run.candidate_manifest)
        records = manifest.get("reconciliations", [])
        owned_ids = {r["reconciliation_id"] for r in records}
        if len(set(resolved_ids)) != len(resolved_ids) or set(resolved_ids) - owned_ids:
            raise InvalidCandidateIds("Reconciliation IDs must be current and unique")
        decisions = {candidate_id: candidate_id for candidate_id in candidates}
        for record in records:
            if record["reconciliation_id"] not in resolved_ids:
                continue
            record["resolved"] = True
            for old_id in record.get("previous_candidate_ids", []):
                decisions[old_id] = record.get("candidate_id")
        for item in manifest.get("candidate_history", []):
            candidate_id = str(item["candidate_id"])
            if candidate_id in decisions:
                target_id = decisions[candidate_id]
                item["selected"] = target_id in selected
                item["excluded"] = target_id in excluded
        manifest["reconciliation_required"] = any(
            not r.get("resolved") for r in records
        )
        manifest["selected_candidate_ids"] = selected
        manifest["excluded_candidate_ids"] = excluded
        run.candidate_manifest = manifest
        run.selected_candidate_ids = selected
        run.excluded_candidate_ids = excluded
        run.selection_revision += 1
        run.selection_confirmation = None
        run.integration_review = None
        self._db.flush()
        return run

    def _locked_run(
        self,
        run_id: UUID,
        course_id: int,
        teacher_id: int,
        candidate_revision: int,
        selection_revision: int | None = None,
    ) -> MarketAnalysisRun:
        run = self.get_run(run_id, course_id, teacher_id, for_update=True)
        if run is None:
            raise LookupError("Analysis run not found")
        if run.candidate_revision != candidate_revision or (
            selection_revision is not None
            and run.selection_revision != selection_revision
        ):
            raise RevisionConflict("Analysis review has changed; reload before saving")
        return run

    def has_analysis_run(self, course_id: int) -> bool:
        return (
            self._db.scalar(
                select(MarketAnalysisRun.id)
                .where(MarketAnalysisRun.course_id == course_id)
                .limit(1)
            )
            is not None
        )

    def lock_course_publication(self, course_id: int) -> None:
        self._db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": f"marketdemandanalyst:projection:{course_id}"},
        )

    def vacancy_evidence(
        self, run: MarketAnalysisRun
    ) -> dict[str, MarketVacancySnapshot]:
        ids = {
            UUID(str(ref["snapshot_id"]))
            for c in run.candidate_manifest.get("candidates", [])
            for ref in c.get("evidence_references", [])
        }
        return {
            str(row.id): row
            for row in self._db.scalars(
                select(MarketVacancySnapshot)
                .where(MarketVacancySnapshot.id.in_(ids))
                .execution_options(populate_existing=True)
            )
        }

    def workspace_vacancies(
        self, run_id: UUID, snapshot_ids: list[UUID]
    ) -> dict[str, MarketVacancySnapshot]:
        """Bound source reads to the requested owned run, never another course."""
        # Twenty explicit candidates plus a separate focus, two sources each.
        if len(snapshot_ids) > 42:
            raise ValueError("Workspace posting read exceeds its bound")
        return {
            str(row.id): row
            for row in self._db.scalars(
                select(MarketVacancySnapshot)
                .where(
                    MarketVacancySnapshot.run_id == run_id,
                    MarketVacancySnapshot.id.in_(snapshot_ids),
                )
                .execution_options(populate_existing=True)
            )
        }

    def onet_evidence(self, run: MarketAnalysisRun) -> dict:
        from app.modules.occupation_reference.models import OnetEvidence

        ids = {
            UUID(str(a["evidence"]["id"]))
            for c in run.candidate_manifest.get("candidates", [])
            for a in c.get("onet_associations", [])
            if a.get("evidence", {}).get("id")
        }
        return {
            str(row.id): row
            for row in self._db.scalars(
                select(OnetEvidence)
                .where(OnetEvidence.id.in_(ids))
                .execution_options(populate_existing=True)
            )
        }

    def save_integration_review(
        self, run: MarketAnalysisRun, review: dict | None
    ) -> None:
        run.integration_review = deepcopy(review)
        self._db.flush()

    def approval_by_digest(
        self, run_id: UUID, digest: str
    ) -> MarketSkillApproval | None:
        return self._db.scalar(
            select(MarketSkillApproval).where(
                MarketSkillApproval.run_id == run_id,
                MarketSkillApproval.review_digest == digest,
            )
        )

    def resolve_course_skill_reference(
        self, course_id: int, target: dict
    ) -> CourseSkillReference:
        row = self._db.scalar(
            select(CourseSkillReference)
            .where(
                CourseSkillReference.course_id == course_id,
                CourseSkillReference.target_identity == target["identity"],
            )
            .with_for_update()
        )
        if row is not None:
            if (row.label, row.source, row.origin) != (
                target["label"],
                target["source"],
                target["origin"],
            ):
                raise ValueError(
                    "Verified target differs from its existing course reference"
                )
            return row
        row = CourseSkillReference(
            course_id=course_id,
            target_identity=target["identity"],
            label=target["label"],
            source=target["source"],
            origin=target["origin"],
        )
        self._db.add(row)
        self._db.flush()
        return row

    def persist_approval(
        self, run: MarketAnalysisRun, review: dict, items: list[dict]
    ) -> MarketSkillApproval:
        old = list(
            self._db.scalars(
                select(MarketSkillApproval).where(
                    MarketSkillApproval.run_id == run.id,
                    MarketSkillApproval.is_active.is_(True),
                )
            )
        )
        affected = {
            UUID(ref_id)
            for approval in old
            for ref_id in approval.affected_reference_ids
        }
        for approval in old:
            approval.is_active = False
        run.publication_revision += 1
        approval = MarketSkillApproval(
            course_id=run.course_id,
            run_id=run.id,
            teacher_id=run.teacher_id,
            revision=run.publication_revision,
            review_digest=review["review_digest"],
            withdrawal=bool(review.get("withdrawal")),
            items=deepcopy(items),
        )
        self._db.add(approval)
        self._db.flush()
        summary = []
        for item in items:
            reference = self.resolve_course_skill_reference(
                run.course_id, item["target"]
            )
            affected.add(reference.id)
            item["skill_reference_id"] = str(reference.id)
            reference.chapters = deepcopy(item["chapters"])
            reference.display_data = deepcopy(item["candidate"])
            summary.append(
                {
                    "reference_id": str(reference.id),
                    "label": reference.label,
                    "category": item["candidate"]["category_id"],
                    "source": reference.source,
                    "origin": reference.origin,
                    "qualifying_posting_links": item["qualifying_posting_links"],
                    "projection_status": "pending",
                    "available_for_new_selection": False,
                }
            )
            for source, bindings in (
                ("jobs", item["vacancy_bindings"]),
                ("onet", item["onet_bindings"]),
            ):
                for binding in bindings:
                    evidence_id = (
                        binding["snapshot_id"]
                        if source == "jobs"
                        else binding["evidence"]["id"]
                    )
                    key = f"{approval.id}:{item['candidate_id']}:{reference.id}:{source}:{evidence_id}"
                    self._db.add(
                        CourseSkillEvidence(
                            course_id=run.course_id,
                            skill_reference_id=reference.id,
                            approval_id=approval.id,
                            run_id=run.id,
                            candidate_id=UUID(item["candidate_id"]),
                            mapping_relation=binding.get("relation", "equivalent"),
                            rationale=item.get("rationale", ""),
                            provenance=deepcopy(binding),
                            binding_key=key,
                            vacancy_snapshot_id=UUID(evidence_id)
                            if source == "jobs"
                            else None,
                            onet_evidence_id=UUID(evidence_id)
                            if source == "onet"
                            else None,
                        )
                    )
        approval.items = deepcopy(items)
        approval.affected_reference_ids = [str(value) for value in sorted(affected)]
        for reference in self._db.scalars(
            select(CourseSkillReference)
            .where(CourseSkillReference.id.in_(affected))
            .with_for_update()
        ):
            reference.approved_revision += 1
            reference.projection_status = "pending"
            reference.available_for_new_selection = False
        summaries = {}
        for row in summary:
            existing = summaries.setdefault(row["reference_id"], row)
            existing["qualifying_posting_links"] = sorted(
                set(existing["qualifying_posting_links"])
                | set(row["qualifying_posting_links"])
            )
        run.approved_references = list(summaries.values())
        run.lifecycle = "withdrawn" if approval.withdrawal else "approved"
        self._db.flush()
        return approval

    def vacancy_snapshots_by_ids(self, ids: list[str]) -> dict:
        return {
            str(row.id): row
            for row in self._db.scalars(
                select(MarketVacancySnapshot)
                .where(MarketVacancySnapshot.id.in_([UUID(value) for value in ids]))
                .execution_options(populate_existing=True)
            )
        }

    def acquire_projection(self, course_id: int) -> Connection | None:
        # Session locks protect the evidence throughout external graph work
        # without an open SQL transaction, in the same lifecycle-before-course
        # order as approval/purge. Never pool a connection retaining these locks.
        connection = self._db.get_bind().connect()
        scopes = [
            "marketdemandanalyst:vacancy_lifecycle",
            f"marketdemandanalyst:projection:{course_id}",
        ]
        acquired = []
        try:
            for scope in scopes:
                locked = connection.scalar(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:scope, 0))"),
                    {"scope": scope},
                )
                connection.commit()
                if not locked:
                    for prior in reversed(acquired):
                        connection.execute(
                            text(
                                "SELECT pg_advisory_unlock(hashtextextended(:scope, 0))"
                            ),
                            {"scope": prior},
                        )
                    connection.commit()
                    connection.close()
                    return None
                acquired.append(scope)
            return connection
        except BaseException:
            connection.invalidate()
            connection.close()
            raise

    def release_projection(self, connection: Connection, course_id: int) -> None:
        try:
            connection.rollback()
            for scope in (
                f"marketdemandanalyst:projection:{course_id}",
                "marketdemandanalyst:vacancy_lifecycle",
            ):
                connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:scope, 0))"),
                    {"scope": scope},
                )
            connection.commit()
        except BaseException:
            connection.invalidate()
            raise
        finally:
            connection.close()

    def get_approval(
        self, course_id: int, revision: int, run_id: UUID | None
    ) -> MarketSkillApproval:
        query = select(MarketSkillApproval).where(
            MarketSkillApproval.course_id == course_id,
            MarketSkillApproval.revision == revision,
        )
        if run_id is not None:
            query = query.where(MarketSkillApproval.run_id == run_id)
        rows = list(self._db.scalars(query.execution_options(populate_existing=True)))
        if len(rows) != 1:
            raise ValueError("Approval revision must identify one course-owned run")
        return rows[0]

    def active_projection_items(
        self, course_id: int, reference_ids: list[str]
    ) -> tuple[list, list, list]:
        references = list(
            self._db.scalars(
                select(CourseSkillReference)
                .where(
                    CourseSkillReference.course_id == course_id,
                    CourseSkillReference.id.in_(
                        [UUID(value) for value in reference_ids]
                    ),
                )
                .execution_options(populate_existing=True)
            )
        )
        approvals = list(
            self._db.scalars(
                select(MarketSkillApproval)
                .where(
                    MarketSkillApproval.course_id == course_id,
                    MarketSkillApproval.is_active.is_(True),
                )
                .execution_options(populate_existing=True)
            )
        )
        bindings = list(
            self._db.scalars(
                select(CourseSkillEvidence)
                .where(
                    CourseSkillEvidence.course_id == course_id,
                    CourseSkillEvidence.skill_reference_id.in_(
                        [UUID(value) for value in reference_ids]
                    ),
                    CourseSkillEvidence.approval_id.in_([a.id for a in approvals]),
                )
                .execution_options(populate_existing=True)
            )
        )
        return references, approvals, bindings

    def complete_projection_readiness(self, approval: MarketSkillApproval) -> None:
        """Persist gate/review invalidation alongside this revision's projection."""
        from app.modules.courses.models import Course, CourseMarketGateStatus
        from app.modules.curricularalignmentarchitect.skill_prerequisites.review_repository import (
            PrerequisiteReviewRepository,
        )

        course = self._db.scalar(
            select(Course).where(Course.id == approval.course_id).with_for_update()
        )
        if course is None:
            raise ValueError("Projection course no longer exists")
        course.market_gate_status = CourseMarketGateStatus.COMPLETED
        PrerequisiteReviewRepository(self._db).mark_stale(approval.course_id)
        approval.readiness_applied = True
        self._db.flush()

    def finish_projection(
        self,
        approval: MarketSkillApproval,
        reference_ids: list[str],
        status: str,
        available_ids: set[str],
        *,
        error: str | None = None,
    ) -> None:
        approval.projection_status = status
        approval.projection_error = error
        for reference in self._db.scalars(
            select(CourseSkillReference)
            .where(
                CourseSkillReference.course_id == approval.course_id,
                CourseSkillReference.id.in_([UUID(value) for value in reference_ids]),
            )
            .with_for_update()
        ):
            reference.projection_status = status
            reference.available_for_new_selection = (
                status == "projected" and str(reference.id) in available_ids
            )
            if status == "projected":
                reference.projection_revision = reference.approved_revision
        for run in self._db.scalars(
            select(MarketAnalysisRun).where(
                MarketAnalysisRun.course_id == approval.course_id
            )
        ):
            summaries = deepcopy(run.approved_references)
            for summary in summaries:
                if summary["reference_id"] in reference_ids:
                    summary["projection_status"] = status
                    summary["available_for_new_selection"] = (
                        status == "projected"
                        and summary["reference_id"] in available_ids
                    )
            run.approved_references = summaries
        self._db.flush()


class ThreadStateRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def execution_status(self, thread_id: str) -> ExecutionStatus:
        """Observe the session lease without acquiring or releasing any lock."""
        with self._session_factory() as session:
            row = session.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_locks
                        WHERE locktype = 'advisory'
                          AND database = (
                              SELECT oid FROM pg_database
                              WHERE datname = current_database()
                          )
                          AND granted
                          AND classid = ((lock_key >> 32) & 4294967295)::oid
                          AND objid = (lock_key & 4294967295)::oid
                          AND objsubid = 1
                    ) AS busy,
                    (SELECT updated_at FROM mda_thread_state
                     WHERE thread_id = :thread_id) AS state_updated_at
                    FROM (SELECT hashtextextended(:thread_id, 0) AS lock_key) AS requested
                    """
                ),
                {"thread_id": thread_id},
            ).one()
            return ExecutionStatus(
                status="busy" if row.busy else "idle",
                state_updated_at=row.state_updated_at,
            )

    def acquire(self, thread_id: str) -> Connection | None:
        with self._session_factory() as session:
            connection = session.get_bind().engine.connect()
        try:
            locked = connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:thread_id, 0))"),
                {"thread_id": thread_id},
            )
            # Session-level locks survive commit. Keep the actual connection open
            # without an idle transaction for the entire execution lifetime.
            connection.commit()
            if not locked:
                connection.close()
                return None
            return connection
        except BaseException:
            connection.invalidate()
            connection.close()
            raise

    def release(self, connection: Connection, thread_id: str) -> None:
        try:
            connection.rollback()
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:thread_id, 0))"),
                {"thread_id": thread_id},
            )
            connection.commit()
        except BaseException:
            # Never return a connection carrying a session advisory lock to the pool.
            connection.invalidate()
            raise
        finally:
            connection.close()

    def load(self, thread_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.get(MDAThreadState, thread_id)
            return (
                MarketReviewRepository(session).sanitize_source_content(row.state_json)
                if row
                else None
            )

    def save(self, thread_id: str, state: dict[str, Any]) -> None:
        with self._session_factory() as session:
            repo = MarketReviewRepository(session)
            repo.lock_vacancy_lifecycle()
            state = repo.sanitize_source_content(state)
            session.execute(
                insert(MDAThreadState)
                .values(thread_id=thread_id, state_json=state)
                .on_conflict_do_update(
                    index_elements=["thread_id"],
                    set_={"state_json": state, "updated_at": func.now()},
                )
            )
            session.commit()

    def delete(self, thread_id: str) -> None:
        with self._session_factory() as session:
            session.execute(
                delete(MDAThreadState).where(MDAThreadState.thread_id == thread_id)
            )
            session.commit()


async def load_async_thread_state(session_factory, thread_id: str) -> dict | None:
    async with session_factory() as session:
        row = await session.get(MDAThreadState, thread_id)
        if row is None:
            return None
        ids = []
        for value in snapshot_ids(row.state_json):
            try:
                ids.append(UUID(value))
            except ValueError:
                continue
        removed = (
            {
                str(value)
                for value in await session.scalars(
                    select(MarketVacancySnapshot.id).where(
                        MarketVacancySnapshot.id.in_(ids),
                        MarketVacancySnapshot.purged_at.is_not(None),
                    )
                )
            }
            if ids
            else set()
        )
        return redact_snapshot_content(row.state_json, removed)
