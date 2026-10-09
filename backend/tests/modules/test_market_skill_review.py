"""Real PostgreSQL revision, ownership, and durable-run regression tests."""

from uuid import uuid4

import pytest


def _owned_course(client, teacher_auth_headers):
    response = client.post(
        "/courses", json={"title": "Review course"}, headers=teacher_auth_headers
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
        "candidate_revision": 0,
        "selection_revision": 0,
        "categories": [],
        "candidates": [],
        "selected_candidate_ids": [],
        "excluded_candidate_ids": [],
        "recommendations": [],
        "source_outcomes": {},
        "extraction_coverage": {},
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
