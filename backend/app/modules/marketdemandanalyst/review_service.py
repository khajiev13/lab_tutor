"""Teacher-owned review decisions and immutable agent advice."""

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import HTTPException

from .evidence import reference_fingerprint
from .models import MarketAnalysisRun
from .repository import InvalidCandidateIds, MarketReviewRepository, RevisionConflict
from .schemas import (
    AnalysisMetadata,
    IntegrationApproval,
    IntegrationApprovalResult,
    RecommendationProposal,
    SkillCandidate,
    SkillReview,
    SkillReviewDraft,
    SkillReviewRevision,
)
from .service import available_evidence_omissions


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[\w+#]+", value.casefold()))


def _mentions(text: str, label: str) -> bool:
    text, label = _normalized(text), _normalized(label)
    return bool(label) and f" {label} " in f" {text} "


def genuine_posting_url(url: str, provider: str) -> bool:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return False
    host = parsed.hostname.casefold()
    path = parsed.path.casefold()
    if provider == "headhunter":
        return host in {"hh.uz", "hh.ru", "hh.kz"} and bool(
            re.fullmatch(r"/vacancy/[^/]+/?", path)
        )
    if provider == "linkedin":
        return host in {"linkedin.com", "www.linkedin.com"} and bool(
            re.match(r"/jobs/view/[^/]+", path)
        )
    if provider == "indeed":
        return (
            (host == "indeed.com" or host.endswith(".indeed.com"))
            and path == "/viewjob"
            and "jk=" in parsed.query
        )
    return False


def qualifying_vacancy_bindings(
    run: MarketAnalysisRun,
    candidate: dict,
    target: dict,
    snapshots: dict,
    *,
    trusted_observations: list[dict] | None = None,
) -> list[dict]:
    """Revalidate original content and both identities; neighbors cannot lend support."""
    if "jobs" not in run.config.get("evidence_sources", ["jobs"]):
        return []
    bindings = []
    seen = set()
    registry = (
        trusted_observations
        if trusted_observations is not None
        else run.candidate_manifest.get("validated_observations", [])
    )
    for ref in candidate.get("evidence_references", []):
        snapshot = snapshots.get(str(ref.get("snapshot_id")))
        if (
            snapshot is None
            or snapshot.id in seen
            or snapshot.run_id != run.id
            or snapshot.purged_at
            or snapshot.status == "purged"
            or snapshot.provider
            not in run.config.get("sources", ["indeed", "linkedin"])
        ):
            continue
        if (
            ref.get("provider") != snapshot.provider
            or ref.get("original_url") != snapshot.original_url
            or not genuine_posting_url(snapshot.original_url, snapshot.provider)
        ):
            continue
        phrase = ref.get("original_phrase") or ""
        if not phrase:
            continue
        kind = ref.get("evidence_kind")
        if kind == "provider_tag":
            if not any(
                _normalized(tag) == _normalized(phrase) for tag in snapshot.skill_tags
            ):
                continue
        elif kind == "extracted_text":
            start, end, excerpt = (
                ref.get("excerpt_start"),
                ref.get("excerpt_end"),
                ref.get("excerpt"),
            )
            text = snapshot.description_text or ""
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or not isinstance(excerpt, str)
                or not 0 <= start < end <= len(text)
                or text[start:end] != excerpt
                or not _mentions(excerpt, phrase)
            ):
                continue
        else:
            continue
        supported_labels = {_normalized(phrase)}
        if kind == "extracted_text":
            supported_labels.update(
                _normalized(observation["competency"])
                for observation in registry
                if observation.get("reference_hash") == reference_fingerprint(ref)
                and observation.get("identity_key") == candidate.get("identity_key")
            )
        # Each identity must match exact source identity or trusted extraction.
        if any(
            _normalized(label) not in supported_labels
            for label in (candidate["display_name"], target["label"])
        ):
            continue
        seen.add(snapshot.id)
        bindings.append(
            {
                **deepcopy(ref),
                "snapshot_id": str(snapshot.id),
                "original_url": snapshot.original_url,
                "retrieved_at": snapshot.retrieved_at.isoformat(),
                "status": snapshot.status,
            }
        )
    return bindings


def _fingerprint(run: MarketAnalysisRun, snapshots: dict, onet: dict) -> dict:
    return {
        "run_id": str(run.id),
        "course_id": run.course_id,
        "teacher_id": run.teacher_id,
        "candidate_revision": run.candidate_revision,
        "selection_revision": run.selection_revision,
        "publication_revision": run.publication_revision,
        "manifest": deepcopy(run.candidate_manifest),
        "config": deepcopy(run.config),
        "selected": deepcopy(run.selected_candidate_ids),
        "excluded": deepcopy(run.excluded_candidate_ids),
        "confirmation": deepcopy(run.selection_confirmation),
        "outcomes": deepcopy(run.source_outcomes),
        "coverage": deepcopy(run.extraction_coverage),
        "snapshots": {
            key: {
                "run_id": str(row.run_id),
                "provider": row.provider,
                "url": row.original_url,
                "hash": row.content_hash,
                "text": row.description_text,
                "tags": deepcopy(row.skill_tags),
                "status": row.status,
                "purged_at": row.purged_at.isoformat() if row.purged_at else None,
            }
            for key, row in sorted(snapshots.items())
        },
        "onet": {
            key: {
                "release": row.release,
                "soc_code": row.soc_code,
                "label": row.label,
                "ratings": deepcopy(row.ratings),
                "flags": deepcopy(row.flags),
                "rows": deepcopy(row.source_rows),
            }
            for key, row in sorted(onet.items())
        },
    }


def _digest(value: dict) -> str:
    return sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


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
            analysis_metadata=AnalysisMetadata(
                country=run.config.get("country"),
                job_sources=run.config.get("sources") or [],
                evidence_sources=run.config.get("evidence_sources") or [],
                onet_release=run.config.get("onet_release"),
                occupations=run.config.get("selected_onet_occupations") or [],
                created_at=run.created_at,
                updated_at=run.updated_at,
            ),
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
            integration_review={
                key: deepcopy(value)
                for key, value in run.integration_review.items()
                if not key.startswith("_")
            }
            if run.integration_review
            else None,
            publication_revision=run.publication_revision,
            approved_references=run.approved_references,
        )

    def save_mapping_state(
        self, course_id: int, teacher_id: int, body: SkillReviewRevision, fields: dict
    ) -> dict:
        run, snapshot = self._active_run(course_id, teacher_id, body)
        if not self._confirmed(run):
            raise HTTPException(
                409, "Confirm the exact current teacher shortlist before mapping"
            )
        allowed = {
            "curriculum_mapping",
            "mapped_skills",
            "_cleaned_results",
            "selected_for_insertion",
            "final_skills",
            "skill_concepts",
        }
        if set(fields) - allowed:
            raise HTTPException(422, "Invalid mapping state fields")
        if fields.get("curriculum_mapping") is not None:
            ids = [str(row.get("candidate_id")) for row in fields["curriculum_mapping"]]
            if len(set(ids)) != len(ids) or set(ids) != set(run.selected_candidate_ids):
                raise HTTPException(422, "Map every confirmed candidate exactly once")
        self._repo.save_integration_review(run, None)
        _, committed = self._commit_snapshot(
            run, {**deepcopy(snapshot), **deepcopy(fields)}
        )
        return {**committed, **deepcopy(fields)}

    def prepare_integration_review(
        self,
        course_id: int,
        teacher_id: int,
        body: SkillReviewRevision,
        proposals: list[dict],
        *,
        graph,
    ) -> SkillReview:
        self._repo.lock_vacancy_lifecycle()
        run, _ = self._active_run(course_id, teacher_id, body)
        if not self._confirmed(run):
            raise HTTPException(
                409, "Confirm the current teacher shortlist before mapping"
            )
        candidates = {
            c["candidate_id"]: deepcopy(c)
            for c in run.candidate_manifest.get("candidates", [])
        }
        proposal_ids = [str(row.get("candidate_id")) for row in proposals]
        if len(set(proposal_ids)) != len(proposal_ids) or set(proposal_ids) != set(
            run.selected_candidate_ids
        ):
            raise HTTPException(
                422, "Review must account for each confirmed candidate exactly once"
            )
        baseline = _fingerprint(
            run, self._repo.vacancy_evidence(run), self._repo.onet_evidence(run)
        )
        safe_proposals = []
        for row in proposals:
            candidate = candidates[str(row["candidate_id"])]
            disposition = row.get("disposition", "new")
            if disposition not in {"new", "covered", "merged"}:
                raise HTTPException(422, "Invalid target disposition")
            safe_proposals.append(
                {
                    **deepcopy(row),
                    "candidate_id": candidate["candidate_id"],
                    "name": candidate["display_name"],
                    "identity_key": candidate.get(
                        "identity_key", candidate["candidate_id"]
                    ),
                    "origin": "onet"
                    if disposition == "new"
                    and str(candidate.get("identity_key", "")).startswith("onet:")
                    else row.get("origin", "market_demand"),
                }
            )
        # Graph/embedding/LLM work is outside any SQL transaction. The lease is
        # already held by the HTTP caller or executing ToolNode, never reclaimed.
        self._repo.rollback()
        resolved = graph.resolve_targets(course_id, safe_proposals)
        self._repo.lock_vacancy_lifecycle()
        run, snapshot = self._active_run(course_id, teacher_id, body)
        current_snapshots = self._repo.vacancy_evidence(run)
        current_onet = self._repo.onet_evidence(run)
        current = _fingerprint(run, current_snapshots, current_onet)
        if current != baseline or not self._confirmed(run):
            raise HTTPException(409, "Evidence changed while preparing the review")
        if len(resolved) != len(proposals) or {
            row["candidate_id"] for row in resolved
        } != set(proposal_ids):
            raise HTTPException(
                422, "Not every confirmed candidate resolved a verified target"
            )
        items = []
        for row in resolved:
            candidate = candidates[row["candidate_id"]]
            bindings = qualifying_vacancy_bindings(
                run, candidate, row["target"], current_snapshots
            )
            items.append(
                {
                    "candidate_id": row["candidate_id"],
                    "target": row["target"],
                    "chapters": row["chapters"],
                    "disposition": row["disposition"],
                    "concepts": deepcopy(row.get("concepts", [])),
                    "qualifying_posting_links": sorted(
                        {b["original_url"] for b in bindings}
                    ),
                    "evidence_snapshot_ids": [b["snapshot_id"] for b in bindings],
                }
            )
        review = {
            "candidate_revision": run.candidate_revision,
            "selection_revision": run.selection_revision,
            "items": items,
            "omissions": available_evidence_omissions(run),
            "omissions_acknowledged": True,
            "_proposals": deepcopy(resolved),
            "_fingerprint": current,
        }
        review["review_digest"] = _digest(review)
        self._repo.save_integration_review(run, review)
        result, _ = self._commit_snapshot(run, snapshot)
        return result

    def prepare_withdrawal_review(
        self, course_id: int, teacher_id: int, body: SkillReviewRevision
    ) -> SkillReview:
        self._repo.lock_vacancy_lifecycle()
        run, snapshot = self._active_run(course_id, teacher_id, body)
        if not run.approved_references:
            raise HTTPException(422, "This analysis has no active offering to withdraw")
        review = {
            "candidate_revision": run.candidate_revision,
            "selection_revision": run.selection_revision,
            "items": [],
            "omissions": [],
            "omissions_acknowledged": True,
            "withdrawal": True,
            "_fingerprint": _fingerprint(
                run, self._repo.vacancy_evidence(run), self._repo.onet_evidence(run)
            ),
        }
        review["review_digest"] = _digest(review)
        self._repo.save_integration_review(run, review)
        result, _ = self._commit_snapshot(run, snapshot)
        return result

    def approve_integration(
        self, course_id: int, teacher_id: int, body: IntegrationApproval
    ) -> IntegrationApprovalResult:
        self._repo.lock_vacancy_lifecycle()
        self._repo.lock_course_publication(course_id)
        run, snapshot = self._active_run(course_id, teacher_id, body)
        review = deepcopy(run.integration_review)
        if not review or review.get("review_digest") != body.review_digest:
            raise HTTPException(409, "Integration review has changed; prepare it again")
        approved_ids = [str(value) for value in body.approved_candidate_ids]
        withdrawal = bool(review.get("withdrawal"))
        if (
            len(set(approved_ids)) != len(approved_ids)
            or (withdrawal and approved_ids)
            or (
                not withdrawal
                and (
                    not approved_ids
                    or set(approved_ids) - set(run.selected_candidate_ids)
                )
            )
        ):
            raise HTTPException(
                422,
                "Approve only current reviewed candidate IDs; empty approval requires explicit withdrawal",
            )
        previous = self._repo.approval_by_digest(run.id, body.review_digest)
        if previous is not None and previous.revision == run.publication_revision:
            if set(approved_ids) != {item["candidate_id"] for item in previous.items}:
                raise HTTPException(
                    409,
                    "This review already approved a different set; prepare a new review",
                )
            previous_status = previous.projection_status
            self._repo.rollback()
            return IntegrationApprovalResult(
                review=self.get_review(course_id, teacher_id),
                projection_status=previous_status,
            )
        snapshots, onet = (
            self._repo.vacancy_evidence(run),
            self._repo.onet_evidence(run),
        )
        if (
            _fingerprint(run, snapshots, onet) != review.get("_fingerprint")
            or _digest(
                {key: value for key, value in review.items() if key != "review_digest"}
            )
            != body.review_digest
        ):
            raise HTTPException(409, "Evidence changed; prepare the review again")
        if withdrawal:
            if not run.approved_references:
                raise HTTPException(
                    422, "This analysis has no active offering to withdraw"
                )
            items = []
        else:
            if not self._confirmed(run):
                raise HTTPException(409, "Current teacher shortlist must be confirmed")
            candidates = {
                c["candidate_id"]: c
                for c in run.candidate_manifest.get("candidates", [])
            }
            reviewed = {p["candidate_id"]: p for p in review["_proposals"]}
            if set(approved_ids) - set(reviewed):
                raise HTTPException(422, "Candidate has no server-reviewed target")
            items, missing = [], []
            for candidate_id in approved_ids:
                candidate, proposal = candidates[candidate_id], reviewed[candidate_id]
                bindings = qualifying_vacancy_bindings(
                    run, candidate, proposal["target"], snapshots
                )
                if not bindings:
                    missing.append(candidate_id)
                    continue
                onet_bindings = []
                for association in candidate.get("onet_associations", []):
                    evidence_id = str(association.get("evidence", {}).get("id", ""))
                    evidence = onet.get(evidence_id)
                    if evidence is None:
                        raise HTTPException(422, "O*NET evidence is not stored")
                    if (
                        "onet" not in run.config.get("evidence_sources", [])
                        or evidence.release != run.config.get("onet_release")
                        or evidence.soc_code
                        not in {
                            o["soc_code"]
                            for o in run.config.get("selected_onet_occupations", [])
                        }
                    ):
                        raise HTTPException(
                            422,
                            "O*NET evidence is outside the selected occupation/release",
                        )
                    onet_bindings.append(deepcopy(association))
                items.append(
                    {
                        **deepcopy(proposal),
                        "candidate": SkillCandidate.model_validate(
                            candidate
                        ).model_dump(mode="json"),
                        "vacancy_bindings": bindings,
                        "validated_observations": deepcopy(
                            run.candidate_manifest.get("validated_observations", [])
                        ),
                        "onet_bindings": onet_bindings,
                        "qualifying_posting_links": sorted(
                            {b["original_url"] for b in bindings}
                        ),
                    }
                )
            if missing:
                raise HTTPException(
                    422, {"code": "missing_job_evidence", "candidate_ids": missing}
                )
        try:
            approval = self._repo.persist_approval(run, review, items)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        result, _ = self._commit_snapshot(run, snapshot)
        return IntegrationApprovalResult(
            review=result, projection_status=approval.projection_status
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
