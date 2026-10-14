"""Real PostgreSQL revision, ownership, and durable-run regression tests."""

import json
from uuid import uuid4

import pytest


def _owned_course(client, teacher_auth_headers, title="Review course"):
    response = client.post(
        "/courses", json={"title": title}, headers=teacher_auth_headers
    )
    assert response.status_code == 201
    return response.json()


def test_runs_survive_chat_deletion_and_reject_foreign_owner(
    db_session, client, teacher_auth_headers, monkeypatch
):
    course = _owned_course(client, teacher_auth_headers)
    from app.modules.marketdemandanalyst.repository import (
        MarketReviewRepository,
    )

    repo = MarketReviewRepository(db_session)
    run = repo.create_run(
        course["id"], course["teacher_id"], {"sources": ["headhunter"]}
    )
    run_id = run.id
    db_session.commit()
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.modules.marketdemandanalyst import routes

    monkeypatch.setattr(
        routes,
        "get_graph",
        AsyncMock(return_value=(SimpleNamespace(checkpointer=None), None)),
    )
    response = client.delete(
        f"/courses/{course['id']}/market-demand/history", headers=teacher_auth_headers
    )
    assert response.status_code == 200
    assert (
        client.get(
            f"/courses/{course['id']}/market-demand/state", headers=teacher_auth_headers
        ).json()["run_id"]
        is None
    )
    from sqlalchemy.orm import Session

    with Session(bind=db_session.get_bind()) as fresh_session:
        restored = MarketReviewRepository(fresh_session).get_run(
            run_id, course["id"], course["teacher_id"]
        )
        assert restored.config == {"sources": ["headhunter"]}
        assert restored.approval_contract_version == 1
    assert repo.get_run(run_id, course["id"] + 1, course["teacher_id"]) is None
    assert repo.get_run(run_id, course["id"], course["teacher_id"] + 1) is None


def test_manifest_and_draft_use_transactional_revision_checks(
    db_session, client, teacher_auth_headers
):
    course = _owned_course(client, teacher_auth_headers)
    from app.modules.marketdemandanalyst.repository import (
        MarketReviewRepository,
        RevisionConflict,
    )

    repo = MarketReviewRepository(db_session)
    run = repo.create_run(course["id"], course["teacher_id"], {})
    candidate_id = str(uuid4())
    repo.update_manifest(
        run.id,
        course["id"],
        course["teacher_id"],
        expected_candidate_revision=0,
        candidates=[
            {
                "candidate_id": candidate_id,
                "display_name": "Python",
                "category_id": str(uuid4()),
            }
        ],
    )
    repo.save_draft(
        run.id,
        course["id"],
        course["teacher_id"],
        expected_candidate_revision=1,
        expected_selection_revision=0,
        selected_candidate_ids=[candidate_id],
        excluded_candidate_ids=[],
    )
    db_session.commit()
    with pytest.raises(RevisionConflict):
        repo.save_draft(
            run.id,
            course["id"],
            course["teacher_id"],
            expected_candidate_revision=1,
            expected_selection_revision=0,
            selected_candidate_ids=[],
            excluded_candidate_ids=[candidate_id],
        )
    db_session.rollback()
    restored = repo.get_run(run.id, course["id"], course["teacher_id"])
    assert restored.selected_candidate_ids == [candidate_id]
    assert restored.selection_revision == 1


@pytest.mark.parametrize("selected,excluded", [(["foreign"], []), (["same"], ["same"])])
def test_draft_rejects_invalid_ids_without_changing_selection(
    db_session, client, teacher_auth_headers, selected, excluded
):
    course = _owned_course(client, teacher_auth_headers)
    from app.modules.marketdemandanalyst.repository import (
        InvalidCandidateIds,
        MarketReviewRepository,
    )

    repo = MarketReviewRepository(db_session)
    run = repo.create_run(course["id"], course["teacher_id"], {})
    with pytest.raises(InvalidCandidateIds):
        repo.save_draft(
            run.id,
            course["id"],
            course["teacher_id"],
            expected_candidate_revision=0,
            expected_selection_revision=0,
            selected_candidate_ids=selected,
            excluded_candidate_ids=excluded,
        )
    assert run.selection_revision == 0
    assert run.selected_candidate_ids == []


def test_empty_review_dto_is_coherent_and_detached():
    from app.modules.marketdemandanalyst.schemas import SkillReview

    first = SkillReview()
    first.selected_candidate_ids.append(str(uuid4()))
    second = SkillReview()
    assert second.model_dump(mode="json") == {
        "run_id": None,
        "analysis_metadata": None,
        "candidate_revision": 0,
        "selection_revision": 0,
        "categories": [],
        "candidates": [],
        "selected_candidate_ids": [],
        "excluded_candidate_ids": [],
        "recommendations": [],
        "reconciliations": [],
        "source_outcomes": {},
        "extraction_coverage": {},
        "evidence_omissions": [],
        "integration_review": None,
        "publication_revision": 0,
        "approved_references": [],
    }


def test_concurrent_draft_writers_cannot_both_commit_same_revision(
    db_session, client, teacher_auth_headers
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.repository import (
        MarketReviewRepository,
        RevisionConflict,
    )

    course = _owned_course(client, teacher_auth_headers)
    repo = MarketReviewRepository(db_session)
    run = repo.create_run(course["id"], course["teacher_id"], {})
    run_id = run.id
    candidate_id = str(uuid4())
    repo.update_manifest(
        run_id,
        course["id"],
        course["teacher_id"],
        expected_candidate_revision=0,
        candidates=[
            {
                "candidate_id": candidate_id,
                "display_name": "Python",
                "category_id": "programming",
            }
        ],
    )
    db_session.commit()
    barrier = Barrier(2)
    engine = db_session.get_bind()

    def save(selected):
        with Session(bind=engine) as session:
            writer = MarketReviewRepository(session)
            barrier.wait(timeout=10)
            try:
                writer.save_draft(
                    run_id,
                    course["id"],
                    course["teacher_id"],
                    expected_candidate_revision=1,
                    expected_selection_revision=0,
                    selected_candidate_ids=[candidate_id] if selected else [],
                    excluded_candidate_ids=[] if selected else [candidate_id],
                )
                session.commit()
                return "saved"
            except RevisionConflict:
                session.rollback()
                return "stale"

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(save, selected) for selected in (True, False)]
        assert sorted(future.result(timeout=15) for future in futures) == [
            "saved",
            "stale",
        ]
    with Session(bind=engine) as session:
        restored = MarketReviewRepository(session).get_run(
            run_id, course["id"], course["teacher_id"]
        )
        assert restored.selection_revision == 1
        assert set(
            restored.selected_candidate_ids + restored.excluded_candidate_ids
        ) == {candidate_id}


def active_review(db_session, client, headers):
    """Persist an owned two-candidate run and its real disposable pointer."""
    from app.modules.marketdemandanalyst.models import MDAThreadState
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    course = _owned_course(client, headers)
    repo = MarketReviewRepository(db_session)
    run = repo.create_run(
        course["id"],
        course["teacher_id"],
        {"sources": ["headhunter"], "evidence_sources": ["jobs", "onet"]},
    )
    ids = [str(uuid4()), str(uuid4())]
    repo.update_manifest(
        run.id,
        course["id"],
        course["teacher_id"],
        expected_candidate_revision=0,
        candidates=[
            {
                "candidate_id": ids[0],
                "display_name": "Python",
                "category_id": "technical",
                "identity_key": "private",
                "onet_associations": [
                    {
                        "relation": "broader",
                        "evidence": {
                            "ratings": {"IM": {"value": 4.2, "status": "suppressed"}}
                        },
                    }
                ],
            },
            {
                "candidate_id": ids[1],
                "display_name": "Communication",
                "category_id": "transferable",
            },
        ],
        categories=[
            {"category_id": "technical", "label": "Technical"},
            {"category_id": "transferable", "label": "Transferable"},
        ],
    )
    db_session.add(
        MDAThreadState(
            thread_id=f"mda-{course['teacher_id']}-course-{course['id']}",
            state_json={
                "run_id": str(run.id),
                "course_id": course["id"],
                "teacher_id": course["teacher_id"],
                "candidate_revision": 1,
            },
        )
    )
    db_session.commit()
    return course, run.id, ids


def draft_body(run_id, selected, excluded, revision=0, candidate_revision=1):
    return {
        "run_id": str(run_id),
        "expected_candidate_revision": candidate_revision,
        "expected_selection_revision": revision,
        "selected_candidate_ids": selected,
        "excluded_candidate_ids": excluded,
    }


def test_inline_confirmation_saves_exact_choices_evidence_and_reconciliation(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    run = db_session.get(MarketAnalysisRun, run_id)
    old_id, reconciliation_id = str(uuid4()), str(uuid4())
    run.source_outcomes = {
        "headhunter": {"status": "error", "warnings": ["Application unavailable"]}
    }
    run.candidate_manifest = {
        **run.candidate_manifest,
        "reconciliations": [
            {
                "reconciliation_id": reconciliation_id,
                "candidate_id": ids[0],
                "previous_candidate_ids": [old_id],
                "previous_selected_candidate_ids": [old_id],
                "previous_excluded_candidate_ids": [],
                "reason": "ambiguous_equivalent_merge",
                "resolved": False,
            }
        ],
    }
    db_session.commit()
    base = review_url(course)
    omissions = ["headhunter: Application unavailable", "headhunter: error"]
    assert (
        client.get(base, headers=teacher_auth_headers).json().get("evidence_omissions")
        == omissions
    )
    body = {
        **draft_body(run_id, [ids[1]], [ids[0]]),
        "confirm_current_evidence": True,
        "expected_omissions": omissions,
    }
    response = client.post(
        base + "/selection-confirmation", headers=teacher_auth_headers, json=body
    )
    assert response.status_code == 200, response.text
    assert response.json()["selected_candidate_ids"] == [ids[1]]
    assert response.json()["excluded_candidate_ids"] == [ids[0]]
    assert response.json()["reconciliations"][0]["resolved"] is True
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    assert run.selection_revision == 1
    assert run.selection_confirmation["selected_candidate_ids"] == [ids[1]]
    assert run.selection_confirmation["excluded_candidate_ids"] == [ids[0]]
    assert run.selection_confirmation["acknowledged_omissions"] == omissions
    assert run.publication_revision == 0
    assert run.approved_references == []
    snapshot = db_session.get(
        MDAThreadState, f"mda-{course['teacher_id']}-course-{course['id']}"
    ).state_json
    assert snapshot["curated_skills"][0]["candidate_id"] == ids[1]
    assert snapshot["curriculum_mapping"] is None


@pytest.mark.parametrize(
    "kind,status",
    [
        ("consent", 422),
        ("missing_exclusions", 422),
        ("missing_omissions", 422),
        ("changed_omissions", 409),
        ("foreign", 422),
        ("overlap", 422),
        ("duplicate", 422),
        ("stale", 409),
        ("empty", 422),
    ],
)
def test_inline_confirmation_rejects_invalid_payload_without_draft_write(
    db_session, client, teacher_auth_headers, kind, status
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    body = {
        **draft_body(run_id, [ids[0]], [ids[1]]),
        "confirm_current_evidence": True,
        "expected_omissions": [],
    }
    if kind == "consent":
        body["confirm_current_evidence"] = False
    elif kind == "missing_exclusions":
        body.pop("excluded_candidate_ids")
    elif kind == "missing_omissions":
        body.pop("expected_omissions")
    elif kind == "changed_omissions":
        body["expected_omissions"] = ["old source warning"]
    elif kind == "foreign":
        body["selected_candidate_ids"] = [str(uuid4())]
    elif kind == "overlap":
        body["excluded_candidate_ids"] = [ids[0]]
    elif kind == "duplicate":
        body["selected_candidate_ids"] = [ids[0], ids[0]]
    elif kind == "stale":
        body["expected_candidate_revision"] = 0
    elif kind == "empty":
        body["selected_candidate_ids"] = []
    response = client.post(
        review_url(course) + "/selection-confirmation",
        headers=teacher_auth_headers,
        json=body,
    )
    assert response.status_code == status, response.text
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    assert run.selected_candidate_ids == []
    assert run.selection_revision == 0
    assert run.selection_confirmation is None


def test_inline_confirmation_snapshot_failure_rolls_back_all_decisions(
    db_session, client, teacher_auth_headers
):
    from sqlalchemy import event

    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    body = {
        **draft_body(run_id, [ids[0]], [ids[1]]),
        "confirm_current_evidence": True,
        "expected_omissions": [],
    }

    def fail_snapshot(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("UPDATE mda_thread_state"):
            raise RuntimeError("simulated inline snapshot failure")

    event.listen(db_session.get_bind(), "before_cursor_execute", fail_snapshot)
    try:
        with pytest.raises(RuntimeError, match="inline snapshot failure"):
            client.post(
                review_url(course) + "/selection-confirmation",
                headers=teacher_auth_headers,
                json=body,
            )
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", fail_snapshot)
    db_session.rollback()
    run = db_session.get(MarketAnalysisRun, run_id, populate_existing=True)
    assert run.selected_candidate_ids == []
    assert run.excluded_candidate_ids == []
    assert run.selection_revision == 0
    assert run.selection_confirmation is None
    assert "acknowledged_omissions" not in run.candidate_manifest


def test_inline_confirmation_keeps_removed_exclusions_in_history_without_transfer(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    run = db_session.get(MarketAnalysisRun, run_id)
    old_id = str(uuid4())
    run.candidate_manifest = {
        **run.candidate_manifest,
        "candidate_history": [
            {"candidate_id": old_id, "selected": False, "excluded": True}
        ],
        "reconciliations": [
            {
                "reconciliation_id": str(uuid4()),
                "candidate_id": None,
                "previous_candidate_ids": [old_id],
                "reason": "candidate_no_longer_observed",
                "previous_excluded_candidate_ids": [old_id],
                "resolved": False,
            }
        ],
    }
    db_session.commit()
    response = client.post(
        review_url(course) + "/selection-confirmation",
        headers=teacher_auth_headers,
        json={
            **draft_body(run_id, [ids[0]], [ids[1]]),
            "confirm_current_evidence": True,
            "expected_omissions": [],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["selected_candidate_ids"] == [ids[0]]
    assert response.json()["excluded_candidate_ids"] == [ids[1]]
    assert response.json()["reconciliations"][0]["resolved"] is True
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    assert run.candidate_manifest["candidate_history"][0]["excluded"] is True
    assert run.candidate_manifest["candidate_history"][0]["selected"] is False


def test_candidate_advice_summary_separates_job_skills_from_references(
    db_session, client, teacher_auth_headers
):
    from copy import deepcopy

    from app.modules.marketdemandanalyst import review_service
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.schemas import ProviderVacancy
    from app.modules.marketdemandanalyst.state import bind_tool_store
    from app.modules.marketdemandanalyst.tools import get_skills_by_category

    course, run_id, _ = active_review(db_session, client, teacher_auth_headers)
    repo = MarketReviewRepository(db_session)
    run = db_session.get(MarketAnalysisRun, run_id)
    postings = [
        repo.upsert_vacancy_snapshot(
            run_id,
            ProviderVacancy(
                provider="headhunter",
                native_id=f"advice-{index}",
                original_url=f"https://hh.uz/vacancy/advice-{index}",
                title="Developer",
                original_description="Retained posting body",
                description_text="Retained posting body",
                skill_tags=[f"Job skill {i}" for i in range(index, 58, 7)],
                raw_payload={},
            ),
        )
        for index in range(7)
    ]
    association = {
        "relation": "related",
        "evidence": {"label": "Programming", "ratings": {"IM": {"value": 3.38}}},
    }
    candidates = []
    for index in range(452):
        supported = index < 58
        posting = postings[index % 7]
        candidates.append(
            {
                "candidate_id": str(uuid4()),
                "display_name": f"Job skill {index}"
                if supported
                else f"Reference {index}",
                "category_id": "technical",
                "original_labels": [f"Original {index}"],
                "aliases": [f"Alias {index}"],
                "recommendation_reasons": ["Consider curriculum fit"],
                "onet_associations": [deepcopy(association)],
                "posting_support": "supported" if supported else "missing",
                "qualifying_posting_links": [posting.original_url] if supported else [],
                "job_metrics": {"supporting_posting_count": 1 if supported else 0},
                "evidence_references": [
                    {
                        "snapshot_id": str(posting.id),
                        "provider": "headhunter",
                        "original_url": posting.original_url,
                        "original_phrase": f"Job skill {index}",
                        "evidence_kind": "provider_tag",
                    }
                ]
                if supported
                else [],
            }
        )
    repo.update_manifest(
        run_id,
        course["id"],
        course["teacher_id"],
        expected_candidate_revision=1,
        candidates=candidates,
        categories=[{"category_id": "technical", "label": "Technical"}],
    )
    repo.save_draft(
        run_id,
        course["id"],
        course["teacher_id"],
        expected_candidate_revision=2,
        expected_selection_revision=0,
        selected_candidate_ids=[candidates[0]["candidate_id"]],
        excluded_candidate_ids=[candidates[1]["candidate_id"]],
    )
    run.extraction_coverage = {"selected_postings": 7, "assessed_postings": 7}
    repo.commit()
    review = review_service.SkillReviewService(repo).get_review(
        course["id"], course["teacher_id"]
    )
    summary = review_service.candidate_advice_summary(review)
    assert summary["evidence_counts"] == {
        "job_backed_candidates": 58,
        "reference_only_candidates": 394,
        "unavailable_candidates": 0,
        "selected_postings": 7,
        "assessed_postings": 7,
    }
    assert len(summary["candidates"]) == 452
    assert all("evidence_references" not in c for c in summary["candidates"])
    assert summary["candidate_revision"] == 2
    assert summary["selection_revision"] == 1
    assert summary["selected_candidate_ids"] == [candidates[0]["candidate_id"]]
    assert summary["excluded_candidate_ids"] == [candidates[1]["candidate_id"]]
    assert summary["candidates"][0]["onet_associations"] == [association]
    assert summary["candidates"][0]["aliases"] == ["Alias 0"]
    assert summary["candidates"][0]["original_labels"] == ["Original 0"]
    assert summary["candidates"][0]["recommendation_reasons"] == [
        "Consider curriculum fit"
    ]
    assert summary["candidates"][0]["job_metrics"] == {"supporting_posting_count": 1}
    assert (
        not {"integration_review", "approved_references", "recommendations"}
        & summary.keys()
    )
    assert "Retained posting body" not in json.dumps(summary)
    assert review.candidates[0].evidence_references
    with bind_tool_store(
        {
            "run_id": str(run_id),
            "course_id": course["id"],
            "teacher_id": course["teacher_id"],
        }
    ):
        assert json.loads(get_skills_by_category.invoke({})) == summary


@pytest.mark.parametrize(
    "coverage,selected,assessed",
    [
        ({}, None, None),
        ({"selected_postings": 0, "assessed_postings": 0}, 0, 0),
        ({"selected_postings": 7}, 7, None),
    ],
)
def test_candidate_advice_summary_does_not_invent_coverage(
    db_session, client, teacher_auth_headers, coverage, selected, assessed
):
    from app.modules.marketdemandanalyst import review_service
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    course, run_id, _ = active_review(db_session, client, teacher_auth_headers)
    run = db_session.get(MarketAnalysisRun, run_id)
    run.extraction_coverage = coverage
    db_session.commit()
    review = review_service.SkillReviewService(
        MarketReviewRepository(db_session)
    ).get_review(course["id"], course["teacher_id"])
    assert review_service.candidate_advice_summary(review)["evidence_counts"] == {
        "job_backed_candidates": 0,
        "reference_only_candidates": 1,
        "unavailable_candidates": 1,
        "selected_postings": selected,
        "assessed_postings": assessed,
    }


@pytest.mark.parametrize(
    "links",
    [
        [],
        ["file:///tmp/posting"],
        ["https:///vacancy/1"],
        ["https://user:secret@hh.uz/vacancy/1"],
    ],
)
def test_candidate_advice_summary_requires_valid_posting_url(
    db_session, client, teacher_auth_headers, links
):
    from copy import deepcopy

    from app.modules.marketdemandanalyst import review_service
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    course, run_id, _ = active_review(db_session, client, teacher_auth_headers)
    run = db_session.get(MarketAnalysisRun, run_id)
    manifest = deepcopy(run.candidate_manifest)
    manifest["candidates"][1].update(
        posting_support="supported", qualifying_posting_links=links
    )
    run.candidate_manifest = manifest
    db_session.commit()
    review = review_service.SkillReviewService(
        MarketReviewRepository(db_session)
    ).get_review(course["id"], course["teacher_id"])
    counts = review_service.candidate_advice_summary(review)["evidence_counts"]
    assert counts["job_backed_candidates"] == 0
    assert counts["reference_only_candidates"] == 1
    assert counts["unavailable_candidates"] == 1


@pytest.mark.parametrize("foreign", ["run", "owner"])
def test_candidate_advice_tool_rejects_wrong_run_or_owner(
    db_session, client, teacher_auth_headers, foreign
):
    from app.modules.marketdemandanalyst.state import bind_tool_store
    from app.modules.marketdemandanalyst.tools import get_skills_by_category

    course, run_id, _ = active_review(db_session, client, teacher_auth_headers)
    state = {
        "run_id": str(run_id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
    }
    if foreign == "run":
        state["run_id"] = str(uuid4())
    else:
        state["teacher_id"] += 1
    with bind_tool_store(state):
        result = get_skills_by_category.invoke({})
    assert "candidate_id" not in result
    assert (
        result.startswith("Candidate review unavailable:")
        if foreign == "owner"
        else result == "Review must belong to the active analysis."
    )


def review_url(course):
    return f"/courses/{course['id']}/market-demand/skill-review"


def test_review_reload_acknowledges_empty_and_pending_draft(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    base = review_url(course)
    empty = client.get(base, headers=teacher_auth_headers)
    assert empty.status_code == 200
    assert empty.json()["selected_candidate_ids"] == []
    saved = client.put(
        base + "/draft", headers=teacher_auth_headers, json=draft_body(run_id, ids, [])
    )
    assert saved.status_code == 200
    assert saved.json()["selected_candidate_ids"] == ids
    assert saved.json()["candidates"][0]["posting_support"] == "missing"
    assert "identity_key" not in saved.json()["candidates"][0]
    assert saved.json()["candidates"][0]["onet_associations"][0]["evidence"]["ratings"][
        "IM"
    ] == {"value": 4.2, "status": "suppressed"}
    assert client.get(base, headers=teacher_auth_headers).json() == saved.json()
    db_session.expire_all()
    snapshot = db_session.get(
        MDAThreadState, f"mda-{course['teacher_id']}-course-{course['id']}"
    ).state_json
    assert snapshot["selected_candidate_ids"] == ids
    assert snapshot["selection_revision"] == 1
    cleared = client.put(
        base + "/draft",
        headers=teacher_auth_headers,
        json=draft_body(run_id, [], [], 1),
    )
    assert cleared.status_code == 200
    assert cleared.json()["selected_candidate_ids"] == []
    db_session.expire_all()
    assert db_session.get(MarketAnalysisRun, run_id).publication_revision == 0


@pytest.mark.parametrize(
    "kind,status",
    [
        ("overlap", 422),
        ("foreign", 422),
        ("duplicate", 422),
        ("candidate_revision", 409),
        ("selection_revision", 409),
    ],
)
def test_review_draft_validation_is_atomic(
    db_session, client, teacher_auth_headers, kind, status
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    body = draft_body(run_id, [ids[0]], [ids[1]])
    if kind == "overlap":
        body["excluded_candidate_ids"] = [ids[0]]
    if kind == "foreign":
        body["selected_candidate_ids"] = [str(uuid4())]
    if kind == "duplicate":
        body["selected_candidate_ids"] = [ids[0], ids[0]]
    if kind == "candidate_revision":
        body["expected_candidate_revision"] = 0
    if kind == "selection_revision":
        body["expected_selection_revision"] = 10
    response = client.put(
        review_url(course) + "/draft", json=body, headers=teacher_auth_headers
    )
    assert response.status_code == status
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    assert run.selected_candidate_ids == []
    assert run.selection_revision == 0


def test_confirmation_requires_nonempty_exact_current_draft(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    base = review_url(course)
    revisions = {
        "run_id": str(run_id),
        "expected_candidate_revision": 1,
        "expected_selection_revision": 0,
    }
    assert (
        client.post(
            base + "/selection-confirmation",
            json=revisions,
            headers=teacher_auth_headers,
        ).status_code
        == 422
    )
    saved = client.put(
        base + "/draft",
        json=draft_body(run_id, [ids[0]], [ids[1]]),
        headers=teacher_auth_headers,
    )
    assert saved.status_code == 200
    revisions["expected_selection_revision"] = 1
    # Confirmation is a shortlist for mapping, including pending references.
    assert (
        client.post(
            base + "/selection-confirmation",
            json=revisions,
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    db_session.expire_all()
    confirmation = db_session.get(MarketAnalysisRun, run_id).selection_confirmation
    assert confirmation["selected_candidate_ids"] == [ids[0]]
    assert confirmation["teacher_id"] == course["teacher_id"]
    changed = client.put(
        base + "/draft",
        json=draft_body(run_id, [], ids, 1),
        headers=teacher_auth_headers,
    )
    assert changed.status_code == 200
    db_session.expire_all()
    assert db_session.get(MarketAnalysisRun, run_id).selection_confirmation is None


@pytest.mark.parametrize("operation", ["draft", "selection-confirmation"])
def test_failed_snapshot_write_rolls_back_draft_and_confirmation(
    db_session, client, teacher_auth_headers, monkeypatch, operation
):
    from sqlalchemy import event

    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    base = review_url(course)

    def fail_snapshot(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("UPDATE mda_thread_state"):
            raise RuntimeError("simulated snapshot write failure")

    if operation == "selection-confirmation":
        assert (
            client.put(
                base + "/draft",
                json=draft_body(run_id, [ids[0]], []),
                headers=teacher_auth_headers,
            ).status_code
            == 200
        )
    event.listen(db_session.get_bind(), "before_cursor_execute", fail_snapshot)
    try:
        with pytest.raises(RuntimeError, match="snapshot write failure"):
            if operation == "draft":
                client.put(
                    base + "/draft",
                    json=draft_body(run_id, [ids[0]], []),
                    headers=teacher_auth_headers,
                )
            else:
                client.post(
                    base + "/selection-confirmation",
                    json={
                        "run_id": str(run_id),
                        "expected_candidate_revision": 1,
                        "expected_selection_revision": 1,
                    },
                    headers=teacher_auth_headers,
                )
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", fail_snapshot)
    db_session.rollback()
    run = db_session.get(MarketAnalysisRun, run_id, populate_existing=True)
    assert run.selected_candidate_ids == ([] if operation == "draft" else [ids[0]])
    assert run.selection_revision == (0 if operation == "draft" else 1)
    assert run.selection_confirmation is None
    retry = client.put(
        base + "/draft",
        json=draft_body(run_id, [ids[0]], [], run.selection_revision),
        headers=teacher_auth_headers,
    )
    assert retry.status_code == 200


def test_clear_history_never_reactivates_old_review_and_wrong_course_rejected(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    other = _owned_course(client, teacher_auth_headers, title="Other review course")
    assert (
        client.put(
            review_url(other) + "/draft",
            json=draft_body(run_id, ids, []),
            headers=teacher_auth_headers,
        ).status_code
        == 422
    )
    db_session.delete(
        db_session.get(
            MDAThreadState, f"mda-{course['teacher_id']}-course-{course['id']}"
        )
    )
    db_session.commit()
    empty = client.get(review_url(course), headers=teacher_auth_headers)
    assert empty.status_code == 200
    assert empty.json()["run_id"] is None
    assert (
        client.put(
            review_url(course) + "/draft",
            json=draft_body(run_id, ids, []),
            headers=teacher_auth_headers,
        ).status_code
        == 409
    )
    assert db_session.get(MarketAnalysisRun, run_id).selected_candidate_ids == []


def test_reconciliations_reload_resolve_only_explicit_teacher_ids(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    run = db_session.get(MarketAnalysisRun, run_id)
    old_id, reconciliation_id = str(uuid4()), str(uuid4())
    run.candidate_manifest = {
        **run.candidate_manifest,
        "reconciliation_required": True,
        "candidate_history": [
            {
                "candidate_id": old_id,
                "identity_key": "private",
                "display_name": "Prior Python",
                "selected": False,
                "excluded": True,
                "superseded_by_candidate_id": ids[0],
            }
        ],
        "reconciliations": [
            {
                "reconciliation_id": reconciliation_id,
                "candidate_id": ids[0],
                "previous_candidate_ids": [old_id],
                "reason": "ambiguous_equivalent_merge",
                "historical_candidates": [
                    {
                        "candidate_id": old_id,
                        "identity_key": "private",
                        "display_name": "Prior Python",
                        "excerpt": "secret content",
                    }
                ],
                "previous_selected_candidate_ids": [],
                "previous_excluded_candidate_ids": [old_id],
                "resolved": False,
            }
        ],
    }
    db_session.commit()
    base = review_url(course)
    loaded = client.get(base, headers=teacher_auth_headers)
    assert loaded.status_code == 200
    record = loaded.json()["reconciliations"][0]
    assert record["previous_candidates"] == [
        {"candidate_id": old_id, "display_name": "Prior Python"}
    ]
    assert "private" not in str(record) and "secret content" not in str(record)
    saved = client.put(
        base + "/draft",
        json=draft_body(run_id, [ids[0]], []),
        headers=teacher_auth_headers,
    )
    assert saved.status_code == 200
    assert not saved.json()["reconciliations"][0]["resolved"]
    blocked = client.post(
        base + "/selection-confirmation",
        json={
            "run_id": str(run_id),
            "expected_candidate_revision": 1,
            "expected_selection_revision": 1,
        },
        headers=teacher_auth_headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "reconciliation_required"
    body = {
        **draft_body(run_id, [ids[0]], [], 1),
        "resolved_reconciliation_ids": [str(uuid4())],
    }
    assert (
        client.put(base + "/draft", json=body, headers=teacher_auth_headers).status_code
        == 422
    )
    body["resolved_reconciliation_ids"] = [reconciliation_id]
    resolved = client.put(base + "/draft", json=body, headers=teacher_auth_headers)
    assert resolved.status_code == 200
    assert resolved.json()["reconciliations"][0]["resolved"]
    db_session.expire_all()
    history = db_session.get(MarketAnalysisRun, run_id).candidate_manifest[
        "candidate_history"
    ]
    prior = next(item for item in history if item["candidate_id"] == old_id)
    assert prior["selected"] is True and prior["excluded"] is False


def test_continuation_acknowledges_exact_omissions_and_stale_changes_block(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    run = db_session.get(MarketAnalysisRun, run_id)
    run.source_outcomes = {
        "headhunter": {"status": "error", "warnings": ["rate limited"]},
        "onet": {"status": "success"},
    }
    run.extraction_coverage = {"status": "partial", "warnings": ["tail uncovered"]}
    db_session.commit()
    body = {
        "run_id": str(run_id),
        "expected_candidate_revision": 1,
        "expected_selection_revision": 0,
    }
    response = client.post(
        review_url(course) + "/continue-with-available-evidence",
        json=body,
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["extraction_coverage"]["acknowledged"]
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    assert run.candidate_manifest["acknowledged_omissions"] == [
        "extraction: partial",
        "headhunter: error",
        "headhunter: rate limited",
        "tail uncovered",
    ]
    assert run.selected_candidate_ids == [] and run.selection_confirmation is None
    run.extraction_coverage = {"status": "failed", "warnings": ["new failure"]}
    db_session.commit()
    assert not client.get(review_url(course), headers=teacher_auth_headers).json()[
        "extraction_coverage"
    ]["acknowledged"]


def test_confirmation_requires_current_omissions_acknowledgement(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    base = review_url(course)
    assert (
        client.put(
            base + "/draft",
            json=draft_body(run_id, [ids[0]], []),
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    run.source_outcomes = {"headhunter": {"status": "error", "warnings": ["timeout"]}}
    db_session.commit()
    body = {
        "run_id": str(run_id),
        "expected_candidate_revision": 1,
        "expected_selection_revision": 1,
    }
    blocked = client.post(
        base + "/selection-confirmation", json=body, headers=teacher_auth_headers
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "omissions_acknowledgement_required"
    assert (
        client.post(
            base + "/continue-with-available-evidence",
            json=body,
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            base + "/selection-confirmation", json=body, headers=teacher_auth_headers
        ).status_code
        == 200
    )
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    assert run.publication_revision == 0 and run.approved_references == []
    run.source_outcomes = {
        "headhunter": {"status": "error", "warnings": ["new failure"]}
    }
    db_session.commit()
    assert (
        client.post(
            base + "/selection-confirmation", json=body, headers=teacher_auth_headers
        ).status_code
        == 409
    )


def test_resolved_history_retry_preserves_explicit_decisions_and_late_candidates(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.evidence import reconcile_candidates
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    run = db_session.get(MarketAnalysisRun, run_id)
    old_id, record_id = str(uuid4()), str(uuid4())
    run.candidate_manifest = {
        **run.candidate_manifest,
        "candidate_history": [
            {
                "candidate_id": old_id,
                "identity_key": "private",
                "display_name": "Prior Python",
                "selected": True,
                "excluded": False,
                "superseded_by_candidate_id": ids[0],
            }
        ],
        "reconciliations": [
            {
                "reconciliation_id": record_id,
                "candidate_id": ids[0],
                "previous_candidate_ids": [old_id],
                "reason": "ambiguous_equivalent_merge",
                "resolved": False,
            }
        ],
    }
    db_session.commit()
    body = {
        **draft_body(run_id, [ids[1]], [ids[0]]),
        "resolved_reconciliation_ids": [record_id],
    }
    assert (
        client.put(
            review_url(course) + "/draft", json=body, headers=teacher_auth_headers
        ).status_code
        == 200
    )
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    observations = [
        {"identity_key": "private", "name": "Python", "category": "technical"},
        {
            "identity_key": "communication",
            "name": "Communication",
            "category": "transferable",
        },
        {"identity_key": "late", "name": "SQL", "category": "technical"},
    ]
    # Give the unchanged candidate the production extractor's identity key.
    manifest = dict(run.candidate_manifest)
    manifest["candidates"][1]["identity_key"] = "communication"
    retried = reconcile_candidates(
        observations,
        {
            **manifest,
            "selected_candidate_ids": run.selected_candidate_ids,
            "excluded_candidate_ids": run.excluded_candidate_ids,
        },
    )
    assert retried["selected_candidate_ids"] == [ids[1]]
    assert retried["excluded_candidate_ids"] == [ids[0]]
    assert not retried["reconciliation_required"]
    prior = next(h for h in retried["candidate_history"] if h["candidate_id"] == old_id)
    assert prior["excluded"] is True and prior["selected"] is False
    # Reappearance after an empty retry must use those current choices, not stale historical approval.
    absent = reconcile_candidates([], retried)
    run.candidate_manifest = absent
    run.selected_candidate_ids = []
    run.excluded_candidate_ids = []
    run.candidate_revision += 1
    db_session.commit()
    pending = [
        r["reconciliation_id"] for r in absent["reconciliations"] if not r["resolved"]
    ]
    response = client.put(
        review_url(course) + "/draft",
        json={
            **draft_body(run_id, [], [], 1, 2),
            "resolved_reconciliation_ids": pending,
        },
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    restored = reconcile_candidates(observations, run.candidate_manifest)
    assert (
        restored["selected_candidate_ids"] == []
        and restored["excluded_candidate_ids"] == []
    )


def test_unresolved_reconciliation_blocks_even_empty_shortlist_confirmation(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    run = db_session.get(MarketAnalysisRun, run_id)
    run.candidate_manifest = {
        **run.candidate_manifest,
        "reconciliations": [
            {
                "reconciliation_id": str(uuid4()),
                "candidate_id": None,
                "previous_candidate_ids": [],
                "reason": "candidate_no_longer_observed",
                "resolved": False,
            }
        ],
    }
    db_session.commit()
    response = client.post(
        review_url(course) + "/selection-confirmation",
        json={
            "run_id": str(run_id),
            "expected_candidate_revision": 1,
            "expected_selection_revision": 0,
        },
        headers=teacher_auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "reconciliation_required"


@pytest.mark.parametrize(
    "config,expected",
    [
        (
            {
                "country": "uzbekistan",
                "sources": ["headhunter"],
                "evidence_sources": ["jobs", "onet"],
                "onet_release": "30.1",
                "selected_onet_occupations": [
                    {"soc_code": "15-1252.00", "title": "Software Developers"}
                ],
            },
            {
                "country": "uzbekistan",
                "job_sources": ["headhunter"],
                "evidence_sources": ["jobs", "onet"],
                "onet_release": "30.1",
                "occupations": [
                    {"soc_code": "15-1252.00", "title": "Software Developers"}
                ],
            },
        ),
        (
            {},
            {
                "country": None,
                "job_sources": [],
                "evidence_sources": [],
                "onet_release": None,
                "occupations": [],
            },
        ),
        (
            {
                "country": None,
                "sources": None,
                "evidence_sources": None,
                "onet_release": None,
                "selected_onet_occupations": None,
            },
            {
                "country": None,
                "job_sources": [],
                "evidence_sources": [],
                "onet_release": None,
                "occupations": [],
            },
        ),
    ],
)
def test_review_metadata_comes_from_its_run_not_thread_or_latest_run(
    db_session, client, teacher_auth_headers, config, expected
):
    from datetime import UTC, datetime

    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.review_service import SkillReviewService

    course = _owned_course(client, teacher_auth_headers)
    repo = MarketReviewRepository(db_session)
    run = repo.create_run(course["id"], course["teacher_id"], config)
    run.created_at = datetime(2026, 1, 1, 12, tzinfo=UTC)
    run.updated_at = datetime(2026, 1, 2, 12, tzinfo=UTC)
    repo.create_run(
        course["id"],
        course["teacher_id"],
        {"country": "united_states", "onet_release": "other"},
    )
    repo.save_configuration_snapshot(
        SkillReviewService.thread_id(course["id"], course["teacher_id"]),
        {
            "run_id": str(run.id),
            "job_search_country": "united_states",
            "onet_release": "other",
        },
    )
    db_session.commit()
    response = client.get(
        f"/courses/{course['id']}/market-demand/skill-review",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200
    review = response.json()
    assert review["run_id"] == str(run.id)
    metadata = review["analysis_metadata"]
    assert {
        key: value
        for key, value in metadata.items()
        if key not in {"created_at", "updated_at"}
    } == expected
    assert datetime.fromisoformat(metadata["created_at"]) == run.created_at
    assert datetime.fromisoformat(metadata["updated_at"]) == run.updated_at
    # DTO collections remain detached from the persisted configuration.
    dto = SkillReviewService.review_from_run(run)
    dto.analysis_metadata.job_sources.append("indeed")
    assert run.config == config


def test_no_active_run_has_no_analysis_metadata(client, teacher_auth_headers):
    course = _owned_course(client, teacher_auth_headers)
    response = client.get(
        f"/courses/{course['id']}/market-demand/skill-review",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["analysis_metadata"] is None


@pytest.mark.parametrize(
    "occupation,expected_title",
    [
        ({"soc_code": "15-1252.00"}, "15-1252.00"),
        ({"soc_code": "15-1252.00", "title": None}, "15-1252.00"),
        ({"soc_code": "15-1252.00", "title": ""}, "15-1252.00"),
        ({"soc_code": "15-1252.00", "title": " \t\n"}, "15-1252.00"),
        (
            {"soc_code": "15-1252.00", "title": "  Software Developers  "},
            "  Software Developers  ",
        ),
    ],
    ids=["missing-title", "null-title", "empty-title", "blank-title", "stored-title"],
)
def test_review_metadata_preserves_legacy_occupation_codes_without_rewriting_config(
    db_session, client, teacher_auth_headers, occupation, expected_title
):
    from copy import deepcopy
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.models import MarketAnalysisRun
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.review_service import SkillReviewService

    course = _owned_course(client, teacher_auth_headers)
    config = {
        "country": "uzbekistan",
        "sources": ["headhunter"],
        "evidence_sources": ["jobs", "onet"],
        "onet_release": "30.1",
        "selected_onet_occupations": [
            occupation,
            {"soc_code": "15-1253.00", "title": "Software Quality Assurance Analysts"},
        ],
    }
    stored_config = deepcopy(config)
    repo = MarketReviewRepository(db_session)
    run = repo.create_run(course["id"], course["teacher_id"], config)
    repo.save_configuration_snapshot(
        SkillReviewService.thread_id(course["id"], course["teacher_id"]),
        {"run_id": str(run.id), "onet_release": "other-release"},
    )
    db_session.commit()
    created_at, updated_at = run.created_at, run.updated_at
    response = client.get(
        f"/courses/{course['id']}/market-demand/skill-review",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200
    review = response.json()
    assert review["run_id"] == str(run.id)
    metadata = review["analysis_metadata"]
    assert metadata["onet_release"] == "30.1"
    assert metadata["occupations"] == [
        {"soc_code": "15-1252.00", "title": expected_title},
        {"soc_code": "15-1253.00", "title": "Software Quality Assurance Analysts"},
    ]
    assert datetime.fromisoformat(metadata["created_at"]) == created_at
    assert datetime.fromisoformat(metadata["updated_at"]) == updated_at
    assert run.config == stored_config
    dto = SkillReviewService.review_from_run(run)
    dto.analysis_metadata.occupations[0].title = "Changed response label"
    assert run.config == stored_config
    with Session(bind=db_session.get_bind()) as fresh_session:
        stored_run = fresh_session.get(MarketAnalysisRun, run.id)
        assert stored_run.config == stored_config
        assert stored_run.created_at == created_at
        assert stored_run.updated_at == updated_at
