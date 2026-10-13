"""Pure display rules, shared with the reviewed frontend JSON corpus."""

import math
import unicodedata
from copy import deepcopy

from .schemas import (
    PatternObservation,
    PatternValue,
    RunReviewContext,
    SkillCandidate,
    SkillReview,
)

# ECMAScript WhiteSpace + LineTerminator, matching native JavaScript trim.
# NEL and U+001C–001F stay significant; only these edge characters are removed.
_ECMASCRIPT_TRIM_CHARACTERS = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def _normalized_text(value: str) -> str:
    return (
        unicodedata.normalize("NFKC", value).strip(_ECMASCRIPT_TRIM_CHARACTERS).lower()
    )


def lexical_key(candidate: SkillCandidate) -> tuple[str, str]:
    # Identical to the frontend: NFKC, trim, lowercase, Unicode code-point
    # comparison. Internal whitespace stays significant; no locale collation.
    return (
        _normalized_text(candidate.display_name),
        str(candidate.candidate_id),
    )


def matching_candidates(
    review: SkillReview, context: RunReviewContext
) -> list[SkillCandidate]:
    selected = {str(value) for value in review.selected_candidate_ids}
    search = _normalized_text(context.filters.search)
    return sorted(
        (
            candidate
            for candidate in review.candidates
            if (
                not context.filters.category_ids
                or candidate.category_id in context.filters.category_ids
            )
            and (
                not search
                or any(
                    search in _normalized_text(label)
                    for label in (
                        candidate.display_name,
                        *candidate.aliases,
                        *candidate.original_labels,
                    )
                )
            )
            and (
                context.filters.scope == "all"
                or str(candidate.candidate_id) in selected
            )
        ),
        key=lexical_key,
    )


def descriptor_key(evidence: dict) -> tuple[str, str, str]:
    return (
        evidence.get("release", ""),
        evidence.get("family", ""),
        evidence.get("element_id", ""),
    )


def descriptor_cells(
    candidate: SkillCandidate, context: RunReviewContext, release: str | None
) -> dict[str, dict]:
    """Keep ambiguity until an explicit per-role choice resolves it."""
    unique = {}
    for association in candidate.onet_associations:
        evidence = association.get("evidence") or {}
        if (
            association.get("relation") == "equivalent"
            and evidence.get("id")
            and evidence.get("release") == release
            and evidence.get("soc_code") in context.occupation_codes
            and evidence.get("family") in {"essential", "transferable"}
            and evidence.get("element_id")
        ):
            unique.setdefault(str(evidence["id"]), evidence)
    choices = {
        str(choice.evidence_id)
        for choice in context.descriptor_choices
        if choice.candidate_id == candidate.candidate_id
    }
    cells = {}
    for code in context.occupation_codes:
        rows = [row for row in unique.values() if row.get("soc_code") == code]
        chosen = [row for row in rows if str(row["id"]) in choices]
        if len(chosen) == 1:
            cells[code] = chosen[0]
        elif not chosen and len({descriptor_key(row) for row in rows}) == 1:
            cells[code] = min(rows, key=lambda row: str(row["id"]))
    return cells


def reported_value(evidence: dict, metric: str) -> float | None:
    rating = evidence.get("ratings", {}).get(metric, {})
    if not isinstance(rating, dict) or rating.get("status") != "reported":
        return None
    value = rating.get("value")
    bounds = (1, 5) if metric == "IM" else (0, 7)
    if (
        rating.get("scale_id") != metric
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (rating.get("minimum"), rating.get("maximum")) != bounds
        or not bounds[0] <= value <= bounds[1]
    ):
        return None
    return float(value)


def derive_pattern_observations(
    review: SkillReview, context: RunReviewContext
) -> list[PatternObservation]:
    """Compute over every filtered row; focus and chart pagination are irrelevant."""
    candidates = matching_candidates(review, context)
    coverage = {
        "extraction_coverage": deepcopy(review.extraction_coverage),
        "source_outcomes": {
            key: value.model_dump() for key, value in review.source_outcomes.items()
        },
    }
    result = []
    common = []
    for candidate in candidates:
        facts = candidate.job_metrics
        support = facts.get("supporting_posting_count")
        assessed = facts.get("assessed_posting_count")
        percent = facts.get("percentage")
        if (
            type(assessed) is int
            and assessed >= 10
            and type(support) is int
            and 3 <= support <= assessed
            and type(percent) in {int, float}
            and math.isfinite(percent)
            and 50 <= percent <= 100
        ):
            common.append(candidate)
    common.sort(key=lambda row: (-row.job_metrics["percentage"], *lexical_key(row)))
    if common:
        denominator = common[0].job_metrics["assessed_posting_count"]
        common = [
            row
            for row in common
            if row.job_metrics["assessed_posting_count"] == denominator
        ][:3]
        result.append(
            PatternObservation(
                kind="common_sample",
                candidate_ids=[str(row.candidate_id) for row in common],
                occupation_codes=[],
                descriptor_keys=[],
                values=[
                    PatternValue(
                        candidate_id=str(row.candidate_id),
                        value=row.job_metrics["percentage"],
                        supporting_count=row.job_metrics["supporting_posting_count"],
                        assessed_count=denominator,
                    )
                    for row in common
                ],
                coverage=coverage,
            )
        )
    used = {row.candidate_id for row in common}
    release = (
        review.analysis_metadata.onet_release if review.analysis_metadata else None
    )
    confirmed = (
        {row.soc_code for row in review.analysis_metadata.occupations}
        if review.analysis_metadata
        else set()
    )
    if (
        len(context.occupation_codes) < 2
        or not set(context.occupation_codes) <= confirmed
    ):
        return result
    differences, shared = [], []
    for candidate in candidates:
        if candidate.candidate_id in used:
            continue
        cells = descriptor_cells(candidate, context, release)
        values = [
            reported_value(cells.get(code, {}), "IM")
            for code in context.occupation_codes
        ]
        if (
            len(cells) != len(context.occupation_codes)
            or None in values
            or len({descriptor_key(row) for row in cells.values()}) != 1
        ):
            continue
        spread = max(values) - min(values)
        observation = PatternObservation(
            kind="occupation_difference" if spread >= 1 else "shared_importance",
            candidate_ids=[str(candidate.candidate_id)],
            occupation_codes=context.occupation_codes,
            descriptor_keys=[descriptor_key(next(iter(cells.values())))],
            values=[
                PatternValue(
                    candidate_id=str(candidate.candidate_id),
                    occupation_code=code,
                    value=value,
                )
                for code, value in zip(context.occupation_codes, values, strict=True)
            ],
            coverage=coverage,
        )
        if spread >= 1:
            differences.append((-spread, lexical_key(candidate), observation))
        elif min(values) >= 4:
            shared.append((lexical_key(candidate), observation))
    if differences:
        result.append(min(differences, key=lambda row: row[:2])[2])
    elif shared:
        result.append(min(shared, key=lambda row: row[0])[1])
    return result[:2]
