"""Isolated quality evaluation; source ratings are gold, never model input."""

import math
from collections import Counter
from typing import Any


def _number(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and 1 <= value <= 5


def _cited_ids(decision: dict) -> set[str]:
    associations = decision.get("associations")
    cited = (
        {str(decision["direct_reference_id"])}
        if decision.get("direct_reference_id")
        else set()
    )
    if isinstance(associations, list):
        cited.update(
            str(row["reference_id"])
            for row in associations
            if isinstance(row, dict) and row.get("reference_id")
        )
    return cited


def raw_reference_violations(payload: dict, decisions: Any) -> int:
    """Audit all raw records, including foreign candidates rejected by policy."""
    supplied = {str(row["id"]) for row in payload["references"]}
    return (
        sum(
            len(_cited_ids(row) - supplied)
            for row in decisions
            if isinstance(row, dict)
        )
        if isinstance(decisions, list)
        else 0
    )


def canonical_score_call(payload: dict, decisions: list[dict], aliases):
    """Audit exact per-request aliases independently before grading canonical IDs."""
    candidates, references, evidence = aliases
    pairs = {row["candidate_id"]: row for row in payload["pairs"]}
    seen = [row.get("c") for row in decisions]
    if len(seen) != len(pairs) or set(seen) != set(pairs):
        raise ValueError("Incomplete, duplicate or foreign scoring aliases")
    try:
        rows = []
        for row in decisions:
            candidate = row["c"]
            if any(
                candidate not in payload["passages"][key]["candidate_ids"]
                for key in row["e"]
            ):
                raise ValueError("Scoring passage belongs to another candidate")
            rows.append(
                {
                    "candidate_id": candidates[candidate],
                    "soc_code": pairs[candidate]["soc_code"],
                    "basis": row["b"],
                    "direct_reference_id": references[row["d"]]
                    if row["d"] is not None
                    else None,
                    "estimate": row["v"],
                    "associations": [
                        {
                            "reference_id": references[item["r"]],
                            "relation": item["k"],
                            "rationale": item["why"],
                        }
                        for item in row["a"]
                    ],
                    "supporting_evidence_ids": [evidence[key] for key in row["e"]],
                    "explanation": row["why"],
                    "limitations": row["limits"],
                    "unavailable_reason": row.get("missing"),
                }
            )
        canonical_payload = {
            **payload,
            "pairs": [
                {**row, "candidate_id": candidates[row["candidate_id"]]}
                for row in payload["pairs"]
            ],
            "references": [
                {**row, "id": references[row["id"]]} for row in payload["references"]
            ],
        }
        return canonical_payload, rows
    except (KeyError, TypeError) as exc:
        raise ValueError("Unknown or invalid scoring alias in calibration") from exc


def record_score_reply(calls, payload, decisions, aliases):
    """Keep raw violations even when transport/schema/canonical validation rejects."""
    supplied = {row["id"] for row in payload["references"]}
    records = decisions if isinstance(decisions, list) else []
    violations = 0
    for row in records:
        if not isinstance(row, dict):
            continue
        cited = {row["d"]} if isinstance(row.get("d"), str) else set()
        associations = row.get("a", [])
        if isinstance(associations, list):
            cited.update(
                item["r"]
                for item in associations
                if isinstance(item, dict) and isinstance(item.get("r"), str)
            )
        violations += len(cited - supplied)
    entry = {
        "raw_reference_violations": violations,
        "alias_violations": 0,
        "canonical": None,
    }
    calls.append(entry)
    try:
        entry["canonical"] = canonical_score_call(payload, decisions, aliases)
    except (ValueError, TypeError, AttributeError):
        entry["alias_violations"] = 1


def validate_cases(document: dict) -> list[dict]:
    cases = document.get("cases", [])
    if len(cases) < 20 or len({case.get("soc_code") for case in cases}) < 3:
        raise ValueError("Need at least 20 cases across three occupations")
    if len({case.get("id") for case in cases}) != len(cases):
        raise ValueError("Every case needs a unique identity")
    weak = [case for case in cases if case.get("kind") == "weak_control"]
    if len(weak) < 5:
        raise ValueError("Need at least five weak evidence controls")
    for case in cases:
        if case.get("kind") not in {"held_out", "weak_control"}:
            raise ValueError("Unrecognized evaluation case")
        provenance = case.get("target_provenance", {})
        if not provenance.get("review_basis"):
            raise ValueError("Every target/control needs a reviewed basis")
        if case["kind"] == "held_out" and (
            not _number(case.get("expected_value"))
            or not case.get("held_out_reference_id")
            or not case.get("held_out_element_id")
            or not provenance.get("source_url", "").startswith(
                "https://www.onetcenter.org/"
            )
            or len(provenance.get("source_sha256", "")) != 64
            or provenance.get("release") != document.get("source_release")
        ):
            raise ValueError("Held-out target lacks valid source provenance")
    return cases


def summarize_evaluation(
    cases: list[dict],
    rows: list[dict],
    *,
    elapsed_seconds: float = 0,
    raw_reference_violations: int = 0,
    raw_alias_violations: int = 0,
) -> dict[str, Any]:
    index = {case["id"]: case for case in cases}
    supplied = Counter(row.get("case_id") for row in rows)
    if set(supplied) != set(index) or any(count != 1 for count in supplied.values()):
        raise ValueError("Every case must have exactly one result")
    targets = [case for case in cases if case["kind"] == "held_out"]
    controls = [case for case in cases if case["kind"] == "weak_control"]
    accurate = abstentions = fabricated = mislabeled = invalid = scored = 0
    for row in rows:
        case = index[row["case_id"]]
        provided = set(row.get("provided_reference_ids", []))
        if case.get("held_out_reference_id") in provided or row.get("target_leaked"):
            raise ValueError("Held-out target leaked into inference")
        fabricated += len(set(row.get("cited_reference_ids", [])) - provided)
        value, basis = row.get("value"), row.get("basis")
        valid = _number(value)
        invalid += int(value is not None and not valid)
        scored += int(valid)
        if case["kind"] == "held_out":
            mislabeled += int(value is not None and basis != "ai_estimate")
            accurate += int(
                basis == "ai_estimate"
                and valid
                and abs(value - case["expected_value"]) <= 1
            )
        else:
            abstentions += int(basis == "unavailable" and value is None)
    fabricated = max(fabricated, raw_reference_violations)
    accuracy = accurate / len(targets) if targets else 0
    abstention = abstentions / len(controls) if controls else 0
    return {
        "case_count": len(cases),
        "occupation_count": len({case["soc_code"] for case in cases}),
        "scorable_target_count": len(targets),
        "weak_control_count": len(controls),
        "fabricated_reference_count": fabricated,
        "mislabeled_estimate_count": mislabeled,
        "invalid_numeric_count": invalid,
        "invalid_alias_count": raw_alias_violations,
        "within_one_point_count": accurate,
        "within_one_point_rate": accuracy,
        "correct_abstention_count": abstentions,
        "abstention_rate": abstention,
        "coverage": scored / len(cases) if cases else 0,
        "elapsed_seconds": elapsed_seconds,
        "quality_gate_passed": (
            len(cases) >= 20
            and len({case["soc_code"] for case in cases}) >= 3
            and len(controls) >= 5
            and accuracy >= 0.8
            and abstention >= 0.8
            and fabricated == mislabeled == invalid == 0
            and raw_alias_violations == 0
        ),
    }


def _isolated_runtime():
    from urllib.parse import urlsplit

    from app.core.settings import settings

    url = urlsplit(settings.database_url)
    if (
        url.hostname != "lab_tutor_priority_postgres"
        or url.path != "/lab_tutor_workspace_acceptance"
    ):
        raise ValueError("Evaluation refuses application databases")
    settings.market_skill_priority_enabled = True


async def _assess(scope, *, llm_factory=None):
    from app.modules.marketdemandanalyst.priority_service import SkillPriorityService
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService

    _isolated_runtime()
    state = ThreadStateService()
    lease = await state.claim(f"mda-{scope.teacher_id}-course-{scope.course_id}")
    try:
        service = SkillPriorityService(
            **({"llm_factory": llm_factory} if llm_factory else {})
        )
        return await service.assess(scope, lease)
    finally:
        await state.release(lease)


def _seed_cases(cases: list[dict], release: str):
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.modules.auth.models import User, UserRole
    from app.modules.courses.models import Course
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.schemas import PriorityScope, ProviderVacancy
    from app.modules.occupation_reference.repository import (
        OccupationReferenceRepository,
    )

    with SessionLocal() as db:
        owner = db.scalar(
            select(User).where(User.role == UserRole.TEACHER).order_by(User.id)
        )
        if owner is None:
            raise ValueError("Seed the isolated acceptance teacher first")
        occupation = OccupationReferenceRepository(db).get_occupations(
            release, [cases[0]["soc_code"]]
        )[0]
        course = Course(title=f"Priority evaluation {uuid4().hex}", teacher_id=owner.id)
        db.add(course)
        db.flush()
        repo = MarketReviewRepository(db)
        run = repo.create_run(
            course.id,
            owner.id,
            {
                "sources": ["headhunter"],
                "evidence_sources": ["jobs"],
                "onet_release": release,
            },
        )
        fetched, candidates, identities = [], [], {}
        for case in cases:
            text = "SYNTHETIC EVALUATION ONLY. " + (
                case["job_passage"] or case["competency"]
            )
            snapshot = repo.upsert_vacancy_snapshot(
                run.id,
                ProviderVacancy(
                    provider="headhunter",
                    native_id=str(uuid4().int),
                    title=occupation.title,
                    original_url=f"https://hh.uz/vacancy/{uuid4().int}",
                    original_description=text,
                    description_text=text,
                    skill_tags=[case["display_name"]],
                ),
            )
            candidate_id = str(uuid4())
            identities[case["id"]] = candidate_id
            ref = {
                "snapshot_id": str(snapshot.id),
                "provider": "headhunter",
                "original_url": snapshot.original_url,
                "original_phrase": case["display_name"],
                "retrieved_at": datetime.now(UTC).isoformat(),
                "status": snapshot.status,
                "evidence_kind": "extracted_text"
                if case["job_passage"]
                else "provider_tag",
            }
            if case["job_passage"]:
                start = text.index(case["job_passage"])
                ref.update(
                    excerpt=case["job_passage"],
                    excerpt_start=start,
                    excerpt_end=len(text),
                )
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "display_name": case["competency"],
                    "category_id": "evaluation",
                    "original_labels": [case["display_name"]],
                    "evidence_references": [ref],
                }
            )
            fetched.append(
                {
                    "snapshot_id": str(snapshot.id),
                    "title": occupation.title,
                    "description": text,
                }
            )
        repo.update_manifest(
            run.id,
            course.id,
            owner.id,
            expected_candidate_revision=0,
            candidates=candidates,
            categories=[{"category_id": "evaluation", "label": "Evaluation"}],
        )
        repo.save_configuration_snapshot(
            f"mda-{owner.id}-course-{course.id}",
            {
                "run_id": str(run.id),
                "course_id": course.id,
                "teacher_id": owner.id,
                "fetched_jobs": fetched,
                "selected_jobs": fetched,
                "job_groups": {occupation.title: list(range(len(fetched)))},
            },
        )
        repo.commit()
        return PriorityScope(
            run_id=run.id,
            course_id=course.id,
            teacher_id=owner.id,
            expected_candidate_revision=run.candidate_revision,
        ), identities


async def _evaluate(document: dict, output_dir):
    import json
    import time
    from collections import defaultdict
    from contextvars import ContextVar
    from unittest.mock import patch

    from app.modules.marketdemandanalyst import priority_service
    from app.modules.marketdemandanalyst.priority_service import _get_priority_llm
    from app.modules.occupation_reference.repository import (
        OccupationReferenceRepository,
    )

    cases = validate_cases(document)
    _isolated_runtime()
    batches = defaultdict(list)
    for case in cases:
        batches[
            case["soc_code"], case.get("weak_reason") == "no_valid_rated_anchor"
        ].append(case)
    hidden_elements = {
        (case["soc_code"], case["held_out_element_id"])
        for case in cases
        if case["kind"] == "held_out"
    }
    original = OccupationReferenceRepository.get_evidence
    original_compact = priority_service._compact_scoring_payload
    current_aliases = ContextVar("priority_evaluation_aliases", default=None)
    observed, assessments, transport_trace, all_score_calls = [], [], [], []
    started = time.perf_counter()
    for (_, no_anchors), batch in batches.items():
        scope, identities = _seed_cases(batch, document["source_release"])
        calls = []

        def record_aliases(payload):
            compact, *aliases = original_compact(payload)
            current_aliases.set(aliases)
            return compact, *aliases

        def filtered(repository, *args, _no_anchors=no_anchors, **kwargs):
            rows = original(repository, *args, **kwargs)
            return (
                []
                if _no_anchors
                else [
                    row
                    for row in rows
                    if (row.soc_code, row.element_id) not in hidden_elements
                ]
            )

        class RecordingModel:
            def __init__(
                self,
                timeout_seconds,
                *,
                recorded=calls,
                case_ids=tuple(row["id"] for row in batch),
            ):
                self.calls = recorded
                self.case_ids = case_ids
                self.aliases = current_aliases.get()
                self.inner = _get_priority_llm(timeout_seconds=timeout_seconds)

            async def ainvoke(self, messages, **kwargs):
                payload = json.loads(messages[-1].content)
                event = {"phase": payload.get("phase"), "case_ids": self.case_ids}
                transport_trace.append(event)
                call_started = time.perf_counter()
                try:
                    reply = await self.inner.ainvoke(messages, **kwargs)
                    event["content"] = reply.content
                except BaseException as exc:
                    event["error_type"] = type(exc).__name__
                    raise
                finally:
                    event["elapsed_seconds"] = round(
                        time.perf_counter() - call_started, 2
                    )
                if payload.get("phase") == "score":
                    try:
                        decisions = json.loads(reply.content)
                    except (TypeError, ValueError):
                        decisions = []
                    if isinstance(decisions, dict):
                        decisions = decisions.get("results", [])
                    record_score_reply(self.calls, payload, decisions, self.aliases)
                return reply

        with (
            patch.object(OccupationReferenceRepository, "get_evidence", filtered),
            patch.object(priority_service, "_compact_scoring_payload", record_aliases),
        ):
            assessment = await _assess(scope, llm_factory=RecordingModel)
        all_score_calls.extend(calls)
        assessments.append(assessment.model_dump(mode="json"))
        for case in batch:
            candidate_id = identities[case["id"]]
            results = [
                item
                for item in assessment.results
                if str(item.candidate_id) == candidate_id
                and item.soc_code == case["soc_code"]
            ]
            result = results[0] if len(results) == 1 else None
            provided, cited = set(), set()
            for call in calls:
                if call["canonical"] is None:
                    continue
                payload, decisions = call["canonical"]
                if not any(
                    pair["candidate_id"] == candidate_id for pair in payload["pairs"]
                ):
                    continue
                provided.update(str(row["id"]) for row in payload["references"])
                for decision in decisions if isinstance(decisions, list) else []:
                    if (
                        not isinstance(decision, dict)
                        or decision.get("candidate_id") != candidate_id
                    ):
                        continue
                    cited.update(_cited_ids(decision))
            observed.append(
                {
                    "case_id": case["id"],
                    "basis": result.basis if result else "unavailable",
                    "value": result.value if result else None,
                    "provided_reference_ids": sorted(provided),
                    "cited_reference_ids": sorted(cited),
                }
            )
    report = summarize_evaluation(
        cases,
        observed,
        elapsed_seconds=round(time.perf_counter() - started, 2),
        raw_reference_violations=sum(
            max(
                call["raw_reference_violations"],
                raw_reference_violations(*call["canonical"])
                if call["canonical"]
                else 0,
            )
            for call in all_score_calls
        ),
        raw_alias_violations=sum(call["alias_violations"] for call in all_score_calls),
    )
    report["models"] = sorted({row["model_id"] for row in assessments})
    report["method"] = (
        "Live bounded service, held-out official descriptor targets, synthetic responsibilities; not a specific-technology calibration claim."
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation.json").write_text(
        json.dumps(
            {
                "report": report,
                "observations": observed,
                "assessments": assessments,
                "transport_trace": transport_trace,
            },
            indent=2,
        )
    )
    return report


def evaluate_priority_cases(case_path, output_dir) -> dict[str, Any]:
    import asyncio
    import json

    return asyncio.run(_evaluate(json.loads(case_path.read_text()), output_dir))


async def assess_copied_snapshot(scope, output_dir):
    import json
    import time

    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    _isolated_runtime()
    # Register the same complete SQL model metadata as the guarded server CLI.
    import main  # noqa: F401

    def decisions():
        with SessionLocal() as db:
            run = MarketReviewRepository(db).get_run(
                scope.run_id, scope.course_id, scope.teacher_id
            )
            if run is None:
                raise ValueError("Owned copied run not found")
            return [
                run.candidate_revision,
                run.selection_revision,
                run.publication_revision,
                run.selected_candidate_ids,
                run.excluded_candidate_ids,
                run.selection_confirmation,
                run.integration_review,
            ]

    before = decisions()
    started = time.perf_counter()
    result = await _assess(scope)
    if decisions() != before:
        raise AssertionError("Priority assessment altered teacher decisions")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "assessment.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2)
    )
    (output_dir / "snapshot-receipt.json").write_text(
        json.dumps(
            {
                "elapsed_seconds": round(time.perf_counter() - started, 2),
                "teacher_decisions_preserved": True,
                "status": result.status,
                "scored_pairs": sum(row.value is not None for row in result.results),
                "expected_pairs": result.expected_pair_count,
                "accounted_pairs": result.completed_pair_count,
            },
            indent=2,
        )
    )
    return result


def main():
    import argparse
    import asyncio
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--cases", type=Path)
    choice.add_argument("--snapshot-scope", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.cases:
        report = evaluate_priority_cases(args.cases, args.output)
        print(json.dumps(report))
        if not report["quality_gate_passed"]:
            raise SystemExit(1)
    else:
        from app.modules.marketdemandanalyst.schemas import PriorityScope

        if args.snapshot_scope.stat().st_mode & 0o777 != 0o600:
            raise ValueError("Snapshot scope file must be private")
        result = asyncio.run(
            assess_copied_snapshot(
                PriorityScope.model_validate(
                    json.loads(args.snapshot_scope.read_text())
                ),
                args.output,
            )
        )
        print(
            json.dumps(
                {
                    "status": result.status,
                    "expected_pairs": result.expected_pair_count,
                    "completed_pairs": result.completed_pair_count,
                }
            )
        )


if __name__ == "__main__":
    main()
