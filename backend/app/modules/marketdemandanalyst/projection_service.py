"""Retry committed SQL approval independently of graph availability."""

import json
from copy import deepcopy
from uuid import UUID

from .repository import MarketReviewRepository
from .review_service import qualifying_vacancy_bindings


class SkillEvidenceProjector:
    def __init__(self, repository: MarketReviewRepository, graph):
        self._repo = repository
        self._graph = graph

    def redact(self, course_id: int) -> str:
        """Retry SQL tombstone cleanup independently of approval projection."""
        self._repo.rollback()
        if self._graph is None:
            return "pending"
        lease = self._repo.acquire_projection(course_id)
        if lease is None:
            return "pending"
        ids = []
        try:
            jobs = self._repo.pending_redactions(course_id)
            ids = [job.snapshot_id for job in jobs]
            records = []
            for job in jobs:
                snapshots = self._repo.vacancy_snapshots_by_ids([str(job.snapshot_id)])
                snapshot = snapshots.get(str(job.snapshot_id))
                if (
                    snapshot is None
                    or not snapshot.purged_at
                    or not job.evidence_payload.get("content_removed")
                ):
                    raise ValueError("Redaction requires a current SQL tombstone")
                reference_ids = [row["reference_id"] for row in job.reference_states]
                references, _, _ = self._repo.active_projection_items(
                    course_id, reference_ids
                )
                if {str(r.id) for r in references} != set(reference_ids):
                    raise ValueError("Redaction references belong to another course")
                records.append(
                    {
                        "evidence_id": f"jobs:{job.snapshot_id}",
                        "evidence_json": json.dumps(
                            job.evidence_payload, sort_keys=True
                        ),
                        "course_id": course_id,
                        "reference_states": [
                            {
                                "reference_id": str(r.id),
                                "available": r.available_for_new_selection,
                            }
                            for r in references
                        ],
                        "binding_ids": job.inactive_binding_ids,
                    }
                )
            self._repo.rollback()
            if records:
                self._graph.redact(records)
            self._repo.finish_redactions(ids, "projected")
            self._repo.commit()
            return "projected"
        except Exception as exc:
            self._repo.rollback()
            self._repo.finish_redactions(ids, "error", error=type(exc).__name__)
            self._repo.commit()
            return "error"
        finally:
            self._repo.rollback()
            self._repo.release_projection(lease, course_id)

    def project(
        self, course_id: int, approved_revision: int, *, run_id: UUID | None = None
    ) -> str:
        self._repo.rollback()
        if self._graph is None:
            return "pending"
        redaction_status = self.redact(course_id)
        if redaction_status != "projected":
            return redaction_status
        lease = self._repo.acquire_projection(course_id)
        if lease is None:
            return "pending"
        approval_id = None
        reference_ids = []
        try:
            approval = self._repo.get_approval(course_id, approved_revision, run_id)
            if not approval.is_active:
                self._repo.rollback()
                return "pending"
            approval_id = approval.id
            reference_ids = list(approval.affected_reference_ids)
            references, approvals, bindings = self._repo.active_projection_items(
                course_id, reference_ids
            )
            if (
                len(set(reference_ids)) != len(reference_ids)
                or set(reference_ids) != {str(reference.id) for reference in references}
                or not {item["skill_reference_id"] for item in approval.items}.issubset(
                    reference_ids
                )
            ):
                raise ValueError("Approval affected references are incomplete")
            reference_rows, binding_rows, available = self._records(
                course_id, references, approvals, bindings
            )
            # Commit no open SQL transaction across driver retries/network work.
            self._repo.rollback()
            self._graph.project(reference_rows, binding_rows)
            current = self._repo.get_approval(course_id, approved_revision, run_id)
            if current.id != approval_id or not current.is_active:
                raise ValueError("Approval changed during graph projection")
            self._repo.finish_projection(current, reference_ids, "projected", available)
            if not current.readiness_applied:
                self._repo.complete_projection_readiness(current)
            self._repo.commit()
            return "projected"
        except Exception as exc:
            self._repo.rollback()
            if approval_id is None:
                raise
            current = self._repo.get_approval(course_id, approved_revision, run_id)
            self._repo.finish_projection(
                current, reference_ids, "error", set(), error=type(exc).__name__
            )
            self._repo.commit()
            return "error"
        finally:
            self._repo.rollback()
            self._repo.release_projection(lease, course_id)

    def _records(
        self, course_id, references, approvals, bindings
    ) -> tuple[list[dict], list[dict], set[str]]:
        reference_map = {str(row.id): row for row in references}
        expected = set()
        qualified = {}
        reviewed_metadata = {}
        active_items = {}
        inactive_candidates = set()
        approval_map = {row.id: row for row in approvals}
        for approval in approvals:
            if approval.course_id != course_id:
                raise ValueError("Approval belongs to another course")
            run = self._repo.get_run(approval.run_id, course_id, approval.teacher_id)
            if run is None:
                raise ValueError("Approval run is unavailable")
            for item in approval.items:
                ref_id = item["skill_reference_id"]
                if ref_id not in reference_map:
                    continue
                reference = reference_map[ref_id]
                target = item["target"]
                if (
                    reference.target_identity,
                    reference.label,
                    reference.source,
                    reference.origin,
                ) != (
                    target["identity"],
                    target["label"],
                    target["source"],
                    target["origin"],
                ):
                    raise ValueError(
                        "Approval target differs from the course reference"
                    )
                snapshot_ids = [row["snapshot_id"] for row in item["vacancy_bindings"]]
                snapshots = self._repo.vacancy_snapshots_by_ids(snapshot_ids)
                current = qualifying_vacancy_bindings(
                    run,
                    {**item["candidate"], "identity_key": item.get("identity_key")},
                    target,
                    snapshots,
                    trusted_observations=item.get("validated_observations", []),
                )
                removed = {
                    key for key, snapshot in snapshots.items() if snapshot.purged_at
                }
                if {b["snapshot_id"] for b in current} != set(
                    snapshot_ids
                ) - removed or (not current and not removed):
                    raise ValueError(
                        "Approved candidate and target lack genuine posting evidence"
                    )
                if current:
                    active_items.setdefault(ref_id, []).append(item)
                else:
                    inactive_candidates.add((approval.id, item["candidate_id"]))
                for source, evidence_rows in (
                    ("jobs", item["vacancy_bindings"]),
                    ("onet", item["onet_bindings"]),
                ):
                    for evidence in evidence_rows:
                        evidence_id = (
                            evidence["snapshot_id"]
                            if source == "jobs"
                            else evidence["evidence"]["id"]
                        )
                        key = (
                            approval.id,
                            ref_id,
                            item["candidate_id"],
                            source,
                            evidence_id,
                        )
                        expected.add(key)
                        qualified[key] = evidence
                        reviewed_metadata[key] = (
                            evidence.get("relation", "equivalent"),
                            item.get("rationale", ""),
                        )
        records = []
        actual = set()
        for binding in bindings:
            source = "jobs" if binding.vacancy_snapshot_id is not None else "onet"
            evidence_id = str(binding.vacancy_snapshot_id or binding.onet_evidence_id)
            ref_id = str(binding.skill_reference_id)
            key = (
                binding.approval_id,
                ref_id,
                str(binding.candidate_id),
                source,
                evidence_id,
            )
            approval = approval_map.get(binding.approval_id)
            if (
                key not in expected
                or approval is None
                or binding.run_id != approval.run_id
                or binding.course_id != approval.course_id
                or binding.provenance != qualified[key]
                or (binding.mapping_relation, binding.rationale)
                != reviewed_metadata[key]
            ):
                raise ValueError(
                    "Evidence binding differs from its approved SQL intent"
                )
            if key in actual:
                raise ValueError("Duplicate approval evidence binding")
            actual.add(key)
            if (
                binding.approval_id,
                str(binding.candidate_id),
            ) in inactive_candidates or (
                source == "jobs" and binding.provenance.get("content_removed")
            ):
                continue
            evidence = (
                binding.provenance
                if source == "jobs"
                else binding.provenance["evidence"]
            )
            records.append(
                {
                    "binding_id": str(binding.id),
                    "reference_id": ref_id,
                    "course_id": course_id,
                    "approval_id": str(approval.id),
                    "run_id": str(approval.run_id),
                    "candidate_id": str(binding.candidate_id),
                    "review_digest": approval.review_digest,
                    "mapping_relation": binding.mapping_relation,
                    "rationale": binding.rationale,
                    "source": source,
                    "evidence_id": f"{source}:{evidence_id}",
                    "evidence_json": json.dumps(evidence, sort_keys=True),
                    "source_url": evidence.get("original_url")
                    if source == "jobs"
                    else evidence.get("source_url"),
                    "job_urls": [evidence["original_url"]] if source == "jobs" else [],
                }
            )
        if actual != expected:
            raise ValueError("Approval evidence bindings are incomplete")
        reference_records = []
        for reference in references:
            ref_id = str(reference.id)
            kind, target_id = reference.target_identity.split(":", 1)
            if kind not in {"career", "book", "market"}:
                raise ValueError("Unverified graph target identity")
            concepts = {}
            items = active_items.get(ref_id, [])
            for item in items:
                for concept in item.get("concepts", []):
                    concepts[concept["name"]] = deepcopy(concept)
            # Union mappings for the same verified target across active runs.
            chapters = {
                chapter["chapter_id"] for item in items for chapter in item["chapters"]
            } or {chapter["chapter_id"] for chapter in reference.chapters}
            reference_records.append(
                {
                    "reference_id": ref_id,
                    "course_id": course_id,
                    "target_identity": reference.target_identity,
                    "target_kind": kind,
                    "graph_target_id": target_id,
                    "label": reference.label,
                    "source": reference.source,
                    "origin": reference.origin,
                    "description": reference.display_data.get("description"),
                    "identity_key": items[-1].get("identity_key") if items else None,
                    "chapter_ids": sorted(chapters),
                    "concepts": list(concepts.values()),
                    "approved_revision": reference.approved_revision,
                    "available": bool(items),
                }
            )
        return reference_records, records, set(active_items)
