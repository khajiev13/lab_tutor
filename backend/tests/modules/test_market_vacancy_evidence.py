"""Real PostgreSQL full snapshot, deduplication, provenance and purge tests."""

import pytest


def setup_run(db_session, client, teacher_auth_headers):
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    course = client.post(
        "/courses", json={"title": "Evidence course"}, headers=teacher_auth_headers
    ).json()
    repo = MarketReviewRepository(db_session)
    run = repo.create_run(
        course["id"], course["teacher_id"], {"sources": ["headhunter", "linkedin"]}
    )
    return repo, run, course


def vacancy(provider="headhunter", native_id="10", query="Python", **kwargs):
    from app.modules.marketdemandanalyst.schemas import ProviderVacancy

    return ProviderVacancy(
        provider=provider,
        native_id=native_id,
        title="Same",
        company="Same",
        original_url=f"https://{'hh.uz/vacancy' if provider == 'headhunter' else 'www.linkedin.com/jobs/view'}/{native_id}",
        original_description="<p>Русский 中文</p>" + "x" * 9000,
        description_text="Русский 中文" + "x" * 9000,
        raw_payload={"id": native_id, "extra": {"all": [1, 2, 3]}},
        query_membership=[query],
        **kwargs,
    )


def test_complete_snapshot_repeated_observations_union_queries_and_new_ids_survive(
    db_session, client, teacher_auth_headers
):
    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    first = repo.upsert_vacancy_snapshot(run.id, vacancy())
    repeated = repo.upsert_vacancy_snapshot(run.id, vacancy(query="Data"))
    other = repo.upsert_vacancy_snapshot(run.id, vacancy(native_id="11"))
    assert first.id == repeated.id and first.id != other.id
    db_session.commit()
    db_session.expire_all()
    stored = repo.get_vacancy_snapshot(first.id, course["id"], course["teacher_id"])
    assert len(stored.original_description) > 9000
    assert stored.raw_payload == {"id": "10", "extra": {"all": [1, 2, 3]}}
    assert stored.query_membership == ["Python", "Data"]
    assert (
        repo.get_vacancy_snapshot(first.id, course["id"] + 1, course["teacher_id"])
        is None
    )
    assert (
        repo.get_vacancy_snapshot(first.id, course["id"], course["teacher_id"] + 1)
        is None
    )


def test_syndicated_demand_identity_preserves_separate_source_links(
    db_session, client, teacher_auth_headers
):
    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    hh = repo.upsert_vacancy_snapshot(
        run.id, vacancy(demand_identity="verified:syndicated-10")
    )
    linkedin = repo.upsert_vacancy_snapshot(
        run.id, vacancy(provider="linkedin", demand_identity="verified:syndicated-10")
    )
    assert hh.id != linkedin.id and hh.demand_identity == linkedin.demand_identity
    assert hh.original_url != linkedin.original_url


def test_archival_purge_keeps_identity_but_removes_content_and_cannot_rehydrate(
    db_session, client, teacher_auth_headers
):
    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    stored = repo.upsert_vacancy_snapshot(run.id, vacancy())
    repo.purge_vacancy_content(stored.id, reason="provider_archival_removal")
    db_session.commit()
    stored = repo.upsert_vacancy_snapshot(run.id, vacancy(query="Data"))
    assert (
        stored.raw_payload == {}
        and stored.original_description is None
        and stored.description_text is None
    )
    assert stored.purged_at is not None and stored.native_id == "10"
    response = client.get(
        f"/courses/{course['id']}/market-demand/skill-review/postings/{stored.id}",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200 and response.json()["purged_at"]
    assert response.json()["raw_payload"] == {}


def test_snapshot_rejects_nonselected_provider_and_scrubs_secret_fields(
    db_session, client, teacher_auth_headers
):
    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    with pytest.raises(ValueError):
        repo.upsert_vacancy_snapshot(run.id, vacancy(provider="indeed"))
    record = vacancy()
    record.raw_payload["authorization"] = "Bearer synthetic-secret"
    record.raw_payload["extra"]["access_token"] = "synthetic-secret"
    stored = repo.upsert_vacancy_snapshot(run.id, record)
    assert "synthetic-secret" not in str(stored.raw_payload)


def test_purge_reaches_syndicated_same_provider_copies_and_invalidates_review(
    db_session, client, teacher_auth_headers
):
    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    first = repo.upsert_vacancy_snapshot(run.id, vacancy())
    other_run = repo.create_run(
        course["id"], course["teacher_id"], {"sources": ["headhunter"]}
    )
    second = repo.upsert_vacancy_snapshot(other_run.id, vacancy())
    run.integration_review = {"review_digest": "old"}
    other_run.integration_review = {"review_digest": "old"}
    db_session.flush()
    repo.purge_vacancy_content(first.id, reason="provider_archival_removal")
    db_session.expire_all()
    assert repo.get_vacancy_snapshot(
        second.id, course["id"], course["teacher_id"]
    ).purged_at
    assert (
        repo.get_run(run.id, course["id"], course["teacher_id"]).integration_review
        is None
    )
    assert (
        repo.get_run(
            other_run.id, course["id"], course["teacher_id"]
        ).integration_review
        is None
    )
    changed = vacancy()
    changed.raw_payload["new"] = "do not restore"
    new_snapshot = repo.upsert_vacancy_snapshot(other_run.id, changed)
    assert new_snapshot.raw_payload == {} and new_snapshot.purged_at


def test_owned_full_detail_endpoint_and_all_source_urls_survive_reload(
    db_session, client, teacher_auth_headers, student_auth_headers
):
    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    record = vacancy()
    record.source_urls = [record.original_url, "https://company.example/careers/10"]
    stored = repo.upsert_vacancy_snapshot(run.id, record)
    db_session.commit()
    db_session.expire_all()
    restored = repo.get_vacancy_snapshot(stored.id, course["id"], course["teacher_id"])
    assert restored.source_urls == [
        "https://hh.uz/vacancy/10",
        "https://company.example/careers/10",
    ]
    url = f"/courses/{course['id']}/market-demand/skill-review/postings/{stored.id}"
    response = client.get(url, headers=teacher_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert (
        len(body["description_text"]) > 9000
        and len(body["original_description"]) > 9000
    )
    assert body["raw_payload"] == {"id": "10", "extra": {"all": [1, 2, 3]}}
    assert set(body) == {
        "snapshot_id",
        "provider",
        "native_id",
        "original_url",
        "title",
        "company",
        "description_text",
        "original_description",
        "raw_payload",
        "retrieved_at",
        "status",
        "purged_at",
    }
    other_course = client.post(
        "/courses",
        json={"title": "Other evidence course"},
        headers=teacher_auth_headers,
    ).json()
    assert (
        client.get(
            f"/courses/{other_course['id']}/market-demand/skill-review/postings/{stored.id}",
            headers=teacher_auth_headers,
        ).status_code
        == 404
    )
    assert client.get(url, headers=student_auth_headers).status_code == 403
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("mutation", ["upsert", "purge"])
def test_stale_preloaded_run_cannot_keep_review_after_evidence_mutation(
    db_session, client, teacher_auth_headers, mutation
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.models import MarketAnalysisRun
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    stored = repo.upsert_vacancy_snapshot(run.id, vacancy())
    run_id, snapshot_id = run.id, stored.id
    db_session.commit()
    bind = db_session.get_bind()
    with Session(bind=bind) as stale, Session(bind=bind) as concurrent:
        stale_repo = MarketReviewRepository(stale)
        preloaded = stale_repo.get_run(run_id, course["id"], course["teacher_id"])
        assert preloaded.integration_review is None
        current = concurrent.get(MarketAnalysisRun, run_id)
        current.integration_review = {"review_digest": "committed-after-preload"}
        concurrent.commit()
        if mutation == "upsert":
            stale_repo.upsert_vacancy_snapshot(run_id, vacancy(native_id="11"))
        else:
            stale_repo.purge_vacancy_content(
                snapshot_id, reason="provider_archival_removal"
            )
        stale.commit()
    with Session(bind=bind) as fresh:
        assert fresh.get(MarketAnalysisRun, run_id).integration_review is None


def test_preloaded_snapshot_unions_concurrently_committed_queries_and_source_urls(
    db_session, client, teacher_auth_headers
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    snapshot = repo.upsert_vacancy_snapshot(run.id, vacancy())
    run_id, snapshot_id = run.id, snapshot.id
    db_session.commit()
    bind = db_session.get_bind()
    with Session(bind=bind) as stale, Session(bind=bind) as concurrent:
        stale_repo = MarketReviewRepository(stale)
        preloaded = stale_repo.get_vacancy_snapshot(
            snapshot_id, course["id"], course["teacher_id"]
        )
        assert preloaded.query_membership == ["Python"]
        other = vacancy(query="Data")
        other.source_urls = [other.original_url, "https://company.example/careers/10"]
        MarketReviewRepository(concurrent).upsert_vacancy_snapshot(run_id, other)
        concurrent.commit()
        latest = vacancy(query="Analyst")
        latest.source_urls = [latest.original_url, "https://mirror.example/postings/10"]
        stale_repo.upsert_vacancy_snapshot(run_id, latest)
        stale.commit()
    with Session(bind=bind) as fresh:
        stored = MarketReviewRepository(fresh).get_vacancy_snapshot(
            snapshot_id, course["id"], course["teacher_id"]
        )
        assert stored.query_membership == ["Python", "Data", "Analyst"]
        assert stored.source_urls == [
            "https://hh.uz/vacancy/10",
            "https://company.example/careers/10",
            "https://mirror.example/postings/10",
        ]


@pytest.mark.parametrize("operation", ["upsert", "read"])
def test_preloaded_snapshot_never_returns_content_after_concurrent_purge(
    db_session, client, teacher_auth_headers, operation
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    snapshot = repo.upsert_vacancy_snapshot(run.id, vacancy())
    run_id, snapshot_id = run.id, snapshot.id
    db_session.commit()
    bind = db_session.get_bind()
    with Session(bind=bind) as stale, Session(bind=bind) as concurrent:
        stale_repo = MarketReviewRepository(stale)
        preloaded = stale_repo.get_vacancy_snapshot(
            snapshot_id, course["id"], course["teacher_id"]
        )
        assert preloaded.raw_payload and preloaded.description_text
        MarketReviewRepository(concurrent).purge_vacancy_content(
            snapshot_id, reason="provider_archival_removal"
        )
        concurrent.commit()
        if operation == "upsert":
            returned = stale_repo.upsert_vacancy_snapshot(run_id, vacancy(query="Data"))
        else:
            returned = stale_repo.get_vacancy_snapshot(
                snapshot_id, course["id"], course["teacher_id"]
            )
        # Assert before commit's default expiration can hide an unsafe return.
        assert returned.raw_payload == {}
        assert (
            returned.original_description is None and returned.description_text is None
        )
        assert returned.status == "purged" and returned.purged_at is not None
        stale.commit()
    with Session(bind=bind) as fresh:
        stored = MarketReviewRepository(fresh).get_vacancy_snapshot(
            snapshot_id, course["id"], course["teacher_id"]
        )
        assert stored.raw_payload == {}
        assert stored.query_membership == (
            ["Python", "Data"] if operation == "upsert" else ["Python"]
        )


def test_purge_refreshes_preloaded_snapshot_provenance(
    db_session, client, teacher_auth_headers
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    snapshot = repo.upsert_vacancy_snapshot(run.id, vacancy())
    run_id, snapshot_id = run.id, snapshot.id
    db_session.commit()
    bind = db_session.get_bind()
    with Session(bind=bind) as stale, Session(bind=bind) as concurrent:
        stale_repo = MarketReviewRepository(stale)
        preloaded = stale_repo.get_vacancy_snapshot(
            snapshot_id, course["id"], course["teacher_id"]
        )
        assert preloaded.query_membership == ["Python"]
        current = vacancy(query="Data")
        current.source_urls = [
            current.original_url,
            "https://company.example/careers/10",
        ]
        MarketReviewRepository(concurrent).upsert_vacancy_snapshot(run_id, current)
        concurrent.commit()
        stale_repo.purge_vacancy_content(
            snapshot_id, reason="provider_archival_removal"
        )
        returned = stale_repo.get_vacancy_snapshot(
            snapshot_id, course["id"], course["teacher_id"]
        )
        assert returned.query_membership == ["Python", "Data"]
        assert returned.source_urls == [
            "https://hh.uz/vacancy/10",
            "https://company.example/careers/10",
        ]
        assert returned.raw_payload == {} and returned.purged_at
        stale.commit()


def test_transaction_wide_batch_upsert_and_purge_have_no_lock_cycle(
    db_session, client, teacher_auth_headers
):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    existing = repo.upsert_vacancy_snapshot(run.id, vacancy(native_id="20"))
    run_id, existing_id = run.id, existing.id
    db_session.commit()
    bind = db_session.get_bind()
    first_stored = Event()
    purge_started = Event()
    store_second = Event()
    pids = {}

    def store_batch():
        with Session(bind=bind) as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            session.execute(text("SET LOCAL statement_timeout = '8s'"))
            pids["batch"] = session.scalar(text("SELECT pg_backend_pid()"))
            worker_repo = MarketReviewRepository(session)
            first = worker_repo.upsert_vacancy_snapshot(run_id, vacancy(native_id="10"))
            first_id = first.id
            first_stored.set()
            if not store_second.wait(10):
                raise TimeoutError("Batch continuation was not released")
            second = worker_repo.upsert_vacancy_snapshot(
                run_id, vacancy(native_id="20", query="Data")
            )
            second_id = second.id
            session.commit()
            return first_id, second_id

    def purge_existing():
        with Session(bind=bind) as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            session.execute(text("SET LOCAL statement_timeout = '8s'"))
            pids["purge"] = session.scalar(text("SELECT pg_backend_pid()"))
            purge_started.set()
            count = MarketReviewRepository(session).purge_vacancy_content(
                existing_id, reason="provider_archival_removal"
            )
            session.commit()
            return count

    with ThreadPoolExecutor(max_workers=2) as pool:
        batch_future = pool.submit(store_batch)
        purge_future = None
        try:
            assert first_stored.wait(5), (
                "First transaction never stored its first vacancy"
            )
            purge_future = pool.submit(purge_existing)
            assert purge_started.wait(5), "Purge transaction never started"
            # Inspect actual PostgreSQL blocking, never infer it from elapsed time.
            blocked = False
            deadline = time.monotonic() + 3
            with Session(bind=bind) as observer:
                while time.monotonic() < deadline:
                    blockers = observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": pids["purge"]}
                    )
                    if pids["batch"] in blockers:
                        blocked = True
                        break
                    if purge_future.done():
                        break
                    time.sleep(0.01)
            assert blocked, "Purge did not reach the real transaction lock boundary"
            store_second.set()
            first_id, second_id = batch_future.result(timeout=12)
            assert purge_future.result(timeout=12) >= 1
            assert second_id == existing_id
        finally:
            # Events and database-side timeouts bound cleanup even on RED.
            store_second.set()
    with Session(bind=bind) as fresh:
        assert fresh.get(MarketVacancySnapshot, first_id).raw_payload
        purged = fresh.get(MarketVacancySnapshot, existing_id)
        assert purged.raw_payload == {} and purged.purged_at
        assert purged.query_membership == ["Python", "Data"]


def test_canonical_url_tombstone_blocks_equivalent_url_only_refetch(
    db_session, client, teacher_auth_headers
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.schemas import ProviderVacancy

    repo, run, course = setup_run(db_session, client, teacher_auth_headers)
    record = ProviderVacancy(
        provider="headhunter",
        title="Python",
        original_url="HTTPS://HH.UZ:443/vacancy/10?b=2&a=1#one",
        original_description="Python " * 1000,
        description_text="Python " * 1000,
        raw_payload={"description": "Python " * 1000},
        query_membership=["Python"],
    )
    initial = repo.upsert_vacancy_snapshot(run.id, record)
    original_id, run_id = initial.id, run.id
    repo.purge_vacancy_content(original_id, reason="provider_archival_removal")
    db_session.commit()
    alias = record.model_copy(
        update={
            "original_url": "https://hh.uz/vacancy/10?b=2&a=1#one",
            "query_membership": ["Data"],
        }
    )
    refetched = repo.upsert_vacancy_snapshot(run_id, alias)
    refetched_id = refetched.id
    assert refetched.raw_payload == {} and refetched.description_text is None
    assert refetched.purged_at and refetched.status == "purged"
    db_session.commit()
    with Session(bind=db_session.get_bind()) as fresh:
        fresh_repo = MarketReviewRepository(fresh)
        first = fresh_repo.get_vacancy_snapshot(
            original_id, course["id"], course["teacher_id"]
        )
        second = fresh_repo.get_vacancy_snapshot(
            refetched_id, course["id"], course["teacher_id"]
        )
        assert first.demand_identity == second.demand_identity
        assert first.original_url == "HTTPS://HH.UZ:443/vacancy/10?b=2&a=1#one"
        assert second.original_url == "https://hh.uz/vacancy/10?b=2&a=1#one"
        assert first.raw_payload == second.raw_payload == {}
