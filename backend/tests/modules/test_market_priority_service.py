"""Bounded inference orchestration over real owned SQL and advisory leases."""

import asyncio
import json
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

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
            return SimpleNamespace(content=json.dumps({"results": data}))
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
    monkeypatch.setattr(settings, "market_skill_priority_model", None)
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
        <= 2
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
    cancellations = 0

    async def delayed(messages, *, config):
        nonlocal cancellations
        if json.loads(messages[1].content)["phase"] != "score":
            return await original_invoke(messages, config=config)
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancellations += 1
            if cancellations == 2:
                # Release only after both actual transports have been abandoned.
                asyncio.get_running_loop().call_soon(release.set)
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
        case.model.ainvoke = delayed
        monkeypatch.setattr(priority_service.asyncio, "wait", timeout_scores)
        try:
            result = await asyncio.wait_for(
                case.service.assess(case.scope, case.lease), timeout=1
            )
        finally:
            release.set()
        assert result.status in {"partial", "unavailable"}
        assert all(item.value is None for item in result.results[:4])
        assert sum(item.value is not None for item in result.results) <= 20
        saved = deepcopy(case.reload().priority_assessment)
        release.set()
        for _ in range(8):
            await asyncio.sleep(0)
        assert cancellations >= 2
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
            records = json.loads(response.content)["results"]
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
            response.content = json.dumps({"results": records})
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
            records = json.loads(response.content)["results"]
            records[0]["official_value"] = 5
            response.content = json.dumps({"results": records})
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


def test_model_payload_defines_strict_results_object_response_schema(service_case):
    assert assess(service_case).status == "ready"
    for payload in service_case.model.calls:
        schema = payload["response_schema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["results"]
        assert set(schema["properties"]) == {"results"}
        assert schema["properties"]["results"]["type"] == "array"
        model_name = (
            "PriorityDecision" if payload["phase"] == "score" else "_ContextDecision"
        )
        assert schema["$defs"][model_name]["additionalProperties"] is False
        assert '{"results": []}' in payload["response_instruction"]


@pytest.mark.parametrize("new_service", [False, True])
def test_cancelled_transport_permits_survive_same_assessment_resume(
    service_case, new_service
):
    from app.modules.marketdemandanalyst.priority_service import SkillPriorityService

    case = service_case
    original = case.model.ainvoke

    async def scenario():
        release = asyncio.Event()
        two_entered = asyncio.Event()
        extra_entered = asyncio.Event()
        active = 0
        maximum = 0
        total_entered = 0
        first = None
        resumed = None

        async def stubborn(messages, *, config):
            nonlocal active, maximum, total_entered
            if json.loads(messages[1].content)["phase"] != "score":
                return await original(messages, config=config)
            # Count the actual transport entry before the cancellation-resistant wait.
            active += 1
            total_entered += 1
            maximum = max(maximum, active)
            if total_entered == 2:
                two_entered.set()
            elif total_entered > 2:
                extra_entered.set()
            try:
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()
                return await original(messages, config=config)
            finally:
                active -= 1

        case.model.ainvoke = stubborn
        try:
            first = asyncio.create_task(case.service.assess(case.scope, case.lease))
            await asyncio.wait_for(two_entered.wait(), timeout=1)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            interrupted = case.reload().priority_assessment
            assert interrupted["status"] == "running" and interrupted["results"] == []
            service = (
                SkillPriorityService(
                    session_factory=case.factory, llm_factory=case.model.factory
                )
                if new_service
                else case.service
            )
            resumed = asyncio.create_task(service.assess(case.scope, case.lease))
            with suppress(TimeoutError):
                await asyncio.wait_for(extra_entered.wait(), timeout=0.1)
            assert active == 2
            assert maximum == 2
            # The old calls cannot write, and resume waits with the same durable attempt.
            assert case.reload().priority_assessment["results"] == []
            release.set()
            result = await asyncio.wait_for(resumed, timeout=2)
            assert result.assessment_id == UUID(interrupted["assessment_id"])
            assert result.deadline_at == datetime.fromisoformat(
                interrupted["deadline_at"]
            )
            assert result.status == "ready" and len(result.results) == 24
            assert maximum == 2
            assert case.reload().priority_assessment == result.model_dump(mode="json")
        finally:
            release.set()
            for task in (first, resumed):
                if task and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(task for task in (first, resumed) if task), return_exceptions=True
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("model", ["qwen3.5-plus", "deepseek-v4.1-flash"])
def test_priority_factory_binds_configured_agent_model_and_disables_thinking(
    monkeypatch,
    model,
):
    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI

    from app.modules.marketdemandanalyst import priority_service

    monkeypatch.setattr(settings, "llm_agent_model", "separate-agent-model")
    monkeypatch.setattr(settings, "market_skill_priority_model", model)
    monkeypatch.setenv("LAB_TUTOR_LLM_MODEL", "different-extraction-model")
    timeouts = []

    def extraction_factory(*, timeout_seconds):
        timeouts.append(timeout_seconds)
        return ChatOpenAI(
            model="different-extraction-model",
            api_key="test-only",
            timeout=timeout_seconds,
            max_retries=0,
        )

    monkeypatch.setattr(priority_service, "_get_extraction_llm", extraction_factory)
    llm = priority_service._get_priority_llm(timeout_seconds=7.5)
    # Characterize the installed LangChain binding -> actual OpenAI payload merge.
    payload = llm.bound._get_request_payload([HumanMessage(content="[]")], **llm.kwargs)
    assert payload["model"] == model
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["extra_body"] == (
        {"thinking": {"type": "disabled"}}
        if model.startswith("deepseek")
        else {"enable_thinking": False}
    )
    assert priority_service.configured_priority_model() == model
    assert llm.bound.max_retries == 0
    assert timeouts == [7.5]


def test_agent_model_identity_is_saved_and_invalidates_cached_assessment(
    service_case, monkeypatch
):
    case = service_case
    monkeypatch.setattr(settings, "llm_agent_model", "configured-agent-model")
    monkeypatch.setenv("LAB_TUTOR_LLM_MODEL", "different-extraction-model")
    first = assess(case)
    assert first.model_id == "configured-agent-model"
    assert first.prompt_version == "4"
    count = len(case.model.calls)
    assert assess(case) == first
    assert len(case.model.calls) == count
    monkeypatch.setattr(settings, "llm_agent_model", "next-agent-model")
    second = assess(case)
    assert second.model_id == "next-agent-model"
    assert second.assessment_id != first.assessment_id
    assert second.input_fingerprint != first.input_fingerprint
    assert len(case.model.calls) > count
    assert len(second.results) == 24


def test_two_pair_batches_account_for_all_candidates_and_request_concise_evidence(
    service_case,
):
    assert assess(service_case).status == "ready"
    batches = [
        payload for payload in service_case.model.calls if payload["phase"] == "score"
    ]
    assert len(batches) == 12
    assert [len(batch["pairs"]) for batch in batches] == [2] * 12
    candidate_ids = {
        pair["candidate_id"] for batch in batches for pair in batch["pairs"]
    }
    assert candidate_ids == {
        candidate["candidate_id"] for candidate in service_case.candidates
    }
    for payload in service_case.model.calls:
        assert "one concise sentence" in payload["response_instruction"]
        assert (
            "minimal sufficient reference and passage IDs"
            in payload["response_instruction"]
        )


def test_context_group_aliases_round_trip_both_phases_to_immutable_saved_ids(
    service_case,
):
    case = service_case
    with case.factory() as db:
        from app.modules.marketdemandanalyst.repository import MarketReviewRepository

        groups = MarketReviewRepository(db).load_priority_inputs(case.scope)["groups"]
    result = assess(case)
    assert result.status == "ready"
    assert result.prompt_version == "4"
    choose = next(call for call in case.model.calls if call["phase"] == "choose")
    validate = next(call for call in case.model.calls if call["phase"] == "validate")
    assert [group["group_id"] for group in choose["groups"]] == ["G1", "G2", "G3"]
    assert validate["groups"] == choose["groups"]
    assert {row["group_id"] for row in validate["proposals"]} == {"G1", "G2", "G3"}
    assert {context.group_id for context in result.contexts} == {
        group["group_id"] for group in groups
    }
    persisted = case.reload().priority_assessment["contexts"]
    assert {context["group_id"] for context in persisted} == {
        group["group_id"] for group in groups
    }
    for group in groups:
        context = next(
            item for item in result.contexts if item.group_id == group["group_id"]
        )
        assert {str(value) for value in context.posting_ids} == set(
            group["posting_ids"]
        )
        assert group["group_id"] not in json.dumps(choose)
        assert group["group_id"] not in json.dumps(validate)


@pytest.mark.parametrize("phase", ["choose", "validate"])
@pytest.mark.parametrize("invalid", ["foreign", "duplicate", "original_id"])
def test_unknown_or_duplicate_context_aliases_are_rejected_without_repair(
    service_case, phase, invalid
):
    case = service_case
    with case.factory() as db:
        from app.modules.marketdemandanalyst.repository import MarketReviewRepository

        saved_id = MarketReviewRepository(db).load_priority_inputs(case.scope)[
            "groups"
        ][0]["group_id"]
    original = case.model.ainvoke

    async def damaged_alias(messages, *, config):
        response = await original(messages, config=config)
        if json.loads(messages[1].content)["phase"] == phase:
            records = json.loads(response.content)["results"]
            records[0]["group_id"] = {
                "foreign": "G999",
                "duplicate": records[1]["group_id"],
                "original_id": saved_id,
            }[invalid]
            response.content = json.dumps({"results": records})
        return response

    case.model.ainvoke = damaged_alias
    result = assess(case)
    assert result.status == "unavailable"
    assert len(result.results) == 24
    assert all(item.value is None for item in result.results)
    assert all(item.soc_code is None for item in result.contexts)
    assert all(item.group_id.startswith("group:") for item in result.contexts)
    assert not any(call["phase"] == "score" for call in case.model.calls)


def test_scoring_payload_states_general_rubric_and_evidence_consistency(service_case):
    assert assess(service_case).status == "ready"
    for payload in service_case.model.calls:
        if payload["phase"] != "score":
            continue
        assert payload["scoring_rubric"] == {
            "1": "Little importance to the role.",
            "2": "Supporting or secondary to the role's primary responsibilities.",
            "3": "Important to the role.",
            "4": "Central to multiple primary responsibilities.",
            "5": "Essential: core work cannot be performed without this capability.",
        }
        rules = " ".join(payload["evidence_consistency_rules"])
        assert "same complete action, object, outcome and scope" in rules
        assert "partial overlap" in rules and "not an official rating" in rules
        assert "ai_estimate" in rules and "never equivalent" in rules
        assert (
            "missing or suppressed measurement" in rules
            and "no suitable direct descriptor" in rules
        )
        assert "Do not escalate" in rules and "mentions" in rules
        assert "whole validated occupation" in rules
        assert "independent occupation context and anchors" in rules


def test_priority_model_override_uses_environment_and_preserves_other_agents(
    monkeypatch,
):
    from app.core.settings import Settings
    from app.modules.marketdemandanalyst import priority_service

    monkeypatch.delenv("LAB_TUTOR_MARKET_SKILL_PRIORITY_MODEL", raising=False)
    config = Settings(
        _env_file=None,
        database_url="postgresql://unused",
        llm_agent_model="separate-agent-model",
    )
    assert config.market_skill_priority_model is None
    monkeypatch.setattr(priority_service, "settings", config)
    assert priority_service.configured_priority_model() == "separate-agent-model"
    monkeypatch.setenv("LAB_TUTOR_MARKET_SKILL_PRIORITY_MODEL", "deepseek-v4.1-flash")
    overridden = Settings(
        _env_file=None,
        database_url="postgresql://unused",
        llm_agent_model="separate-agent-model",
    )
    monkeypatch.setattr(priority_service, "settings", overridden)
    assert priority_service.configured_priority_model() == "deepseek-v4.1-flash"
    assert overridden.llm_agent_model == "separate-agent-model"


@pytest.mark.parametrize(
    "content",
    [
        "[1]",
        "{}",
        '{"items":[1]}',
        '{"results":[1],"foreign":true}',
        '{"results":1}',
        '```json\n{"results":[1]}\n```',
    ],
)
def test_priority_transport_rejects_nonexact_results_wrapper(content):
    from threading import BoundedSemaphore
    from time import monotonic

    from pydantic import TypeAdapter

    from app.modules.marketdemandanalyst.priority_service import (
        SkillPriorityService,
        _Unavailable,
    )

    async def invoke(messages, *, config):
        assert config == {"callbacks": []}
        return SimpleNamespace(content=content)

    service = SkillPriorityService(
        llm_factory=lambda **kwargs: SimpleNamespace(ainvoke=invoke)
    )
    with pytest.raises(_Unavailable):
        asyncio.run(
            service._request(
                {"phase": "score"},
                "Unchanged test system prompt",
                TypeAdapter(list[int]),
                monotonic() + 1,
                BoundedSemaphore(2),
            )
        )


def test_priority_transport_unwraps_only_the_existing_array_adapter():
    from threading import BoundedSemaphore
    from time import monotonic

    from pydantic import TypeAdapter

    from app.modules.marketdemandanalyst.priority_service import SkillPriorityService

    async def invoke(messages, *, config):
        payload = json.loads(messages[1].content)
        assert payload["response_schema"]["type"] == "object"
        return SimpleNamespace(content='{"results":[1,2]}')

    service = SkillPriorityService(
        llm_factory=lambda **kwargs: SimpleNamespace(ainvoke=invoke)
    )
    result = asyncio.run(
        service._request(
            {"phase": "score"},
            "Unchanged test system prompt",
            TypeAdapter(list[int]),
            monotonic() + 1,
            BoundedSemaphore(2),
        )
    )
    assert result == [1, 2]
