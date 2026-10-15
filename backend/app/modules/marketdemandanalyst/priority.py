"""Deterministic evidence validation and occupational importance summaries.

The caller supplies an owned, pinned reference catalog and verified pairs. Saved
passages must be enriched with context_keys derived from posting membership;
model-provided quotations or context metadata are never authoritative.
"""

import json
import math
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.modules.marketdemandanalyst.schemas import (
    CandidatePriority,
    CategoryPriority,
    PriorityContext,
    PriorityDecision,
    PriorityPair,
    PriorityResult,
    PrioritySummarySet,
    SkillCandidate,
    SkillCategory,
)
from app.modules.occupation_reference.schemas import OnetEvidence


def _posting_ids(candidate: SkillCandidate) -> set[str]:
    return {
        str(ref["snapshot_id"])
        for ref in candidate.evidence_references
        if ref.get("snapshot_id")
        and ref.get("evidence_kind") in {"extracted_text", "provider_tag"}
        and ref.get("status") not in {"purged", "removed", "unavailable"}
    }


def _valid_value(value: Any) -> bool:
    return type(value) in {float, int} and math.isfinite(value) and 1 <= value <= 5


def _importance(reference: OnetEvidence) -> float | None:
    metric = reference.ratings.get("IM")
    if (
        reference.family not in {"essential", "transferable"}
        or metric is None
        or metric.scale_id != "IM"
        or metric.status != "reported"
        or not _valid_value(metric.value)
    ):
        return None
    return float(metric.value)


def _unavailable(pair: PriorityPair, reason: str) -> PriorityResult:
    return PriorityResult(
        candidate_id=pair.candidate_id,
        soc_code=pair.soc_code,
        context_key=pair.context_key,
        basis="unavailable",
        direct_reference_id=None,
        estimate=None,
        associations=[],
        supporting_evidence_ids=[],
        explanation="No validated importance score is available.",
        limitations=[reason],
        unavailable_reason=reason,
    )


def _decision_value(
    decision: PriorityDecision,
    pair: PriorityPair,
    references: dict[UUID, OnetEvidence],
    passages: dict[str, dict[str, Any]],
    candidate: SkillCandidate,
) -> tuple[float | None, str | None]:
    if pair.soc_code is None:
        return None, "No validated occupation for this group."
    if not _posting_ids(candidate):
        return None, "Candidate has no current job evidence."
    if not decision.explanation.strip():
        return None, "The decision does not explain the evidence."
    associations = {}
    for association in decision.associations:
        reference = references.get(association.reference_id)
        if reference is None or reference.soc_code != pair.soc_code:
            return None, "Foreign, ambiguous or wrong-occupation reference."
        if not association.rationale.strip():
            return None, "A reference association lacks its rationale."
        prior = associations.get(association.reference_id)
        if prior is not None and prior != association.relation:
            return None, "Conflicting reference associations."
        associations[association.reference_id] = association.relation
    for evidence_id in decision.supporting_evidence_ids:
        passage = passages.get(evidence_id)
        if (
            passage is None
            or str(candidate.candidate_id)
            not in {str(value) for value in passage.get("candidate_ids", [])}
            or pair.context_key not in passage.get("context_keys", [])
            or str(passage.get("snapshot_id")) not in _posting_ids(candidate)
            or not isinstance(passage.get("text"), str)
            or not passage["text"].strip()
        ):
            return None, "Passage is not verified for this candidate and context."
    equivalents = {
        key for key, relation in associations.items() if relation == "equivalent"
    }
    if decision.basis == "onet":
        reference = references.get(decision.direct_reference_id)
        if (
            decision.estimate is not None
            or reference is None
            or reference.soc_code != pair.soc_code
            or equivalents != {decision.direct_reference_id}
        ):
            return (
                None,
                "Direct importance requires one unambiguous equivalent reference.",
            )
        value = _importance(reference)
        return value, None if value is not None else "No valid reported IM rating."
    if decision.basis == "ai_estimate":
        if (
            decision.direct_reference_id is not None
            or type(decision.estimate) is not int
            or not 1 <= decision.estimate <= 5
            or not decision.supporting_evidence_ids
            or equivalents
        ):
            return (
                None,
                "Estimate lacks independent passage support or a valid integer.",
            )
        anchors = [
            references[key]
            for key, relation in associations.items()
            if relation in {"related", "broader"}
        ]
        if not any(_importance(reference) is not None for reference in anchors):
            return None, "Estimate requires a related or broader reported IM anchor."
        return float(decision.estimate), None
    return (
        None,
        decision.unavailable_reason or "The analyst could not assess this pair.",
    )


def validate_priority_decisions(
    decisions: list[PriorityDecision],
    *,
    pairs: list[PriorityPair],
    references: list[OnetEvidence],
    passages: dict[str, dict[str, Any]],
    candidates: list[SkillCandidate],
) -> list[PriorityResult]:
    """Return exactly one safe outcome for each distinct requested pair.

    Duplicate identical decisions are idempotent. Conflicting decisions/catalog
    identities abstain rather than choosing a convenient numeric result.
    """
    catalog = {}
    ambiguous = set()
    for reference in references:
        prior = catalog.get(reference.id)
        if prior is not None and prior != reference:
            ambiguous.add(reference.id)
        catalog[reference.id] = reference
    catalog = {key: ref for key, ref in catalog.items() if key not in ambiguous}
    if len({reference.release for reference in references}) > 1:
        catalog = {}  # A catalog spanning releases cannot represent a pinned source.
    candidate_index = {candidate.candidate_id: candidate for candidate in candidates}
    grouped = defaultdict(list)
    for decision in decisions:
        grouped[decision.candidate_id, decision.soc_code].append(decision)
    requested = {}
    conflicting_pairs = set()
    for pair in pairs:
        key = pair.candidate_id, pair.context_key
        if key in requested and requested[key].soc_code != pair.soc_code:
            conflicting_pairs.add(key)
        requested[key] = pair
    outcomes = []
    for key, pair in requested.items():
        proposals = grouped[pair.candidate_id, pair.soc_code]
        candidate = candidate_index.get(pair.candidate_id)
        if key in conflicting_pairs or candidate is None or not proposals:
            outcomes.append(
                _unavailable(pair, "Missing or inconsistent candidate/pair decision.")
            )
            continue
        decision = proposals[0]
        if any(proposal != decision for proposal in proposals[1:]):
            outcomes.append(_unavailable(pair, "Conflicting duplicate decisions."))
            continue
        value, reason = _decision_value(decision, pair, catalog, passages, candidate)
        if value is None:
            outcomes.append(_unavailable(pair, reason or "Invalid priority evidence."))
            continue
        outcomes.append(
            PriorityResult(
                **decision.model_dump(),
                context_key=pair.context_key,
                official_value=value if decision.basis == "onet" else None,
                value=value,
            )
        )
    return outcomes


def _context_key(context: PriorityContext) -> str:
    return context.soc_code or f"unmapped:{context.group_id}"


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(Decimal(str(value)) for value in values) / len(values))


def _rounded(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _rank_complete(
    keys: list[str], summaries: dict, postings: dict[str, set[str]]
) -> None:
    slots = [index for index, key in enumerate(keys) if summaries[key].complete]
    ranked = sorted(
        (keys[index] for index in slots),
        key=lambda key: (-_rounded(summaries[key].value), -len(postings[key])),
    )
    for slot, key in zip(slots, ranked, strict=True):
        summaries[key].display_order = slot


def build_priority_summaries(
    candidates: list[SkillCandidate],
    categories: list[SkillCategory],
    contexts: list[PriorityContext],
    results: list[PriorityResult],
) -> PrioritySummarySet:
    """Average distinct occupations, then complete canonical candidates.

    Eligibility comes from current selected posting membership, never the UI's
    posting_support default or teacher checkboxes. Partial rows retain slots.
    """
    current_postings = {
        str(posting) for context in contexts for posting in context.posting_ids
    }
    unique = {}
    for candidate in candidates:
        postings = _posting_ids(candidate)
        if postings and (not contexts or postings & current_postings):
            unique.setdefault(str(candidate.candidate_id), candidate)
    grouped = defaultdict(list)
    for result in results:
        grouped[str(result.candidate_id), result.context_key].append(result)
    summaries = PrioritySummarySet()
    candidate_postings = {}
    for key, candidate in unique.items():
        postings = _posting_ids(candidate) & current_postings
        candidate_postings[key] = postings
        relevant = {
            _context_key(context)
            for context in contexts
            if postings & {str(posting) for posting in context.posting_ids}
        }
        components = []
        for context_key in sorted(relevant):
            matches = grouped[key, context_key]
            if not matches or any(result != matches[0] for result in matches[1:]):
                continue
            result = matches[0]
            if result.basis != "unavailable" and _valid_value(result.value):
                components.append(result)
        values = [component.value for component in components]
        basis = "unavailable"
        if components:
            basis = (
                "ai_estimate"
                if any(component.basis == "ai_estimate" for component in components)
                else "onet_aggregate"
                if len(components) > 1
                else "onet"
            )
        summaries.candidates[key] = CandidatePriority(
            value=_mean(values),
            basis=basis,
            complete=bool(relevant) and len(components) == len(relevant),
            expected_contexts=len(relevant),
            scored_contexts=len(components),
            display_order=len(summaries.candidates),
        )
    category_postings = {}
    for category in categories:
        key = category.category_id
        if key in summaries.categories:
            continue
        members = [
            candidate_key
            for candidate_key, candidate in unique.items()
            if candidate.category_id == key
        ]
        complete = [
            summaries.candidates[member]
            for member in members
            if summaries.candidates[member].complete
        ]
        estimated = sum(member.basis == "ai_estimate" for member in complete)
        partial = sum(
            not summaries.candidates[member].complete
            and summaries.candidates[member].value is not None
            for member in members
        )
        summaries.categories[key] = CategoryPriority(
            value=_mean([member.value for member in complete]),
            basis="ai_estimate"
            if estimated
            else "derived"
            if complete
            else "unavailable",
            complete=bool(members) and len(complete) == len(members),
            eligible_count=len(members),
            scored_count=len(complete),
            onet_count=len(complete) - estimated,
            estimated_count=estimated,
            partial_count=partial,
            unavailable_count=len(members) - len(complete) - partial,
            display_order=len(summaries.categories),
        )
        category_postings[key] = set().union(
            *(candidate_postings[member] for member in members)
        )
        for index, member in enumerate(members):
            summaries.candidates[member].display_order = index
        _rank_complete(members, summaries.candidates, candidate_postings)
    _rank_complete(list(summaries.categories), summaries.categories, category_postings)
    return summaries


def _canonical(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            str(key): _canonical(item)
            for key, item in value.items()
            if str(key).casefold().replace("-", "_")
            not in {
                "priority",
                "selected_candidate_ids",
                "excluded_candidate_ids",
                "selection_revision",
                "publication_revision",
                "prior_assessment",
                "api_key",
                "authorization",
                "password",
                "token",
                "secret",
                "proxy_authorization",
                "access_token",
                "refresh_token",
                "headers",
                "request_headers",
            }
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    return value


def priority_input_fingerprint(
    inputs: dict[str, Any],
    contexts: list[PriorityContext],
    *,
    release: str | None,
    model_id: str,
    prompt_version: str,
    policy_version: str,
) -> str:
    """Hash the source/configuration snapshot, excluding teacher decisions.

    Whitelisting detached input fields avoids hashing credentials or unrelated
    runtime state. Canonical list order remains meaningful for stable tie slots.
    """
    source = {
        key: inputs[key]
        for key in (
            "run_id",
            "candidate_revision",
            "candidates",
            "categories",
            "groups",
            "passages",
            "posting_hashes",
            "configured_release",
        )
        if key in inputs
    }
    payload = _canonical(
        {
            "source": source,
            "contexts": contexts,
            "release": release,
            "model_id": model_id,
            "prompt_version": prompt_version,
            "policy_version": policy_version,
        }
    )
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return sha256(encoded.encode()).hexdigest()
