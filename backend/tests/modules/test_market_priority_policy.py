"""Pure score policy: evidence cannot manufacture or inflate importance."""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.modules.marketdemandanalyst import priority
from app.modules.marketdemandanalyst.schemas import (
    CandidatePriority,
    PriorityAssociation,
    PriorityContext,
    PriorityDecision,
    PriorityPair,
    PriorityResult,
    SkillCandidate,
    SkillCategory,
)
from app.modules.occupation_reference.schemas import Metric, OnetEvidence
from tests.market_priority_fixtures import seed_priority_case

SOC = "15-1252.00"
OTHER_SOC = "15-1253.00"


def candidate(*, category="data", postings=None):
    return SkillCandidate(
        candidate_id=uuid4(),
        display_name="SQL",
        category_id=category,
        evidence_references=[
            {"snapshot_id": str(posting), "evidence_kind": "extracted_text"}
            for posting in (postings or [uuid4()])
        ],
    )


def context(postings, soc=SOC, group="group:data"):
    return PriorityContext(
        group_id=group,
        soc_code=soc,
        occupation_title="Developers" if soc else None,
        posting_ids=postings,
        rationale="Responsibilities match.",
        inferred=True,
    )


def reference(*, value=4.5, soc=SOC, status="reported", scale="IM", family="essential"):
    return OnetEvidence(
        id=uuid4(),
        release="31.0",
        soc_code=soc,
        occupation_title="Developers",
        family=family,
        element_id="2.B.3.e",
        label="Programming",
        definition="Writing programs.",
        workplace_example=None,
        ratings={
            scale: Metric(
                scale_id=scale,
                value=value,
                minimum=1,
                maximum=5,
                status=status,
                date=None,
                quality={},
            )
        },
        flags={},
        source_url="https://www.onetonline.org/",
        attribution="O*NET",
    )


def decision(c, ref=None, *, soc=SOC, basis="onet", estimate=None, passage_ids=None):
    return PriorityDecision(
        candidate_id=c.candidate_id,
        soc_code=soc,
        basis=basis,
        direct_reference_id=ref.id if ref and basis == "onet" else None,
        estimate=estimate,
        associations=[
            PriorityAssociation(
                reference_id=ref.id,
                relation="equivalent" if basis == "onet" else "broader",
                rationale="The competency matches the descriptor.",
            )
        ]
        if ref
        else [],
        supporting_evidence_ids=passage_ids or [],
        explanation="SQL is central to the saved role's database responsibilities.",
        limitations=["Occupational guidance."],
    )


def result(c, value, *, soc=SOC, basis="onet", key=None):
    return PriorityResult(
        **decision(
            c, soc=soc, basis=basis, estimate=4 if basis == "ai_estimate" else None
        ).model_dump(),
        context_key=key or soc or "group:unknown",
        value=value,
        official_value=value if basis == "onet" else None,
    )


@pytest.fixture
def validation_case():
    c = candidate()
    ref = reference()
    pair = PriorityPair(candidate_id=c.candidate_id, soc_code=SOC, context_key=SOC)
    posting = c.evidence_references[0]["snapshot_id"]
    passages = {
        "passage:1": {
            "snapshot_id": posting,
            "start": 0,
            "end": 14,
            "text": "Build SQL apps",
            "candidate_ids": [str(c.candidate_id)],
            "context_keys": [SOC],
        }
    }
    return c, ref, pair, passages


def validate(case, decisions, *, refs=None, passages=None, pairs=None):
    c, ref, pair, saved = case
    return priority.validate_priority_decisions(
        decisions,
        pairs=pairs or [pair],
        references=[ref] if refs is None else refs,
        passages=saved if passages is None else passages,
        candidates=[c],
    )


def test_official_number_is_loaded_from_reported_im(validation_case):
    c, ref, _, _ = validation_case
    outcome = validate(validation_case, [decision(c, ref)])[0]
    assert outcome.value == 4.5 and outcome.official_value == 4.5
    assert outcome.basis == "onet"


@pytest.mark.parametrize(
    "change",
    [
        {"value": 0},
        {"value": 6},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": True},
        {"status": "suppressed"},
        {"status": "missing"},
        {"scale_id": "LV"},
    ],
)
def test_invalid_im_cannot_become_an_official_score(validation_case, change):
    c, ref, _, _ = validation_case
    # model_copy deliberately exercises validation even if a caller bypassed DTO parsing.
    metric = ref.ratings["IM"].model_copy(update=change)
    ref = ref.model_copy(update={"ratings": {"IM": metric}})
    outcome = validate(validation_case, [decision(c, ref)], refs=[ref])[0]
    assert outcome.value is None and outcome.basis == "unavailable"
    assert outcome.unavailable_reason


@pytest.mark.parametrize(
    "kind",
    [
        "foreign",
        "wrong_soc",
        "lv_only",
        "software",
        "ambiguous_id",
        "ambiguous_equivalent",
    ],
)
def test_foreign_or_ambiguous_direct_reference_is_rejected(validation_case, kind):
    c, ref, _, _ = validation_case
    d = decision(c, ref)
    refs = [ref]
    if kind == "foreign":
        refs = []
    elif kind == "wrong_soc":
        refs = [ref.model_copy(update={"soc_code": OTHER_SOC})]
    elif kind == "lv_only":
        refs = [ref.model_copy(update={"ratings": reference(scale="LV").ratings})]
    elif kind == "software":
        refs = [ref.model_copy(update={"family": "software"})]
    elif kind == "ambiguous_id":
        refs.append(ref.model_copy(update={"release": "30.0"}))
    else:
        other = reference(value=3.5)
        refs.append(other)
        d.associations.append(
            PriorityAssociation(
                reference_id=other.id,
                relation="equivalent",
                rationale="Also equivalent.",
            )
        )
    assert validate(validation_case, [d], refs=refs)[0].value is None


def test_estimate_requires_valid_anchor_and_verified_pair_passage(validation_case):
    c, ref, _, _ = validation_case
    d = decision(c, ref, basis="ai_estimate", estimate=4, passage_ids=["passage:1"])
    outcome = validate(validation_case, [d])[0]
    assert outcome.value == 4 and outcome.official_value is None
    assert outcome.basis == "ai_estimate"


@pytest.mark.parametrize(
    "kind",
    [
        "none",
        "foreign_id",
        "wrong_candidate",
        "wrong_context",
        "missing_context",
        "empty_text",
        "unrated",
        "equivalent_anchor",
        "foreign_association",
        "no_explanation",
        "boolean",
        "nan",
        "out_of_range",
    ],
)
def test_estimate_rejects_insufficient_or_foreign_evidence(validation_case, kind):
    c, ref, _, passages = validation_case
    d = decision(c, ref, basis="ai_estimate", estimate=4, passage_ids=["passage:1"])
    passages = deepcopy(passages)
    refs = [ref]
    if kind == "none":
        d.supporting_evidence_ids = []
    elif kind == "foreign_id":
        d.supporting_evidence_ids.append("invented")
    elif kind == "wrong_candidate":
        passages["passage:1"]["candidate_ids"] = [str(uuid4())]
    elif kind == "wrong_context":
        passages["passage:1"]["context_keys"] = [OTHER_SOC]
    elif kind == "missing_context":
        passages["passage:1"].pop("context_keys")
    elif kind == "empty_text":
        passages["passage:1"]["text"] = ""
    elif kind == "unrated":
        refs = [ref.model_copy(update={"ratings": {}})]
    elif kind == "equivalent_anchor":
        d.associations[0].relation = "equivalent"
    elif kind == "foreign_association":
        d.associations.append(
            PriorityAssociation(
                reference_id=uuid4(), relation="related", rationale="Invented."
            )
        )
    elif kind == "no_explanation":
        d.explanation = " "
    else:
        d = d.model_copy(
            update={
                "estimate": {"boolean": True, "nan": float("nan"), "out_of_range": 6}[
                    kind
                ]
            }
        )
    assert validate(validation_case, [d], refs=refs, passages=passages)[0].value is None


def test_provider_tag_remains_eligible_but_cannot_support_estimate(validation_case):
    c, ref, _, _ = validation_case
    c.evidence_references[0]["evidence_kind"] = "provider_tag"
    d = decision(c, ref, basis="ai_estimate", estimate=4)
    assert validate(validation_case, [d], passages={})[0].value is None
    assert validate(validation_case, [decision(c, ref)], passages={})[0].value == 4.5
    summaries = priority.build_priority_summaries(
        [c],
        [SkillCategory(category_id="data", label="Data")],
        [context([c.evidence_references[0]["snapshot_id"]])],
        [],
    )
    assert summaries.categories["data"].eligible_count == 1


def test_raw_repository_manifest_does_not_hide_verified_candidate(
    db_session, client, teacher_auth_headers
):
    saved = seed_priority_case(db_session, client, teacher_auth_headers, skill_count=1)
    inputs = saved.repo.load_priority_inputs(saved.scope)
    c = inputs["candidates"][0]
    assert c.posting_support == "missing"
    ctx = context(inputs["groups"][0]["posting_ids"])
    summaries = priority.build_priority_summaries(
        inputs["candidates"], inputs["categories"], [ctx], [result(c, 4.5)]
    )
    assert summaries.candidates[str(c.candidate_id)].value == 4.5
    assert summaries.categories["programming"].eligible_count == 1


def test_missing_conflicting_and_foreign_decisions_never_fill_another_pair(
    validation_case,
):
    c, ref, pair, _ = validation_case
    other = pair.model_copy(update={"soc_code": OTHER_SOC, "context_key": OTHER_SOC})
    d = decision(c, ref)
    conflicting = d.model_copy(
        update={"basis": "unavailable", "unavailable_reason": "Contradiction"}
    )
    foreign = d.model_copy(update={"candidate_id": uuid4()})
    outcomes = validate(validation_case, [d, conflicting, foreign], pairs=[pair, other])
    assert len(outcomes) == 2
    assert all(r.value is None and r.basis == "unavailable" for r in outcomes)
    assert {r.context_key for r in outcomes} == {SOC, OTHER_SOC}


def test_identical_duplicates_are_idempotent(validation_case):
    c, ref, pair, _ = validation_case
    d = decision(c, ref)
    outcomes = validate(validation_case, [d, d], pairs=[pair, pair])
    assert len(outcomes) == 1 and outcomes[0].value == 4.5


@pytest.fixture
def policy_case():
    posting = uuid4()
    candidates = [candidate(postings=[posting]) for _ in range(5)]
    return {
        "candidates": candidates,
        "categories": [SkillCategory(category_id="data", label="Data")],
        "contexts": [context([posting])],
        "results": [
            result(candidates[0], 4.5),
            result(candidates[1], 3.5),
            result(candidates[2], 4, basis="ai_estimate"),
        ],
    }


def test_partial_category_mean_does_not_zero_fill(policy_case):
    category = priority.build_priority_summaries(**policy_case).categories["data"]
    assert category.value == 4.0
    assert category.scored_count == 3 and category.eligible_count == 5
    assert category.estimated_count == 1 and category.onet_count == 2
    assert category.unavailable_count == 2 and category.partial_count == 0
    assert category.basis == "ai_estimate" and not category.complete


def test_distinct_socs_and_candidates_are_equal_weight_and_keep_precision(policy_case):
    c = policy_case["candidates"][0]
    posting = c.evidence_references[0]["snapshot_id"]
    policy_case["candidates"] = [c, c]
    policy_case["contexts"] += [
        context([posting], group="duplicate"),
        context([posting], soc=OTHER_SOC, group="other"),
    ]
    policy_case["results"] = [
        result(c, 4.44),
        result(c, 4.44),
        result(c, 3.45, soc=OTHER_SOC),
    ]
    summaries = priority.build_priority_summaries(**policy_case)
    summary = summaries.candidates[str(c.candidate_id)]
    assert summary.value == pytest.approx(3.945)
    assert summary.basis == "onet_aggregate"
    assert summary.expected_contexts == summary.scored_contexts == 2
    assert summary.complete
    assert summaries.categories["data"].eligible_count == 1
    assert summaries.categories["data"].value == pytest.approx(3.945)


def test_partial_candidate_is_excluded_from_category_mean(policy_case):
    c = policy_case["candidates"][0]
    posting = c.evidence_references[0]["snapshot_id"]
    policy_case["contexts"].append(context([posting], soc=OTHER_SOC, group="other"))
    policy_case["results"].append(
        result(policy_case["candidates"][1], 4.5, soc=OTHER_SOC)
    )
    summaries = priority.build_priority_summaries(**policy_case)
    assert not summaries.candidates[str(c.candidate_id)].complete
    assert summaries.candidates[str(c.candidate_id)].value == 4.5
    category = summaries.categories["data"]
    assert category.value == 4 and category.scored_count == 1
    assert category.partial_count == 2 and category.unavailable_count == 2


def test_mixed_official_and_estimate_role_is_labeled_estimated(policy_case):
    c = policy_case["candidates"][0]
    policy_case["contexts"].append(
        context([c.evidence_references[0]["snapshot_id"]], soc=OTHER_SOC, group="other")
    )
    policy_case["results"].append(result(c, 3, soc=OTHER_SOC, basis="ai_estimate"))
    summary = priority.build_priority_summaries(**policy_case).candidates[
        str(c.candidate_id)
    ]
    assert summary.complete and summary.value == 3.75 and summary.basis == "ai_estimate"


def test_empty_category_and_unmapped_context_are_unavailable(policy_case):
    c = policy_case["candidates"][0]
    policy_case["categories"].append(SkillCategory(category_id="empty", label="Empty"))
    policy_case["contexts"].append(
        context(
            [c.evidence_references[0]["snapshot_id"]], soc=None, group="group:unknown"
        )
    )
    summaries = priority.build_priority_summaries(**policy_case)
    assert not summaries.candidates[str(c.candidate_id)].complete
    empty = summaries.categories["empty"]
    assert empty.value is None and not empty.complete and empty.eligible_count == 0


def test_unknown_positions_remain_fixed():
    posting = uuid4()
    unknown, low, partial, high = [candidate(postings=[posting]) for _ in range(4)]
    other_posting = uuid4()
    partial.evidence_references.append(
        {"snapshot_id": str(other_posting), "evidence_kind": "provider_tag"}
    )
    summaries = priority.build_priority_summaries(
        [unknown, low, partial, high],
        [SkillCategory(category_id="data", label="Data")],
        [context([posting]), context([other_posting], soc=OTHER_SOC, group="other")],
        [result(low, 2), result(partial, 3), result(high, 5)],
    )
    ordered = sorted(
        summaries.candidates, key=lambda key: summaries.candidates[key].display_order
    )
    assert ordered == [str(c.candidate_id) for c in [unknown, high, partial, low]]


def test_rounded_half_up_ties_use_distinct_postings_then_old_order():
    first, second = uuid4(), uuid4()
    a = candidate(postings=[first])
    b = candidate(postings=[first, second, second])
    c = candidate(postings=[first])
    summaries = priority.build_priority_summaries(
        [a, b, c],
        [SkillCategory(category_id="data", label="Data")],
        [context([first, second])],
        [result(a, 4.25), result(b, 4.26), result(c, 4.34)],
    )
    ordered = sorted(
        summaries.candidates, key=lambda key: summaries.candidates[key].display_order
    )
    assert ordered == [str(b.candidate_id), str(a.candidate_id), str(c.candidate_id)]


def test_category_sort_uses_complete_slots_and_distinct_posting_counts():
    posting = uuid4()
    categories = [
        SkillCategory(category_id=key, label=key)
        for key in ["unknown", "low", "partial", "high"]
    ]
    candidates = [
        candidate(category=cat.category_id, postings=[posting]) for cat in categories
    ]
    candidates.append(candidate(category="partial", postings=[posting]))
    summaries = priority.build_priority_summaries(
        candidates,
        categories,
        [context([posting])],
        [result(candidates[1], 2), result(candidates[2], 3), result(candidates[3], 5)],
    )
    assert sorted(
        summaries.categories, key=lambda key: summaries.categories[key].display_order
    ) == ["unknown", "high", "partial", "low"]


def fingerprint(inputs, contexts, **kwargs):
    return priority.priority_input_fingerprint(
        inputs,
        contexts,
        **{
            "release": "31.0",
            "model_id": "model-v1",
            "prompt_version": "1",
            "policy_version": "1",
            **kwargs,
        },
    )


def test_checkbox_changes_do_not_change_fingerprint(policy_case):
    inputs = {
        **policy_case,
        "run_id": str(uuid4()),
        "candidate_revision": 2,
        "groups": [{"group_id": "g", "posting_ids": ["p"]}],
        "posting_hashes": {"p": "hash"},
        "passages": {"p": {"text": "SQL"}},
        "selected_candidate_ids": [],
        "excluded_candidate_ids": [],
    }
    contexts = inputs.pop("contexts")
    before = fingerprint(inputs, contexts)
    changed = deepcopy(inputs)
    changed["selected_candidate_ids"] = [str(inputs["candidates"][0].candidate_id)]
    changed["excluded_candidate_ids"] = [str(inputs["candidates"][1].candidate_id)]
    changed["prior_assessment"] = {"status": "running"}
    changed["candidates"][0].priority = None
    changed["api_key"] = "secret-never-in-hash"
    assert fingerprint(changed, contexts) == before
    assert len(before) == 64


@pytest.mark.parametrize(
    "field",
    [
        "passage",
        "category",
        "group",
        "posting",
        "candidate",
        "revision",
        "context",
        "model",
        "policy",
        "prompt",
        "release",
    ],
)
def test_relevant_source_and_policy_changes_invalidate_fingerprint(policy_case, field):
    inputs = {
        "candidates": policy_case["candidates"],
        "categories": policy_case["categories"],
        "run_id": str(uuid4()),
        "candidate_revision": 1,
        "groups": [{"group_id": "g", "posting_ids": ["p"]}],
        "posting_hashes": {"p": "hash"},
        "passages": {"p": {"text": "SQL"}},
    }
    contexts = policy_case["contexts"]
    original = fingerprint(inputs, contexts)
    changed, mappings, config = deepcopy(inputs), deepcopy(contexts), {}
    if field == "passage":
        changed["passages"]["p"]["text"] = "Python"
    elif field == "category":
        changed["categories"][0].label = "New category"
    elif field == "group":
        changed["groups"][0]["posting_ids"].append("other")
    elif field == "posting":
        changed["posting_hashes"]["p"] = "new hash"
    elif field == "candidate":
        changed["candidates"][0].aliases = ["New alias"]
    elif field == "revision":
        changed["candidate_revision"] += 1
    elif field == "context":
        mappings[0].soc_code = OTHER_SOC
    else:
        config[
            {
                "model": "model_id",
                "policy": "policy_version",
                "prompt": "prompt_version",
                "release": "release",
            }[field]
        ] = "new"
    assert fingerprint(changed, mappings, **config) != original


def test_interleaved_category_members_keep_partial_local_position():
    posting, other = uuid4(), uuid4()
    outside = candidate(category="outside", postings=[posting])
    low, partial, high = [candidate(postings=[posting]) for _ in range(3)]
    partial.evidence_references.append(
        {"snapshot_id": str(other), "evidence_kind": "provider_tag"}
    )
    summaries = priority.build_priority_summaries(
        [outside, low, partial, high],
        [
            SkillCategory(category_id="outside", label="Outside"),
            SkillCategory(category_id="data", label="Data"),
        ],
        [context([posting]), context([other], soc=OTHER_SOC, group="other")],
        [result(low, 2), result(partial, 3), result(high, 5)],
    )
    members = [str(c.candidate_id) for c in [low, partial, high]]
    assert sorted(members, key=lambda key: summaries.candidates[key].display_order) == [
        str(high.candidate_id),
        str(partial.candidate_id),
        str(low.candidate_id),
    ]


def test_category_rounded_ties_count_distinct_postings_and_preserve_equal_order():
    first, second = uuid4(), uuid4()
    a = candidate(category="a", postings=[first])
    b = candidate(category="b", postings=[first, second, second])
    c = candidate(category="c", postings=[first])
    summaries = priority.build_priority_summaries(
        [a, b, c],
        [SkillCategory(category_id=key, label=key) for key in ["a", "b", "c"]],
        [context([first, second])],
        [result(a, 4.25), result(b, 4.26), result(c, 4.34)],
    )
    assert sorted(
        summaries.categories, key=lambda key: summaries.categories[key].display_order
    ) == ["b", "a", "c"]


def test_unselected_posting_cannot_supply_eligibility_or_context_scores():
    selected, foreign = uuid4(), uuid4()
    c = candidate(postings=[foreign])
    summaries = priority.build_priority_summaries(
        [c],
        [SkillCategory(category_id="data", label="Data")],
        [context([selected])],
        [result(c, 5)],
    )
    assert not summaries.candidates
    assert summaries.categories["data"].eligible_count == 0


def test_conflicting_duplicate_components_cannot_inflate_category(policy_case):
    c = policy_case["candidates"][0]
    policy_case["results"].append(result(c, 5))
    summaries = priority.build_priority_summaries(**policy_case)
    assert summaries.candidates[str(c.candidate_id)].value is None
    assert summaries.categories["data"].value == 3.75
    assert summaries.categories["data"].scored_count == 2


def test_fingerprint_ignores_nested_provider_credentials_and_guidance(policy_case):
    inputs = {
        "candidates": policy_case["candidates"],
        "categories": policy_case["categories"],
    }
    before = fingerprint(inputs, policy_case["contexts"])
    changed = deepcopy(inputs)
    changed["candidates"][0].evidence_references[0].update(
        headers={"Authorization": "secret"},
        access_token="secret",
        refresh_token="secret",
    )
    changed["candidates"][0].priority = CandidatePriority(
        value=5,
        basis="ai_estimate",
        complete=True,
        expected_contexts=1,
        scored_contexts=1,
        display_order=99,
    )
    assert fingerprint(changed, policy_case["contexts"]) == before
