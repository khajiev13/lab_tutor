"""Resolve teacher-owned evidence once, then release the SQL read transaction."""

import json
from copy import deepcopy
from uuid import UUID

from fastapi import HTTPException

from app.modules.occupation_reference.importer import release_url
from app.modules.occupation_reference.repository import OccupationReferenceRepository

from .evidence import validated_passage
from .repository import MarketReviewRepository
from .review_service import SkillReviewService
from .schemas import (
    OccupationReferenceContext,
    ResolvedContextMetadata,
    ResolvedWorkspaceContext,
    RunReviewContext,
    SkillReviewRevision,
    WorkspaceContext,
)
from .workspace_patterns import (
    derive_pattern_observations,
    descriptor_key,
    matching_candidates,
)

MODEL_BYTES = 24 * 1024


def _size(value: dict) -> int:
    # Use the ordinary JSON encoding too, so whitespace in downstream serializers
    # cannot turn a just-under-budget detached bundle into an oversized request.
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _error(status: int, code: str, message: str):
    raise HTTPException(
        status,
        {"code": code, "message": message, "recovery": "Refresh context"},
    )


def _coverage(review) -> dict:
    """Persist count/status qualifiers without free-form provider source text."""
    return {
        "extraction_coverage": {
            key: value
            for key, value in review.extraction_coverage.items()
            if isinstance(value, (bool, int, float))
            or (key in {"status", "coverage_status"} and isinstance(value, str))
        },
        "source_outcomes": {
            key: {
                "status": row.status,
                "received_count": row.received_count,
                "usable_count": row.usable_count,
                "warnings": [],
            }
            for key, row in review.source_outcomes.items()
        },
    }


def _facts(evidence: dict) -> dict:
    """Whitelist source identities and numerical facts for persistent history."""
    return {
        key: deepcopy(evidence[key])
        for key in (
            "id",
            "release",
            "soc_code",
            "occupation_title",
            "family",
            "element_id",
            "label",
            "ratings",
            "flags",
            "source_url",
            "attribution",
        )
        if key in evidence
    }


def _official(row, title: str, attribution: str) -> dict:
    ratings = {}
    for metric in ("IM", "LV"):
        raw = row.ratings.get(metric)
        if not isinstance(raw, dict):
            continue
        # Quality metadata and source rows may carry original source strings.
        rating = {
            key: deepcopy(raw[key])
            for key in ("scale_id", "value", "minimum", "maximum", "status", "date")
            if key in raw
        }
        # A suppressed database value must never reach the model as a rating.
        if rating.get("status") != "reported":
            rating["value"] = None
        ratings[metric] = rating
    return {
        "id": str(row.id),
        "release": row.release,
        "soc_code": row.soc_code,
        "occupation_title": title,
        "family": row.family,
        "element_id": row.element_id,
        "label": row.label,
        "definition": row.definition,
        "workplace_example": row.workplace_example,
        # This catalog imports ratings and definitions, not level activity anchors.
        "level_activity_anchors": None,
        "ratings": ratings,
        "flags": deepcopy(row.flags),
        "source_url": release_url(row.release, f"{row.family}_skills.csv"),
        "attribution": attribution,
    }


class WorkspaceContextService:
    def __init__(
        self,
        repository: MarketReviewRepository,
        occupations: OccupationReferenceRepository,
    ):
        self._repo = repository
        self._occupations = occupations

    def resolve(
        self, course_id: int, teacher_id: int, request: WorkspaceContext
    ) -> ResolvedWorkspaceContext:
        """Called under the conversation lease by contextual execution (task 3)."""
        try:
            if not self._repo.owns_course(course_id, teacher_id):
                _error(404, "context_not_found", "Course not found")
            if isinstance(request, OccupationReferenceContext):
                return self._reference(request)
            return self._run(course_id, teacher_id, request)
        finally:
            # All returned Pydantic objects/dictionaries are detached before this.
            # Reads cannot flush/commit changes or hold transactions during models.
            self._repo.rollback()
            self._occupations.rollback()

    def _catalog(self, release: str | None, codes: list[str]):
        ready = self._occupations.get_release(release, fresh=True) if release else None
        if ready is None:
            _error(422, "invalid_context", "A ready pinned O*NET release is required")
        rows = self._occupations.get_occupations(ready.version, codes, fresh=True)
        titles = {row.soc_code: row.title for row in rows}
        if set(titles) != set(codes):
            _error(422, "invalid_context", "Occupation not found in the pinned release")
        return ready, titles

    def _run(self, course_id: int, teacher_id: int, request: RunReviewContext):
        snapshot = self._repo.load_active_snapshot(
            SkillReviewService.thread_id(course_id, teacher_id)
        )
        run = self._repo.get_run(request.run_id, course_id, teacher_id)
        if run is None or not snapshot or snapshot.get("run_id") != str(request.run_id):
            _error(404, "context_not_found", "Active analysis run not found")
        if (
            run.candidate_revision != request.expected_candidate_revision
            or run.selection_revision != request.expected_selection_revision
        ):
            _error(409, "context_stale", "Analysis or saved selection has changed")
        if request.has_unsaved_changes and (
            request.intent == "propose_selection" or request.filters.scope == "selected"
        ):
            _error(
                422, "invalid_context", "Save the shortlist before using this context"
            )
        review = SkillReviewService.review_from_run(run)
        candidates = {str(row.candidate_id): row for row in review.candidates}
        explicit = {str(value) for value in request.candidate_ids}
        if request.focused_candidate_id:
            explicit.add(str(request.focused_candidate_id))
        if not explicit <= set(candidates):
            _error(422, "invalid_context", "Candidate does not belong to this analysis")
        category_ids = {row.category_id for row in review.categories} | {
            row.category_id for row in review.candidates
        }
        if not set(request.filters.category_ids) <= category_ids:
            _error(422, "invalid_context", "Category does not belong to this analysis")
        confirmed = {
            row["soc_code"] for row in run.config.get("selected_onet_occupations", [])
        }
        if not set(request.occupation_codes) <= confirmed:
            _error(
                422, "invalid_context", "Occupation is outside the confirmed analysis"
            )
        if request.metric != "frequency" and not request.occupation_codes:
            _error(422, "invalid_context", "A reported rating requires an occupation")
        release = run.config.get("onet_release")
        ready, titles = None, {}
        if request.occupation_codes or request.descriptor_choices:
            if "onet" not in run.config.get("evidence_sources", []):
                _error(
                    422, "invalid_context", "O*NET was not selected for this analysis"
                )
            ready, titles = self._catalog(release, list(confirmed))
        official = self._repo.onet_evidence(run) if ready else {}
        for candidate in review.candidates:
            associations = []
            seen_evidence = set()
            for association in candidate.onet_associations:
                evidence = association.get("evidence") or {}
                row = official.get(str(evidence.get("id")))
                if (
                    row is None
                    or row.id in seen_evidence
                    or row.release != release
                    or row.soc_code not in titles
                ):
                    continue
                if descriptor_key(evidence) != (
                    row.release,
                    row.family,
                    row.element_id,
                ):
                    continue
                if evidence.get("soc_code") != row.soc_code:
                    continue
                if association.get("relation") not in {
                    "equivalent",
                    "broader",
                    "related",
                    "unmatched",
                }:
                    continue
                seen_evidence.add(row.id)
                associations.append(
                    {
                        "relation": association["relation"],
                        "evidence": _official(
                            row, titles[row.soc_code], ready.attribution
                        ),
                    }
                )
            candidate.onet_associations = associations
        self._choices(request, candidates, official)
        matches = matching_candidates(review, request)
        coverage = _coverage(review)
        review.extraction_coverage = coverage["extraction_coverage"]
        review.source_outcomes = {
            key: row.model_copy(update={"warnings": []})
            for key, row in review.source_outcomes.items()
        }
        patterns = derive_pattern_observations(review, request)
        if request.insight_kind:
            patterns = [row for row in patterns if row.kind == request.insight_kind]
            if not patterns:
                _error(422, "invalid_context", "The named pattern no longer qualifies")
        ordered = sorted(matches, key=lambda row: str(row.candidate_id) not in explicit)
        outside = [
            candidates[key]
            for key in sorted(explicit)
            if candidates[key] not in matches
        ]
        ordered = outside + ordered
        focused = (
            str(request.focused_candidate_id) if request.focused_candidate_id else None
        )
        pattern_ids = {
            candidate_id for row in patterns for candidate_id in row.candidate_ids
        }
        ordered.sort(
            key=lambda row: (
                str(row.candidate_id) != focused,
                str(row.candidate_id) not in explicit,
                str(row.candidate_id) not in pattern_ids,
            )
        )
        posting_ids = {
            UUID(identity)
            for row in ordered
            if str(row.candidate_id) in explicit
            for identity in sorted(
                {
                    ref["snapshot_id"]
                    for ref in row.evidence_references
                    if ref.get("snapshot_id")
                }
            )[:2]
        }
        snapshots = self._repo.workspace_vacancies(run.id, sorted(posting_ids, key=str))
        records = []
        evidence_total = 0
        for row in ordered:
            evidence_total += len(
                {
                    ref.get("snapshot_id")
                    for ref in row.evidence_references
                    if ref.get("snapshot_id")
                }
            )
            evidence_total += len(
                {
                    a["evidence"]["id"]
                    for a in row.onet_associations
                    if a["evidence"]["soc_code"] in request.occupation_codes
                }
            )
        for candidate in ordered:
            postings = []
            if str(candidate.candidate_id) in explicit:
                seen = set()
                for ref in sorted(
                    candidate.evidence_references,
                    key=lambda ref: ref.get("snapshot_id", ""),
                ):
                    identity = ref.get("snapshot_id")
                    if not identity or identity in seen:
                        continue
                    if len(postings) == 2:
                        break
                    seen.add(identity)
                    row = snapshots.get(identity)
                    if row is None:
                        _error(
                            404, "context_not_found", "Posting evidence is inaccessible"
                        )
                    available = row.purged_at is None and row.status != "purged"
                    text = row.description_text or ""
                    excerpt = text[:600] if available else None
                    excerpt_kind = (
                        "introductory_context" if available else "unavailable"
                    )
                    if available:
                        for source in candidate.evidence_references:
                            if (
                                source.get("snapshot_id") != identity
                                or source.get("evidence_kind") != "extracted_text"
                            ):
                                continue
                            start = source.get("excerpt_start")
                            if (
                                not isinstance(start, int)
                                or isinstance(start, bool)
                                or start < 0
                            ):
                                continue
                            passage = validated_passage(
                                text, source.get("excerpt"), start
                            )
                            phrase = source.get("original_phrase")
                            if (
                                passage is None
                                or not isinstance(phrase, str)
                                or not phrase.strip()
                                or phrase not in passage["excerpt"]
                            ):
                                continue
                            position = passage["excerpt"].find(phrase)
                            left_context = min(120, max(0, 600 - len(phrase)))
                            offset = max(
                                0,
                                min(
                                    position - left_context,
                                    len(passage["excerpt"]) - 600,
                                ),
                            )
                            excerpt = passage["excerpt"][offset : offset + 600]
                            excerpt_kind = "validated_skill_passage"
                            break
                    postings.append(
                        {
                            "snapshot_id": identity,
                            "provider": row.provider,
                            "original_url": row.original_url,
                            "title": row.title,
                            "status": row.status if available else "unavailable",
                            "excerpt": excerpt,
                            "excerpt_kind": excerpt_kind,
                        }
                    )
            records.append(
                {
                    "candidate_id": str(candidate.candidate_id),
                    "display_name": candidate.display_name,
                    "category_id": candidate.category_id,
                    "job_metrics": {
                        key: deepcopy(candidate.job_metrics[key])
                        for key in (
                            "supporting_posting_count",
                            "assessed_posting_count",
                            "selected_posting_count",
                            "percentage",
                            "coverage_status",
                        )
                        if key in candidate.job_metrics
                    },
                    "onet_associations": [
                        deepcopy(a)
                        for a in candidate.onet_associations
                        if a["evidence"]["soc_code"] in request.occupation_codes
                    ],
                    "postings": postings,
                }
            )
        revision = SkillReviewRevision(
            run_id=run.id,
            expected_candidate_revision=run.candidate_revision,
            expected_selection_revision=run.selection_revision,
        )
        metadata = ResolvedContextMetadata(
            kind=request.kind,
            intent=request.intent,
            run_id=run.id,
            candidate_revision=run.candidate_revision,
            selection_revision=run.selection_revision,
            release=release,
            view=request.view,
            metric=request.metric,
            occupation_codes=request.occupation_codes,
            occupations=[
                {"soc_code": code, "title": titles.get(code, code)}
                for code in request.occupation_codes
            ],
            candidate_ids=sorted(explicit),
            filters=request.filters.model_copy(deep=True),
            descriptor_choices=request.descriptor_choices,
            insight_kind=request.insight_kind,
            matching_count=len(matches),
            included_count=0,
            omitted_count=0,
            coverage=coverage,
            notices=["Unsaved shortlist changes are not included"]
            if request.has_unsaved_changes
            else [],
        )
        bundle = {
            "kind": request.kind,
            "run_id": str(run.id),
            "candidate_revision": run.candidate_revision,
            "selection_revision": run.selection_revision,
            "release": release,
            "metric": request.metric,
            "occupation_codes": request.occupation_codes,
            "descriptor_choices": [
                choice.model_dump(mode="json") for choice in request.descriptor_choices
            ],
            "coverage": coverage,
            "patterns": [row.model_dump(mode="json") for row in patterns],
            "notices": metadata.notices,
            "candidates": [],
        }
        return self._budget(
            request,
            revision,
            bundle,
            "candidates",
            records,
            metadata,
            len(ordered),
            evidence_total,
        )

    @staticmethod
    def _choices(request, candidates, official):
        allowed_relations = {"equivalent"}
        if request.intent == "explain":
            allowed_relations.update({"broader", "related"})
        seen = set()
        keys = {}
        for choice in request.descriptor_choices:
            candidate_id, evidence_id = (
                str(choice.candidate_id),
                str(choice.evidence_id),
            )
            candidate = candidates.get(candidate_id)
            if candidate is None:
                _error(
                    422,
                    "invalid_context",
                    "Descriptor candidate is outside this analysis",
                )
            association = next(
                (
                    a
                    for a in candidate.onet_associations
                    if a["evidence"]["id"] == evidence_id
                ),
                None,
            )
            if association is None or evidence_id not in official:
                _error(404, "context_not_found", "Descriptor evidence is inaccessible")
            evidence = association["evidence"]
            if (
                association["relation"] not in allowed_relations
                or evidence["family"] not in {"essential", "transferable"}
                or not evidence["element_id"]
                or evidence["soc_code"] not in request.occupation_codes
            ):
                _error(
                    422,
                    "invalid_context",
                    "Descriptor choice requires an allowed skill descriptor and compared occupation",
                )
            cell = (candidate_id, evidence["soc_code"])
            if cell in seen:
                _error(
                    422,
                    "invalid_context",
                    "Choose one descriptor per candidate and occupation",
                )
            seen.add(cell)
            keys.setdefault(candidate_id, set()).add(descriptor_key(evidence))
        if any(len(value) > 1 for value in keys.values()):
            _error(
                422,
                "invalid_context",
                "Comparison choices require the same descriptor identity",
            )

    def _reference(self, request: OccupationReferenceContext):
        ready, titles = self._catalog(request.release, request.occupation_codes)
        rows = self._occupations.get_evidence(
            ready.version, request.occupation_codes, fresh=True
        )
        if not set(request.element_ids) <= {row.element_id for row in rows}:
            _error(422, "invalid_context", "Descriptor not found in these occupations")
        records = [
            _official(row, titles[row.soc_code], ready.attribution)
            for row in rows
            if not request.element_ids or row.element_id in request.element_ids
        ]
        metadata = ResolvedContextMetadata(
            kind=request.kind,
            intent=request.intent,
            release=ready.version,
            metric=request.metric,
            occupation_codes=request.occupation_codes,
            occupations=[
                {"soc_code": code, "title": titles[code]}
                for code in request.occupation_codes
            ],
            matching_count=len(records),
            included_count=0,
            omitted_count=0,
        )
        bundle = {
            "kind": request.kind,
            "release": ready.version,
            "metric": request.metric,
            "occupation_codes": request.occupation_codes,
            "evidence": [],
            "notices": [],
        }
        return self._budget(
            request,
            None,
            bundle,
            "evidence",
            records,
            metadata,
            len(records),
            len(records),
        )

    @staticmethod
    def _budget(
        request, revision, bundle, key, records, metadata, total, evidence_total
    ):
        def counts():
            included = len(bundle[key])
            evidence_included = (
                sum(
                    len(row["postings"]) + len(row["onet_associations"])
                    for row in bundle[key]
                )
                if key == "candidates"
                else included
            )
            bundle["included_count"] = included
            bundle["omitted_count"] = total - included
            bundle["evidence_included_count"] = evidence_included
            bundle["evidence_omitted_count"] = max(
                0, evidence_total - evidence_included
            )

        counts()
        for record in records:
            bundle[key].append(record)
            counts()
            if _size(bundle) > MODEL_BYTES:
                bundle[key].pop()
                counts()
        if bundle["omitted_count"] or bundle["evidence_omitted_count"]:
            bundle["notices"] = [
                *bundle["notices"],
                "Some context was omitted to fit the evidence budget",
            ]
            while _size(bundle) > MODEL_BYTES and bundle[key]:
                bundle[key].pop()
                counts()
        if _size(bundle) > MODEL_BYTES:
            _error(
                422, "invalid_context", "Context facts exceed the model evidence budget"
            )
        metadata.included_count = bundle["included_count"]
        metadata.omitted_count = bundle["omitted_count"]
        metadata.evidence_included_count = bundle["evidence_included_count"]
        metadata.evidence_omitted_count = bundle["evidence_omitted_count"]
        metadata.notices = list(bundle["notices"])
        if key == "candidates":
            metadata.candidate_labels = {
                row["candidate_id"]: row["display_name"] for row in bundle[key]
            }
            metadata.facts = [
                {
                    "candidate_id": row["candidate_id"],
                    "job_metrics": deepcopy(row["job_metrics"]),
                    "onet_associations": [
                        {"relation": a["relation"], "evidence": _facts(a["evidence"])}
                        for a in row["onet_associations"]
                    ],
                    "postings": [
                        {k: v for k, v in posting.items() if k != "excerpt"}
                        for posting in row["postings"]
                    ],
                }
                for row in bundle[key]
            ]
        else:
            metadata.facts = [_facts(row) for row in bundle[key]]
        return ResolvedWorkspaceContext(
            request=request.model_copy(deep=True),
            intent=request.intent,
            revision=revision,
            model_bundle=deepcopy(bundle),
            history_metadata=metadata,
        )
