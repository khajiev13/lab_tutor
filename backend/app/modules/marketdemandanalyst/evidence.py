"""Pure extraction provenance and conservative run-local candidate reconciliation."""

import json
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4


def reference_fingerprint(ref: dict) -> str:
    """Hash exact validated source/passage identity without duplicating its text."""
    keys = (
        "snapshot_id",
        "provider",
        "original_url",
        "evidence_kind",
        "original_phrase",
        "excerpt",
        "excerpt_start",
        "excerpt_end",
    )
    return sha256(
        json.dumps(
            {key: ref.get(key) for key in keys}, sort_keys=True, ensure_ascii=False
        ).encode()
    ).hexdigest()


def snapshot_ids(value) -> set[str]:
    if isinstance(value, list):
        return set().union(*(snapshot_ids(item) for item in value))
    if not isinstance(value, dict):
        return set()
    result = {str(value["snapshot_id"])} if value.get("snapshot_id") else set()
    return result.union(*(snapshot_ids(item) for item in value.values()))


def redact_snapshot_content(value, removed_ids: set[str]):
    """Only source-linked objects are redacted; derived labels/audit IDs remain."""
    if isinstance(value, list):
        return [redact_snapshot_content(item, removed_ids) for item in value]
    if not isinstance(value, dict):
        return deepcopy(value)
    result = {
        key: redact_snapshot_content(item, removed_ids) for key, item in value.items()
    }
    if str(value.get("snapshot_id", "")) in removed_ids:
        for key in (
            "original_phrase",
            "excerpt",
            "original_description",
            "description_text",
            "description",
        ):
            if key in result:
                result[key] = None
        if "raw_payload" in result:
            result["raw_payload"] = {}
        if "skill_tags" in result:
            result["skill_tags"] = []
        result["content_removed"] = True
        result["status"] = "purged"
    return result


def make_extraction_chunks(
    text: str, max_chars: int = 4000, overlap: int = 300
) -> list[dict]:
    if max_chars <= 0 or not 0 <= overlap < max_chars:
        raise ValueError("Invalid extraction chunk bounds")
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < 16:
        end = min(start + max_chars, len(text))
        chunks.append(
            {"text": text[start:end], "start": start, "end": end, "uncovered_chars": 0}
        )
        if end == len(text):
            break
        start = end - overlap
    if chunks:
        chunks[-1]["uncovered_chars"] = len(text) - chunks[-1]["end"]
    return chunks


def validated_passage(text: str, excerpt: str, start: int = 0) -> dict | None:
    if not isinstance(excerpt, str) or not excerpt.strip():
        return None
    offset = text.find(excerpt, start)
    if offset < 0:
        return None
    return {
        "excerpt": excerpt,
        "excerpt_start": offset,
        "excerpt_end": offset + len(excerpt),
    }


def calculate_job_metrics(
    supporting_identities,
    assessed_identities,
    *,
    selected_identities=None,
    coverage_status="full",
) -> dict:
    assessed = set(assessed_identities)
    supporting = set(supporting_identities) & assessed
    selected = set(selected_identities if selected_identities is not None else assessed)
    return {
        "supporting_posting_count": len(supporting),
        "assessed_posting_count": len(assessed),
        "selected_posting_count": len(selected),
        "percentage": round(len(supporting) / len(assessed) * 100, 1)
        if assessed
        else None,
        "coverage_status": coverage_status,
    }


def _union(items: list[dict], field: str) -> list:
    result = []
    for item in items:
        for value in item.get(field, []):
            if value not in result:
                result.append(deepcopy(value))
    return result


def reconcile_candidates(evidence: list[dict], previous_manifest: dict) -> dict:
    """Only explicit identity keys merge; equal labels alone never prove equivalence.

    A conflicting historical teacher decision becomes a visible unresolved merge,
    with old IDs retained in the reconciliation record rather than auto-selected.
    """
    previous = previous_manifest.get("candidates", [])
    selected = set(previous_manifest.get("selected_candidate_ids", []))
    excluded = set(previous_manifest.get("excluded_candidate_ids", []))
    history = {
        str(c["candidate_id"]): deepcopy(c)
        for c in previous_manifest.get("candidate_history", [])
    }
    for candidate in previous:
        candidate_id = str(candidate["candidate_id"])
        history[candidate_id] = {
            **history.get(candidate_id, {}),
            "candidate_id": candidate_id,
            "identity_key": candidate.get("identity_key"),
            "display_name": candidate.get("display_name"),
            "category_id": candidate.get("category_id"),
            "selected": candidate_id in selected,
            "excluded": candidate_id in excluded,
        }
    reconciliations = deepcopy(previous_manifest.get("reconciliations", []))
    for record in reconciliations:
        record.setdefault("reconciliation_id", str(uuid4()))
        record.setdefault(
            "historical_candidates",
            [
                deepcopy(history[c])
                for c in record["previous_candidate_ids"]
                if c in history
            ],
        )

    def reconciliation(candidate_id, old_ids, key, reason):
        return {
            "reconciliation_id": str(uuid4()),
            "candidate_id": candidate_id,
            "identity_key": key,
            "previous_candidate_ids": old_ids,
            "reason": reason,
            "previous_selected_candidate_ids": sorted(
                c for c in old_ids if history[c]["selected"]
            ),
            "previous_excluded_candidate_ids": sorted(
                c for c in old_ids if history[c]["excluded"]
            ),
            "historical_candidates": [deepcopy(history[c]) for c in old_ids],
            "resolved": False,
        }

    groups: dict[str, list[dict]] = {}
    for item in evidence:
        key = item.get("identity_key") or str(uuid4())
        groups.setdefault(key, []).append(item)
    candidates = []
    next_selected, next_excluded = [], []
    for key, items in groups.items():
        matches = [p for p in previous if p.get("identity_key") == key]
        if not matches:
            matches = [
                h
                for h in history.values()
                if h.get("identity_key") == key
                and not h.get("superseded_by_candidate_id")
            ]
        old_ids = [str(p["candidate_id"]) for p in matches]
        conflict = any(history[c]["selected"] for c in old_ids) and any(
            history[c]["excluded"] for c in old_ids
        )
        candidate_id = old_ids[0] if len(matches) == 1 else str(uuid4())
        if len(matches) > 1:
            reconciliations.append(
                reconciliation(
                    candidate_id,
                    old_ids,
                    key,
                    "conflicting_teacher_decisions"
                    if conflict
                    else "ambiguous_equivalent_merge",
                )
            )
            for old_id in old_ids:
                history[old_id]["superseded_by_candidate_id"] = candidate_id
        first = items[0]
        refs = _union(items, "evidence_references")
        links = sorted({r["original_url"] for r in refs if r.get("original_url")})
        candidates.append(
            {
                "candidate_id": candidate_id,
                "identity_key": key,
                "display_name": first.get("display_name") or first["name"],
                "category_id": first.get("category_id")
                or first.get("category", "unknown"),
                "original_labels": list(
                    dict.fromkeys(
                        [
                            *_union(items, "original_labels"),
                            *[i.get("name") or i.get("display_name") for i in items],
                        ]
                    )
                ),
                "aliases": _union(items, "aliases"),
                "evidence_references": refs,
                "supporting_identities": _union(items, "supporting_identities"),
                "job_metrics": deepcopy(first.get("job_metrics", {})),
                "onet_associations": _union(items, "onet_associations"),
                "recommendation_reasons": _union(items, "recommendation_reasons"),
                "posting_support": "supported" if links else "missing",
                "qualifying_posting_links": links,
            }
        )
        if len(matches) == 1:
            if history[candidate_id]["selected"]:
                next_selected.append(candidate_id)
            if history[candidate_id]["excluded"]:
                next_excluded.append(candidate_id)
        history.setdefault(
            candidate_id,
            {
                "candidate_id": candidate_id,
                "identity_key": key,
                "display_name": candidates[-1]["display_name"],
                "category_id": candidates[-1]["category_id"],
                "selected": candidate_id in next_selected,
                "excluded": candidate_id in next_excluded,
            },
        )
    live_ids = {c["candidate_id"] for c in candidates}
    for old in previous:
        old_id = str(old["candidate_id"])
        if old_id not in live_ids and not any(
            not r.get("resolved") and old_id in r["previous_candidate_ids"]
            for r in reconciliations
        ):
            reconciliations.append(
                reconciliation(
                    None,
                    [old_id],
                    old.get("identity_key"),
                    "candidate_no_longer_observed",
                )
            )
    return {
        "candidates": candidates,
        "categories": [
            {"category_id": c, "label": c.replace("_", " ").title()}
            for c in sorted({i["category_id"] for i in candidates})
        ],
        "selected_candidate_ids": next_selected,
        "excluded_candidate_ids": next_excluded,
        "candidate_history": list(history.values()),
        "reconciliation_required": any(not r.get("resolved") for r in reconciliations),
        "reconciliations": reconciliations,
    }


def onet_candidates(rows: list[dict]) -> list[dict]:
    """Reference descriptors and distinct software examples bypass extraction."""
    candidates = []
    for row in rows:
        example = (
            row.get("workplace_example") if row.get("family") == "software" else None
        )
        label = example or row["label"]
        candidates.append(
            {
                "name": label,
                "original_labels": list(dict.fromkeys([row["label"], label])),
                "category": row.get("family", "reference"),
                "identity_key": f"onet:{row['release']}:{row.get('family')}:{row.get('element_id') or row['id']}:{example or ''}",
                "onet_associations": [
                    {
                        "evidence": deepcopy(row),
                        "relation": "equivalent",
                        "mapping_method": "official_software_example"
                        if example
                        else "official_descriptor",
                        "rationale": "Candidate is the original software example."
                        if example
                        else "Candidate is the original occupation descriptor.",
                    }
                ],
                "evidence_references": [],
                "supporting_identities": [],
            }
        )
    return candidates
