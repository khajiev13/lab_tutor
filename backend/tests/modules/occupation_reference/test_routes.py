from uuid import uuid4

import pytest


def import_catalog(db_session, parsed_release):
    from app.modules.occupation_reference.repository import (
        OccupationReferenceRepository,
    )

    OccupationReferenceRepository(db_session).import_release(
        parsed_release, activate=True
    )


def activate_run(db_session, run):
    from app.modules.marketdemandanalyst.models import MDAThreadState

    db_session.merge(
        MDAThreadState(
            thread_id=f"mda-{run.teacher_id}-course-{run.course_id}",
            state_json={
                **run.config,
                "run_id": str(run.id),
                "candidate_revision": run.candidate_revision,
            },
        )
    )


def test_owner_catalog_search_alias_pagination_and_literal_wildcards(
    db_session, client, course, teacher_auth_headers, parsed_release
):
    import_catalog(db_session, parsed_release)
    base = f"/courses/{course['id']}/occupation-reference"
    releases = client.get(base + "/releases", headers=teacher_auth_headers)
    assert releases.status_code == 200
    assert releases.json()["items"][0]["version"] == "31.0"
    for query in ("Data", "Analytics", "15-2051.00"):
        response = client.get(
            base + "/occupations",
            params={"release": "31.0", "q": query, "limit": 1},
            headers=teacher_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["items"][0]["soc_code"] == "15-2051.00"
        assert response.json()["total"] == 1
    response = client.get(
        base + "/occupations",
        params={"release": "31.0", "q": "%%"},
        headers=teacher_auth_headers,
    )
    assert response.json()["total"] == 0
    response = client.get(
        base + "/occupations/15-2051.00/skills",
        params={"release": "31.0"},
        headers=teacher_auth_headers,
    )
    assert len(response.json()["items"]) == 4
    assert response.json()["items"][0]["occupation_title"] == "Data Scientists"
    assert (
        client.get(
            base + "/occupations",
            params={"release": "31.0", "q": "D"},
            headers=teacher_auth_headers,
        ).status_code
        == 422
    )


def test_foreign_course_cannot_read_catalog(
    db_session, client, course, teacher_auth_headers
):
    from app.modules.courses.models import Course

    other = Course(title="Foreign", teacher_id=course["teacher_id"] + 1)
    # The other owner must exist to satisfy the real FK.
    from app.modules.auth.models import User, UserRole

    owner = User(
        email="foreign@example.com",
        hashed_password="unused",
        first_name="Other",
        last_name="Teacher",
        role=UserRole.TEACHER,
    )
    db_session.add(owner)
    db_session.flush()
    other.teacher_id = owner.id
    db_session.add(other)
    db_session.commit()
    assert (
        client.get(
            f"/courses/{other.id}/occupation-reference/releases",
            headers=teacher_auth_headers,
        ).status_code
        == 404
    )


def test_empty_catalog_lists_empty_and_lookup_is_unavailable(
    client, course, teacher_auth_headers
):
    base = f"/courses/{course['id']}/occupation-reference"
    assert client.get(base + "/releases", headers=teacher_auth_headers).json() == {
        "items": []
    }
    assert (
        client.get(
            base + "/occupations",
            params={"release": "31.0", "q": "data"},
            headers=teacher_auth_headers,
        ).status_code
        == 503
    )
    assert (
        client.get(
            f"/courses/{course['id']}/market-demand/sources",
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )


def test_confirmation_persists_explicit_catalog_values_and_revision(
    db_session, client, course, teacher_auth_headers, parsed_release
):
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    import_catalog(db_session, parsed_release)
    repo = MarketReviewRepository(db_session)
    run = repo.create_run(
        course["id"],
        course["teacher_id"],
        {"evidence_sources": ["onet"], "sources": [], "onet_release": "31.0"},
    )
    activate_run(db_session, run)
    db_session.commit()
    body = {
        "run_id": str(run.id),
        "expected_candidate_revision": 0,
        "release": "31.0",
        "soc_codes": ["15-2051.00"],
    }
    path = f"/courses/{course['id']}/market-demand/occupations"
    response = client.post(path, json=body, headers=teacher_auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["candidate_revision"] == 1
    assert response.json()["run_id"] == str(run.id)
    assert response.json()["candidates"] == []
    db_session.expire_all()
    restored = repo.get_run(run.id, course["id"], course["teacher_id"])
    assert restored.config["selected_onet_occupations"] == [
        {
            "soc_code": "15-2051.00",
            "title": "Data Scientists",
            "description": "Analyze data.",
        }
    ]
    assert restored.config["onet_selection_confirmed"] is True
    state = client.get(
        f"/courses/{course['id']}/market-demand/state", headers=teacher_auth_headers
    )
    assert state.status_code == 200
    assert state.json()["selected_onet_occupations"] == ["15-2051.00"]
    assert state.json()["onet_selection_confirmed"] is True
    assert client.post(path, json=body, headers=teacher_auth_headers).status_code == 409


@pytest.mark.parametrize(
    "codes,release,status",
    [
        ([], "31.0", 422),
        (["15-2051.00"] * 2, "31.0", 422),
        (["99-9999.00"], "31.0", 422),
        (["15-2051.00"], "32.0", 422),
        (["15-2051.00"] * 6, "31.0", 422),
    ],
)
def test_confirmation_rejects_invalid_occupations(
    db_session,
    client,
    course,
    teacher_auth_headers,
    parsed_release,
    codes,
    release,
    status,
):
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    import_catalog(db_session, parsed_release)
    run = MarketReviewRepository(db_session).create_run(
        course["id"],
        course["teacher_id"],
        {"evidence_sources": ["onet"], "onet_release": "31.0"},
    )
    activate_run(db_session, run)
    db_session.commit()
    body = {
        "run_id": str(run.id),
        "expected_candidate_revision": 0,
        "release": release,
        "soc_codes": codes,
    }
    assert (
        client.post(
            f"/courses/{course['id']}/market-demand/occupations",
            json=body,
            headers=teacher_auth_headers,
        ).status_code
        == status
    )
    db_session.refresh(run)
    assert run.candidate_revision == 0


def test_confirmation_rejects_foreign_run_jobs_only_and_produced_results(
    db_session, client, course, teacher_auth_headers, parsed_release
):
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    import_catalog(db_session, parsed_release)
    repo = MarketReviewRepository(db_session)
    path = f"/courses/{course['id']}/market-demand/occupations"
    for config, produced in [
        ({"evidence_sources": ["jobs"]}, False),
        ({"evidence_sources": ["onet"], "onet_release": "31.0"}, True),
    ]:
        run = repo.create_run(course["id"], course["teacher_id"], config)
        if produced:
            run.source_outcomes = {
                "onet": {
                    "status": "success",
                    "received_count": 4,
                    "usable_count": 4,
                    "warnings": [],
                }
            }
        activate_run(db_session, run)
        db_session.commit()
        response = client.post(
            path,
            json={
                "run_id": str(run.id),
                "expected_candidate_revision": 0,
                "release": "31.0",
                "soc_codes": ["15-2051.00"],
            },
            headers=teacher_auth_headers,
        )
        assert response.status_code in (409, 422)
    response = client.post(
        path,
        json={
            "run_id": str(uuid4()),
            "expected_candidate_revision": 0,
            "release": "31.0",
            "soc_codes": ["15-2051.00"],
        },
        headers=teacher_auth_headers,
    )
    assert response.status_code == 409


def test_confirmation_respects_cross_process_thread_lease(
    db_session, client, course, teacher_auth_headers, parsed_release
):
    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.repository import (
        MarketReviewRepository,
        ThreadStateRepository,
    )

    import_catalog(db_session, parsed_release)
    run = MarketReviewRepository(db_session).create_run(
        course["id"],
        course["teacher_id"],
        {"evidence_sources": ["onet"], "onet_release": "31.0"},
    )
    activate_run(db_session, run)
    db_session.commit()
    thread_id = f"mda-{course['teacher_id']}-course-{course['id']}"
    locks = ThreadStateRepository(SessionLocal)
    connection = locks.acquire(thread_id)
    assert connection is not None
    try:
        response = client.post(
            f"/courses/{course['id']}/market-demand/occupations",
            json={
                "run_id": str(run.id),
                "expected_candidate_revision": 0,
                "release": "31.0",
                "soc_codes": ["15-2051.00"],
            },
            headers=teacher_auth_headers,
        )
        assert response.status_code == 409
        db_session.refresh(run)
        assert run.candidate_revision == 0
    finally:
        locks.release(connection, thread_id)


def test_failed_thread_write_rolls_back_confirmation_and_allows_retry(
    db_session, client, course, teacher_auth_headers, parsed_release
):
    from copy import deepcopy

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.models import MDAThreadState
    from app.modules.marketdemandanalyst.repository import (
        MarketReviewRepository,
        ThreadStateRepository,
    )

    import_catalog(db_session, parsed_release)
    initial_config = {
        "evidence_sources": ["onet"],
        "sources": [],
        "onet_release": "31.0",
    }
    run = MarketReviewRepository(db_session).create_run(
        course["id"], course["teacher_id"], initial_config
    )
    run_id = run.id
    thread_id = f"mda-{course['teacher_id']}-course-{course['id']}"
    initial_snapshot = {
        **initial_config,
        "run_id": str(run_id),
        "candidate_revision": 0,
        "selected_onet_occupations": ["15-1252.00"],
        "onet_selection_confirmed": False,
    }
    db_session.add(
        MDAThreadState(thread_id=thread_id, state_json=deepcopy(initial_snapshot))
    )
    db_session.commit()
    db_session.execute(
        text(
            "ALTER TABLE mda_thread_state ADD CONSTRAINT test_reject_onet_confirmation "
            "CHECK ((state_json ->> 'onet_selection_confirmed') IS DISTINCT FROM 'true')"
        )
    )
    db_session.commit()
    path = f"/courses/{course['id']}/market-demand/occupations"
    body = {
        "run_id": str(run_id),
        "expected_candidate_revision": 0,
        "release": "31.0",
        "soc_codes": ["15-2051.00"],
    }
    try:
        with pytest.raises(IntegrityError):
            client.post(path, json=body, headers=teacher_auth_headers)
        # Fresh real SQL reads prove the failed second write did not commit either half.
        with Session(db_session.get_bind()) as session:
            restored = MarketReviewRepository(session).get_run(
                run_id, course["id"], course["teacher_id"]
            )
            assert restored.candidate_revision == 0
            assert restored.config == initial_config
            assert session.get(MDAThreadState, thread_id).state_json == initial_snapshot
        reloaded = client.get(
            f"/courses/{course['id']}/market-demand/state", headers=teacher_auth_headers
        )
        assert reloaded.json()["candidate_revision"] == 0
        assert reloaded.json()["selected_onet_occupations"] == ["15-1252.00"]
        assert reloaded.json()["onet_selection_confirmed"] is False
        locks = ThreadStateRepository(SessionLocal)
        connection = locks.acquire(thread_id)
        assert connection is not None
        locks.release(connection, thread_id)
    finally:
        db_session.rollback()
        db_session.execute(
            text(
                "ALTER TABLE mda_thread_state DROP CONSTRAINT test_reject_onet_confirmation"
            )
        )
        db_session.commit()
    response = client.post(path, json=body, headers=teacher_auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["candidate_revision"] == 1
    reloaded = client.get(
        f"/courses/{course['id']}/market-demand/state", headers=teacher_auth_headers
    )
    assert reloaded.json()["candidate_revision"] == 1
    assert reloaded.json()["selected_onet_occupations"] == ["15-2051.00"]
    assert reloaded.json()["onet_selection_confirmed"] is True
    with Session(db_session.get_bind()) as session:
        restored = MarketReviewRepository(session).get_run(
            run_id, course["id"], course["teacher_id"]
        )
        assert restored.candidate_revision == 1
        assert restored.config["onet_selection_confirmed"] is True
        assert (
            restored.config["selected_onet_occupations"][0]["soc_code"] == "15-2051.00"
        )


@pytest.mark.parametrize("source", ["onet", "headhunter"])
def test_completed_empty_collection_freezes_occupations(
    db_session, client, course, teacher_auth_headers, parsed_release, source
):
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    import_catalog(db_session, parsed_release)
    initial_config = {
        "evidence_sources": ["jobs", "onet"],
        "sources": ["headhunter"],
        "onet_release": "31.0",
    }
    run = MarketReviewRepository(db_session).create_run(
        course["id"], course["teacher_id"], initial_config
    )
    run.source_outcomes = {
        source: {
            "status": "empty",
            "received_count": 0,
            "usable_count": 0,
            "warnings": [],
        }
    }
    activate_run(db_session, run)
    db_session.commit()
    response = client.post(
        f"/courses/{course['id']}/market-demand/occupations",
        json={
            "run_id": str(run.id),
            "expected_candidate_revision": 0,
            "release": "31.0",
            "soc_codes": ["15-2051.00"],
        },
        headers=teacher_auth_headers,
    )
    assert response.status_code == 409
    db_session.refresh(run)
    assert run.candidate_revision == 0
    assert run.config == initial_config
    assert run.source_outcomes[source]["status"] == "empty"


def test_late_confirmation_cannot_reactivate_cleared_chat(
    db_session, client, course, teacher_auth_headers, parsed_release, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import routes
    from app.modules.marketdemandanalyst.models import MDAThreadState
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    import_catalog(db_session, parsed_release)
    initial_config = {
        "evidence_sources": ["onet"],
        "sources": [],
        "onet_release": "31.0",
    }
    run = MarketReviewRepository(db_session).create_run(
        course["id"], course["teacher_id"], initial_config
    )
    activate_run(db_session, run)
    run_id = run.id
    db_session.commit()
    monkeypatch.setattr(
        routes,
        "get_graph",
        AsyncMock(return_value=(SimpleNamespace(checkpointer=None), None)),
    )
    cleared = client.delete(
        f"/courses/{course['id']}/market-demand/history", headers=teacher_auth_headers
    )
    assert cleared.status_code == 200
    response = client.post(
        f"/courses/{course['id']}/market-demand/occupations",
        json={
            "run_id": str(run_id),
            "expected_candidate_revision": 0,
            "release": "31.0",
            "soc_codes": ["15-2051.00"],
        },
        headers=teacher_auth_headers,
    )
    assert response.status_code == 409
    with Session(db_session.get_bind()) as session:
        restored = MarketReviewRepository(session).get_run(
            run_id, course["id"], course["teacher_id"]
        )
        assert restored.candidate_revision == 0
        assert restored.config == initial_config
        assert (
            session.get(
                MDAThreadState, f"mda-{course['teacher_id']}-course-{course['id']}"
            )
            is None
        )
    state = client.get(
        f"/courses/{course['id']}/market-demand/state", headers=teacher_auth_headers
    )
    assert state.json()["run_id"] is None
