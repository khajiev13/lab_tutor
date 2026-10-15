"""Bounded inference orchestration over real owned SQL and advisory leases."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.core.settings import settings
from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState
from app.modules.marketdemandanalyst.repository import ThreadStateRepository
from app.modules.marketdemandanalyst.thread_state_service import ThreadLease
from app.modules.occupation_reference.models import (
    OnetEvidence,
    OnetOccupation,
    OnetRelease,
)
from tests.market_priority_fixtures import seed_priority_case


class ModelTransport:
    def __init__(self, case):
        self.case = case
        self.calls = []
        self.timeouts = []
        self.in_flight = 0
        self.maximum_in_flight = 0
        self.hook = None
        self.invalid_context = False
        self.malformed = False
        self.estimate = False

    def factory(self, *, timeout_seconds):
        self.timeouts.append(timeout_seconds)
        return self

    async def ainvoke(self, messages, *, config):
        from app.modules.marketdemandanalyst.prompts import (
            SKILL_PRIORITY_ANALYST_PROMPT,
            SKILL_PRIORITY_CONTEXT_PROMPT,
        )

        assert config == {"callbacks": []}
        payload = json.loads(messages[1].content)
        assert messages[0].content == (
            SKILL_PRIORITY_ANALYST_PROMPT
            if payload["phase"] == "score"
            else SKILL_PRIORITY_CONTEXT_PROMPT
        )
        # Input reads, lease checks and prior writes must all have ended their transactions.
        with Session(self.case.engine) as db:
            assert (
                db.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle in transaction'"
                    )
                )
                == 0
            )
        self.calls.append(payload)
        self.in_flight += 1
        self.maximum_in_flight = max(self.maximum_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0)
            if self.hook:
                await self.hook(payload)
            if self.malformed:
                return SimpleNamespace(content="```json\n[]\n```")
            if payload["phase"] in {"choose", "validate"}:
                data = []
                for group in payload["groups"]:
                    code = (
                        "15-1252.00" if group["label"] != "Analysts" else "15-1211.00"
                    )
                    data.append(
                        {
                            "group_id": group["group_id"],
                            "soc_code": None
                            if self.invalid_context and payload["phase"] == "validate"
                            else code,
                            "supporting_posting_ids": group["posting_ids"],
                            "rationale": "Responsibilities fit the supplied full occupation description.",
                            "unavailable_reason": "Incompatible work"
                            if self.invalid_context
                            else None,
                        }
                    )
            else:
                data = []
                for pair in payload["pairs"]:
                    reference = next(
                        row
                        for row in payload["references"]
                        if row["soc_code"] == pair["soc_code"]
                    )
                    evidence_ids = [
                        key
                        for key, item in payload["passages"].items()
                        if pair["candidate_id"] in item["candidate_ids"]
                        and pair["context_key"] in item["context_keys"]
                    ]
                    data.append(
                        {
                            "candidate_id": pair["candidate_id"],
                            "soc_code": pair["soc_code"],
                            "basis": "ai_estimate" if self.estimate else "onet",
                            "direct_reference_id": None
                            if self.estimate
                            else reference["id"],
                            "estimate": 4 if self.estimate else None,
                            "associations": [
                                {
                                    "reference_id": reference["id"],
                                    "relation": "broader"
                                    if self.estimate
                                    else "equivalent",
                                    "rationale": "Complete competency match",
                                }
                            ],
                            "supporting_evidence_ids": evidence_ids,
                            "explanation": "Saved work needs this competency for core software responsibilities.",
                            "limitations": [],
                        }
                    )
            return SimpleNamespace(content=json.dumps(data))
        finally:
            self.in_flight -= 1


@pytest.fixture
def service_case(db_session, client, teacher_auth_headers, monkeypatch):
    from app.modules.marketdemandanalyst.priority_service import SkillPriorityService

    case = seed_priority_case(db_session, client, teacher_auth_headers, skill_count=24)
    # Complete valid source metrics; the shared storage fixture intentionally has minimal JSON.
    metric = {
        "scale_id": "IM",
        "value": 4.53,
        "minimum": 1,
        "maximum": 5,
        "status": "reported",
        "date": None,
        "quality": {},
    }
    row = db_session.get(OnetEvidence, case.reference_id)
    row.ratings = {"IM": metric}
    db_session.add(
        OnetOccupation(
            release="31.0",
            soc_code="15-1211.00",
            title="Computer Systems Analysts",
            description="Analyze business information systems.",
        )
    )
    db_session.flush()
    db_session.add(
        OnetEvidence(
            id=uuid4(),
            release="31.0",
            soc_code="15-1211.00",
            family="essential",
            element_id="2.B.3.e",
            label="Programming",
            definition="Writing computer programs.",
            ratings={"IM": {**metric, "value": 3.5}},
            flags={},
            source_rows=[],
            source_key="analyst",
        )
    )
    thread = db_session.get(MDAThreadState, case.thread_id)
    thread.state_json = {
        **thread.state_json,
        "job_groups": {
            "Разработчики": list(range(8)),
            "Developers": list(range(8, 16)),
            "Analysts": list(range(16, 24)),
        },
    }
    db_session.commit()
    case.before = case.teacher_decisions()
    case.factory = sessionmaker(bind=case.engine)
    case.lock_repo = ThreadStateRepository(case.factory)
    case.lease = ThreadLease(case.thread_id, case.lock_repo.acquire(case.thread_id))
    case.model = ModelTransport(case)
    case.service = SkillPriorityService(
        session_factory=case.factory, llm_factory=case.model.factory
    )
    monkeypatch.setattr(settings, "market_skill_priority_enabled", True)
    try:
        yield case
    finally:
        if not case.lease.connection.closed:
            case.lock_repo.release(case.lease.connection, case.thread_id)


def assess(case):
    return asyncio.run(case.service.assess(case.scope, case.lease))


def test_all_candidates_and_groups_scored_without_checkbox_or_posting_support_gate(
    service_case,
):
    case = service_case
    result = assess(case)
    assert result.status == "ready"
    assert result.expected_pair_count == result.completed_pair_count == 24
    assert len(result.results) == 24
    assert len(result.contexts) == 3
    assert {row.soc_code for row in result.contexts} == {"15-1252.00", "15-1211.00"}
    assert len(result.references) == 2
    assert result.references[0].source_url.startswith("https://")
    assert {row.value for row in result.results} == {4.53, 3.5}
    assert case.teacher_decisions() == case.before
    assert (
        max(len(call["pairs"]) for call in case.model.calls if call["phase"] == "score")
        <= 8
    )
    assert case.model.maximum_in_flight <= 2
    assert max(case.model.timeouts) <= 20
    assert case.reload().priority_assessment["status"] == "ready"


def test_same_terminal_assessment_makes_no_model_calls(service_case):
    first = assess(service_case)
    calls = len(service_case.model.calls)
    second = assess(service_case)
    assert second == first
    assert len(service_case.model.calls) == calls


def test_empty_candidates_make_no_model_call(service_case):
    case = service_case
    with case.factory() as db:
        row = db.get(MarketAnalysisRun, case.scope.run_id)
        row.candidate_manifest = {**row.candidate_manifest, "candidates": []}
        db.commit()
    result = assess(case)
    assert result.status == "ready" and result.results == []
    assert not case.model.calls


@pytest.mark.parametrize(
    "mode", ["no_catalog", "jobs_only", "incompatible", "malformed", "no_release"]
)
def test_degraded_outcomes_are_terminal_cached_and_preserve_choices(service_case, mode):
    case = service_case
    with case.factory() as db:
        if mode == "no_catalog":
            db.query(OnetEvidence).delete()
            db.query(OnetOccupation).delete()
        elif mode == "no_release":
            db.query(OnetEvidence).delete()
            db.query(OnetOccupation).delete()
            db.query(OnetRelease).delete()
        elif mode == "jobs_only":
            row = db.get(MarketAnalysisRun, case.scope.run_id)
            row.config = {
                key: value for key, value in row.config.items() if key != "onet_release"
            }
        db.commit()
    case.model.invalid_context = mode == "incompatible"
    case.model.malformed = mode == "malformed"
    result = assess(case)
    assert result.status == ("ready" if mode == "jobs_only" else "unavailable")
    assert len(result.results) == 24
    count = len(case.model.calls)
    assert assess(case) == result
    assert len(case.model.calls) == count
    assert case.teacher_decisions() == case.before


@pytest.mark.parametrize("metric", [True, "4.5", 8, None])
def test_raw_invalid_ratings_cannot_be_coerced_into_numbers(service_case, metric):
    case = service_case
    with case.factory() as db:
        for row in db.query(OnetEvidence):
            row.ratings = {"IM": {**row.ratings["IM"], "value": metric}}
        db.commit()
    result = assess(case)
    assert result.status == "unavailable"
    assert not result.references
    assert all(row.value is None for row in result.results)


def test_tag_without_verified_passage_cannot_supply_estimate(service_case):
    case = service_case
    case.model.estimate = True
    with case.factory() as db:
        row = db.get(MarketAnalysisRun, case.scope.run_id)
        manifest = deepcopy(row.candidate_manifest)
        for ref in manifest["candidates"][0]["evidence_references"]:
            ref["evidence_kind"] = "provider_tag"
        row.candidate_manifest = manifest
        db.commit()
    result = assess(case)
    assert result.status == "partial"
    assert result.results[0].value is None
    assert sum(row.value is not None for row in result.results) == 23


def test_deadline_keeps_results_and_accounts_for_every_pair(service_case, monkeypatch):
    from app.modules.marketdemandanalyst import priority_service

    case = service_case
    clock = [0.0]
    monkeypatch.setattr(priority_service, "monotonic", lambda: clock[0])
    scored = [0]

    async def advance(payload):
        if payload["phase"] == "score":
            scored[0] += 1
            if scored[0] > 1:
                # Let the first validated batch checkpoint before advancing the fake clock.
                while not case.reload().priority_assessment["results"]:
                    await asyncio.sleep(0)
                clock[0] = 61

    case.model.hook = advance
    result = assess(case)
    assert result.status == "partial"
    assert len(result.results) == 24
    assert 0 < sum(row.value is not None for row in result.results) < 24
    assert max(case.model.timeouts) <= 20


@pytest.mark.parametrize(
    "mutation",
    ["purge", "revision", "new_assessment", "lost_lock", "groups", "closed_connection"],
)
def test_stale_or_unleased_completions_never_overwrite_storage(service_case, mutation):
    case = service_case
    changed = [False]

    async def mutate(payload):
        if changed[0] or payload["phase"] != "score":
            return
        changed[0] = True
        if mutation == "lost_lock":
            case.lease.connection.execute(text("SELECT pg_advisory_unlock_all()"))
            case.lease.connection.commit()
        elif mutation == "closed_connection":
            case.lock_repo.release(case.lease.connection, case.thread_id)
        else:
            with case.factory() as db:
                row = db.get(MarketAnalysisRun, case.scope.run_id)
                if mutation == "purge":
                    from app.modules.marketdemandanalyst.models import (
                        MarketVacancySnapshot,
                    )

                    db.get(
                        MarketVacancySnapshot, next(iter(case.snapshots))
                    ).purged_at = datetime.now(UTC)
                elif mutation == "revision":
                    row.candidate_revision += 1
                elif mutation == "new_assessment":
                    row.priority_assessment = {
                        **row.priority_assessment,
                        "assessment_id": str(uuid4()),
                    }
                elif mutation == "groups":
                    thread = db.get(MDAThreadState, case.thread_id)
                    thread.state_json = {
                        **thread.state_json,
                        "job_groups": {"Changed": [0]},
                    }
                db.commit()

    case.model.hook = mutate
    result = assess(case)
    assert result.status == "stale"
    assert result.references == [] and result.results == []
    stored = case.reload().priority_assessment
    assert stored["status"] == "running"
    assert stored["results"] == []


def test_disabled_feature_does_not_touch_storage_or_call_model(
    service_case, monkeypatch
):
    monkeypatch.setattr(settings, "market_skill_priority_enabled", False)
    result = assess(service_case)
    assert result.status == "unavailable"
    assert service_case.reload().priority_assessment is None
    assert not service_case.model.calls


def test_expired_running_assessment_does_not_reset_deadline(service_case):
    case = service_case

    async def stop_after_context(payload):
        if payload["phase"] == "score":
            raise asyncio.CancelledError()

    case.model.hook = stop_after_context
    with pytest.raises(asyncio.CancelledError):
        assess(case)
    with case.factory() as db:
        row = db.get(MarketAnalysisRun, case.scope.run_id)
        past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        row.priority_assessment = {**row.priority_assessment, "deadline_at": past}
        db.commit()
    count = len(case.model.calls)
    result = assess(case)
    assert result.status == "unavailable"
    assert len(result.results) == 24
    assert len(case.model.calls) == count
    assert result.deadline_at < datetime.now(UTC)


def test_same_soc_groups_do_not_double_weight_one_candidate(service_case):
    case = service_case
    with case.factory() as db:
        row = db.get(MarketAnalysisRun, case.scope.run_id)
        manifest = deepcopy(row.candidate_manifest)
        manifest["candidates"][0]["evidence_references"].extend(
            [
                manifest["candidates"][8]["evidence_references"][0],
                manifest["candidates"][16]["evidence_references"][0],
            ]
        )
        row.candidate_manifest = manifest
        db.commit()
    result = assess(case)
    assert result.expected_pair_count == 25
    first = result.summaries.candidates[case.candidates[0]["candidate_id"]]
    assert first.expected_contexts == 2
    assert first.value == 4.015


def test_only_verified_passages_are_sent_to_the_model(service_case):
    case = service_case
    with case.factory() as db:
        row = db.get(MarketAnalysisRun, case.scope.run_id)
        manifest = deepcopy(row.candidate_manifest)
        manifest["candidates"][0]["evidence_references"].append(
            {
                "snapshot_id": str(uuid4()),
                "evidence_kind": "extracted_text",
                "excerpt": "UNVERIFIED PRIVATE QUOTE",
                "excerpt_start": 0,
                "excerpt_end": 24,
            }
        )
        row.candidate_manifest = manifest
        db.commit()
    assert assess(case).status == "ready"
    assert "UNVERIFIED PRIVATE QUOTE" not in json.dumps(case.model.calls)


@pytest.mark.parametrize("bad", [True, "1", 2, None])
def test_invalid_raw_scale_metadata_never_becomes_an_anchor(service_case, bad):
    case = service_case
    case.model.estimate = True
    with case.factory() as db:
        for row in db.query(OnetEvidence):
            row.ratings = {"IM": {**row.ratings["IM"], "minimum": bad}}
            flag_modified(row, "ratings")
        db.commit()
    result = assess(case)
    assert result.status == "unavailable"
    assert result.references == []
    assert all(row.value is None for row in result.results)


def test_full_catalog_scan_is_not_limited_to_title_matches(service_case):
    case = service_case
    with case.factory() as db:
        db.add_all(
            [
                OnetOccupation(
                    release="31.0",
                    soc_code=f"19-{index:04d}.00",
                    title=f"Unrelated occupation {index}",
                    description="Other responsibilities",
                )
                for index in range(100)
            ]
        )
        db.commit()
    assert assess(case).status == "ready"
    choose = next(call for call in case.model.calls if call["phase"] == "choose")
    assert len(choose["catalog"]) == 102
    assert choose["catalog"][0]["soc_code"] == "15-1211.00"


def test_oversized_catalog_abstains_instead_of_scoring_a_truncated_scan(
    service_case, monkeypatch
):
    from app.modules.marketdemandanalyst import priority_service

    monkeypatch.setattr(priority_service, "MAX_INPUT_BYTES", 10)
    result = assess(service_case)
    assert result.status == "unavailable"
    assert len(result.results) == 24
    assert not service_case.model.calls


def test_late_provider_response_is_cancelled_without_blocking_terminal_result(
    service_case, monkeypatch
):
    from app.modules.marketdemandanalyst import priority_service

    case = service_case
    original_wait = asyncio.wait
    original_invoke = case.model.ainvoke
    late = []
    release = asyncio.Event()

    async def delayed(messages, *, config):
        if json.loads(messages[1].content)["phase"] != "score":
            return await original_invoke(messages, config=config)
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()  # A transport that finishes despite cancellation.
        late.append(True)
        return await original_invoke(messages, config=config)

    async def timeout_scores(tasks, *, timeout):
        await asyncio.sleep(0)
        # Context transport is immediate; only force the delayed scoring calls to expire.
        return await original_wait(
            tasks, timeout=0 if len(case.model.calls) >= 2 else timeout
        )

    async def scenario():
        asyncio.get_running_loop().call_later(0.1, release.set)
        case.model.ainvoke = delayed
        monkeypatch.setattr(priority_service.asyncio, "wait", timeout_scores)
        result = await asyncio.wait_for(
            case.service.assess(case.scope, case.lease), timeout=1
        )
        assert result.status in {"partial", "unavailable"}
        assert sum(item.value is not None for item in result.results) <= 8
        saved = deepcopy(case.reload().priority_assessment)
        release.set()
        for _ in range(8):
            await asyncio.sleep(0)
        assert late
        assert case.reload().priority_assessment == saved

    asyncio.run(scenario())


def test_group_without_verified_work_stays_unmapped(service_case):
    case = service_case
    with case.factory() as db:
        row = db.get(MarketAnalysisRun, case.scope.run_id)
        manifest = deepcopy(row.candidate_manifest)
        for candidate in manifest["candidates"][:8]:
            for ref in candidate["evidence_references"]:
                ref["evidence_kind"] = "provider_tag"
        row.candidate_manifest = manifest
        db.commit()
    result = assess(case)
    assert result.status == "partial"
    first_posting = case.candidates[0]["evidence_references"][0]["snapshot_id"]
    context = next(
        item
        for item in result.contexts
        if first_posting in {str(value) for value in item.posting_ids}
    )
    assert context.soc_code is None
    assert all(row.value is None for row in result.results[:8])
    choose = next(call for call in case.model.calls if call["phase"] == "choose")
    assert len(choose["groups"]) == 2


def test_considered_unmatched_references_have_readable_metadata_without_bulk_storage(
    service_case,
):
    case = service_case
    with case.factory() as db:
        source = db.get(OnetEvidence, case.reference_id)
        for index in range(2):
            db.add(
                OnetEvidence(
                    id=uuid4(),
                    release=source.release,
                    soc_code=source.soc_code,
                    family=source.family,
                    element_id=f"2.B.3.{index}",
                    label=f"Alternative {index}",
                    definition="Other competency.",
                    ratings=deepcopy(source.ratings),
                    flags={},
                    source_rows=[],
                    source_key=f"alternative-{index}",
                )
            )
        db.commit()
    original = case.model.ainvoke

    async def with_considered_reference(messages, *, config):
        response = await original(messages, config=config)
        payload = json.loads(messages[1].content)
        if payload["phase"] == "score":
            records = json.loads(response.content)
            for record in records:
                others = [
                    ref
                    for ref in payload["references"]
                    if ref["soc_code"] == record["soc_code"]
                    and ref["id"] != record["direct_reference_id"]
                ]
                if others:
                    record["associations"].append(
                        {
                            "reference_id": others[0]["id"],
                            "relation": "unmatched",
                            "rationale": "Considered and rejected as a different capability",
                        }
                    )
            response.content = json.dumps(records)
        return response

    case.model.ainvoke = with_considered_reference
    result = assess(case)
    assert result.status == "ready"
    cited = {item.reference_id for row in result.results for item in row.associations}
    assert {row.id for row in result.references} == cited
    assert len(result.references) == 3


def test_cached_release_stays_pinned_after_active_release_changes(service_case):
    case = service_case
    with case.factory() as db:
        row = db.get(MarketAnalysisRun, case.scope.run_id)
        row.config = {
            key: value for key, value in row.config.items() if key != "onet_release"
        }
        db.commit()
    first = assess(case)
    count = len(case.model.calls)
    with case.factory() as db:
        db.get(OnetRelease, "31.0").active = False
        db.flush()
        db.add(
            OnetRelease(
                version="32.0", active=True, manifest={}, attribution="New release"
            )
        )
        db.commit()
    restored = assess(case)
    assert restored == first
    assert restored.release == "31.0"
    assert len(case.model.calls) == count


def test_model_cannot_supply_server_owned_official_values(service_case):
    case = service_case
    original = case.model.ainvoke

    async def forged(messages, *, config):
        response = await original(messages, config=config)
        if json.loads(messages[1].content)["phase"] == "score":
            records = json.loads(response.content)
            records[0]["official_value"] = 5
            response.content = json.dumps(records)
        return response

    case.model.ainvoke = forged
    result = assess(case)
    assert result.status == "unavailable"
    assert len(result.results) == 24
    assert not result.references
    assert all(row.value is None for row in result.results)


def test_resume_does_not_replace_a_pinned_absent_release(service_case, monkeypatch):
    case = service_case
    with case.factory() as db:
        row = db.get(MarketAnalysisRun, case.scope.run_id)
        row.config = {
            key: value for key, value in row.config.items() if key != "onet_release"
        }
        db.get(OnetRelease, "31.0").active = False
        db.commit()
    original = case.service._contexts

    async def interrupted(*args):
        raise asyncio.CancelledError()

    monkeypatch.setattr(case.service, "_contexts", interrupted)
    with pytest.raises(asyncio.CancelledError):
        assess(case)
    saved = case.reload().priority_assessment
    assert saved["release"] is None and saved["status"] == "running"
    with case.factory() as db:
        db.get(OnetRelease, "31.0").active = True
        db.commit()
    monkeypatch.setattr(case.service, "_contexts", original)
    result = assess(case)
    assert result.release is None
    assert result.status == "unavailable"
    assert not case.model.calls


def test_model_payload_defines_strict_bare_array_response_schema(service_case):
    assert assess(service_case).status == "ready"
    for payload in service_case.model.calls:
        schema = payload["response_schema"]
        assert schema["type"] == "array"
        model_name = (
            "PriorityDecision" if payload["phase"] == "score" else "_ContextDecision"
        )
        assert schema["$defs"][model_name]["additionalProperties"] is False
        assert "bare JSON array" in payload["response_instruction"]
