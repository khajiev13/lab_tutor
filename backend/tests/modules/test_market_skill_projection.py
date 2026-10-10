"""Real SQL + explicit disposable Neo4j target/projector integration."""

import pytest
from sqlalchemy import select

from tests.market_skill_fixtures import prepare, seed_review

pytest_plugins = ["tests.fixtures.market_skill_graph"]


def graph_repo(driver):
    from app.modules.marketdemandanalyst.neo4j_repository import (
        MarketSkillGraphRepository,
    )

    return MarketSkillGraphRepository(driver, database="neo4j")


@pytest.mark.parametrize("context", ["missing", "cleared", "stale"])
def test_insert_without_current_durable_context_cannot_use_legacy_writer(
    db_session, client, teacher_auth_headers, graph_driver, monkeypatch, context
):
    from uuid import uuid4

    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, _, _, _, _ = seed_review(db_session, client, teacher_auth_headers)
    seed_graph(graph_driver, course["id"])
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    monkeypatch.setattr(tools, "_get_neo4j_driver", lambda **kwargs: graph_driver)
    state = {
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        "skill_concepts": {
            "Unapproved bypass": {
                "chapter_title": "Programming",
                "new_concepts": [],
                "existing_concepts": [],
            }
        },
    }
    if context != "missing":
        state["run_id"] = None if context == "cleared" else str(uuid4())
    with bind_tool_store(state):
        result = tools.insert_market_skills_to_neo4j.invoke({})
    with graph_driver.session(database="neo4j") as session:
        assert (
            session.run(
                "MATCH (s:MARKET_SKILL {name: 'Unapproved bypass'}) RETURN count(s) AS n"
            ).single()["n"]
            == 0
        ), result
        assert (
            session.run(
                "MATCH (b:SKILL_EVIDENCE_BINDING) RETURN count(b) AS n"
            ).single()["n"]
            == 0
        )


@pytest.mark.parametrize("surviving_run", [False, True])
def test_extracted_quote_purge_redacts_sql_and_graph_with_retryable_intent(
    db_session, client, teacher_auth_headers, graph_driver, surviving_run
):
    import json
    from copy import deepcopy

    from app.modules.marketdemandanalyst.models import (
        CourseSkillEvidence,
        CourseSkillReference,
        MarketSkillApproval,
        MarketVacancySnapshot,
        MDAThreadState,
    )
    from app.modules.marketdemandanalyst.projection_service import (
        SkillEvidenceProjector,
    )
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    seed_graph(graph_driver, course["id"])
    quote = "Python is required; remove this private source quotation."
    ref = candidates[0]["evidence_references"][0]
    snapshot = db_session.get(MarketVacancySnapshot, ref["snapshot_id"])
    snapshot.description_text = quote
    snapshot.original_description = quote
    snapshot.skill_tags = []
    ref.update(
        evidence_kind="extracted_text",
        excerpt=quote,
        excerpt_start=0,
        excerpt_end=len(quote),
    )
    run.candidate_manifest = {
        **deepcopy(run.candidate_manifest),
        "candidates": candidates,
        "candidate_history": deepcopy(candidates),
    }
    thread = db_session.get(
        MDAThreadState, service.thread_id(course["id"], course["teacher_id"])
    )
    thread.state_json = {
        "run_id": str(run.id),
        "candidate_manifest": deepcopy(run.candidate_manifest),
        "selected_jobs": [{"snapshot_id": str(snapshot.id), "description": quote}],
    }
    db_session.commit()
    review = prepare(
        service,
        course,
        revision,
        candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{course['id']}"],
    )
    approve_sql(service, course, run, review, candidates)
    projector = SkillEvidenceProjector(
        MarketReviewRepository(db_session), graph_repo(graph_driver)
    )
    assert projector.project(course["id"], 1, run_id=run.id) == "projected"
    approval = db_session.scalar(select(MarketSkillApproval))
    recorded_digest, approval_id = approval.review_digest, approval.id
    evidence = db_session.scalar(select(CourseSkillEvidence))
    binding_id, reference_id = evidence.id, evidence.skill_reference_id
    stale_state = {
        "run_id": str(run.id),
        "selected_jobs": [{"snapshot_id": str(snapshot.id), "description": quote}],
        "candidate_manifest": deepcopy(run.candidate_manifest),
    }
    second = None
    if surviving_run:
        _, second, other_candidates, other_service, other_revision = seed_review(
            db_session, client, teacher_auth_headers, course=course
        )
        other_review = prepare(
            other_service,
            course,
            other_revision,
            other_candidates,
            graph=graph_repo(graph_driver),
            chapter_ids=[f"chapter-{course['id']}"],
        )
        approve_sql(other_service, course, second, other_review, other_candidates)
        assert projector.project(course["id"], 1, run_id=second.id) == "projected"
    repo = MarketReviewRepository(db_session)
    repo.purge_vacancy_content(snapshot.id, reason="Provider removal")
    db_session.commit()
    db_session.expire_all()
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.repository import ThreadStateRepository

    ThreadStateRepository(lambda: Session(bind=db_session.get_bind())).save(
        thread.thread_id, stale_state
    )
    db_session.expire_all()
    payloads = [
        db_session.get(CourseSkillEvidence, binding_id).provenance,
        db_session.get(MarketSkillApproval, approval_id).items,
        db_session.get(CourseSkillReference, reference_id).display_data,
        db_session.get(type(run), run.id).candidate_manifest,
        db_session.get(MDAThreadState, thread.thread_id).state_json,
    ]
    assert all(quote not in json.dumps(payload) for payload in payloads)
    assert (
        db_session.get(MarketSkillApproval, approval_id).review_digest
        == recorded_digest
    )
    assert (
        db_session.get(CourseSkillReference, reference_id).available_for_new_selection
        is surviving_run
    )
    assert SkillEvidenceProjector(repo, None).redact(course["id"]) == "pending"
    from app.modules.marketdemandanalyst.models import MarketEvidenceRedaction

    for job in repo.pending_redactions(course["id"]):
        tombstone = repo.vacancy_snapshots_by_ids([str(job.snapshot_id)])[
            str(job.snapshot_id)
        ]
        assert tombstone.purged_at and job.evidence_payload.get("content_removed")
        expected_ids = [row["reference_id"] for row in job.reference_states]
        stored_refs, _, _ = repo.active_projection_items(course["id"], expected_ids)
        assert {str(row.id) for row in stored_refs} == set(expected_ids)
    status = projector.redact(course["id"])
    assert status == "projected", list(
        db_session.scalars(select(MarketEvidenceRedaction.projection_error))
    )
    assert projector.redact(course["id"]) == "projected"
    with graph_driver.session(database="neo4j") as session:
        row = session.run(
            "MATCH (e:CAREER_EVIDENCE {id: $id}) RETURN e.public_json AS payload",
            id=f"jobs:{snapshot.id}",
        ).single()
        assert row and quote not in row["payload"]
        assert json.loads(row["payload"])["content_removed"] is True
        row = session.run(
            "MATCH (b:SKILL_EVIDENCE_BINDING {id: $id}) RETURN b.active AS active",
            id=str(binding_id),
        ).single()
        assert row and row["active"] is False
        if second is not None:
            assert (
                session.run(
                    "MATCH (b:SKILL_EVIDENCE_BINDING {run_id: $id}) RETURN b.active AS active",
                    id=str(second.id),
                ).single()["active"]
                is True
            )
            assert projector.project(course["id"], 1, run_id=second.id) == "projected"


def test_approved_action_proof_survives_current_registry_replacement(
    db_session, client, teacher_auth_headers, graph_driver
):
    from copy import deepcopy

    from app.modules.marketdemandanalyst.models import (
        MarketSkillApproval,
        MarketVacancySnapshot,
    )
    from app.modules.marketdemandanalyst.projection_service import (
        SkillEvidenceProjector,
    )
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.service import MarketSourceService

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, labels=("Explain technical results",)
    )
    seed_graph(graph_driver, course["id"])
    quote = "You must explain results to colleagues."
    candidate = candidates[0]
    ref = candidate["evidence_references"][0]
    snapshot = db_session.get(MarketVacancySnapshot, ref["snapshot_id"])
    snapshot.description_text = quote
    snapshot.original_description = quote
    snapshot.skill_tags = []
    ref.update(
        original_phrase="explain results",
        evidence_kind="extracted_text",
        excerpt=quote,
        excerpt_start=0,
        excerpt_end=len(quote),
    )
    db_session.flush()
    repo = MarketReviewRepository(db_session)
    MarketSourceService._validated_observation(
        repo,
        run,
        {
            "name": candidate["display_name"],
            "identity_key": candidate["identity_key"],
            "evidence_references": [ref],
        },
        trusted_extraction=True,
    )
    run.candidate_manifest = {
        **deepcopy(run.candidate_manifest),
        "candidates": candidates,
    }
    db_session.commit()
    review = prepare(
        service,
        course,
        revision,
        candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{course['id']}"],
    )
    approve_sql(service, course, run, review, candidates)
    approval = db_session.scalar(select(MarketSkillApproval))
    assert approval.items[0]["validated_observations"]
    run.candidate_manifest = {
        **deepcopy(run.candidate_manifest),
        "validated_observations": [],
    }
    db_session.commit()
    projector = SkillEvidenceProjector(repo, graph_repo(graph_driver))
    assert projector.project(course["id"], 1, run_id=run.id) == "projected"
    assert projector.project(course["id"], 1, run_id=run.id) == "projected"


def test_withdraw_one_of_two_runs_preserves_surviving_graph_binding_on_retry(
    db_session, client, teacher_auth_headers, graph_driver
):
    from app.modules.marketdemandanalyst.projection_service import (
        SkillEvidenceProjector,
    )
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.schemas import IntegrationApproval

    course, first, first_candidates, service, first_revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    seed_graph(graph_driver, course["id"])
    first_review = prepare(
        service,
        course,
        first_revision,
        first_candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{course['id']}"],
    )
    approve_sql(service, course, first, first_review, first_candidates)
    projector = SkillEvidenceProjector(
        MarketReviewRepository(db_session), graph_repo(graph_driver)
    )
    assert projector.project(course["id"], 1, run_id=first.id) == "projected"
    _, second, second_candidates, second_service, second_revision = seed_review(
        db_session, client, teacher_auth_headers, course=course
    )
    second_review = prepare(
        second_service,
        course,
        second_revision,
        second_candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{course['id']}"],
    )
    approve_sql(second_service, course, second, second_review, second_candidates)
    assert projector.project(course["id"], 1, run_id=second.id) == "projected"
    repo = MarketReviewRepository(db_session)
    repo.save_configuration_snapshot(
        service.thread_id(course["id"], course["teacher_id"]), {"run_id": str(first.id)}
    )
    repo.commit()
    withdrawal = service.prepare_withdrawal_review(
        course["id"], course["teacher_id"], first_revision
    )
    service.approve_integration(
        course["id"],
        course["teacher_id"],
        IntegrationApproval(
            **first_revision.model_dump(),
            review_digest=withdrawal.integration_review["review_digest"],
            approved_candidate_ids=[],
        ),
    )
    assert projector.project(course["id"], 2, run_id=first.id) == "projected"
    assert projector.project(course["id"], 2, run_id=first.id) == "projected"
    with graph_driver.session(database="neo4j") as session:
        rows = list(
            session.run(
                "MATCH (b:SKILL_EVIDENCE_BINDING) RETURN b.run_id AS run, b.active AS active"
            )
        )
        assert len(rows) == 2 and {row["run"]: row["active"] for row in rows} == {
            str(first.id): False,
            str(second.id): True,
        }
        assert (
            session.run(
                "MATCH (r:COURSE_SKILL_REFERENCE) RETURN count(r) AS n"
            ).single()["n"]
            == 1
        )
        assert (
            session.run("MATCH (s:CAREER_SKILL) RETURN count(s) AS n").single()["n"]
            == 1
        )


def seed_graph(driver, course_id, *, label="Python"):
    with driver.session(database="neo4j") as session:
        session.run(
            "MERGE (c:CLASS {id: $id}) MERGE (ch:COURSE_CHAPTER {id: $chapter}) SET ch.title='Programming' MERGE (c)-[:HAS_COURSE_CHAPTER]->(ch)",
            id=course_id,
            chapter=f"chapter-{course_id}",
        ).consume()
        session.run(
            "MERGE (s:BOOK_SKILL:SKILL {id: $skill}) SET s.name=$label MERGE (ch:COURSE_CHAPTER {id: $chapter}) MERGE (s)-[:MAPPED_TO]->(ch)",
            skill=f"book-{course_id}",
            chapter=f"chapter-{course_id}",
            label=label,
        ).consume()


def approve_sql(service, course, run, review, candidates):
    from app.modules.marketdemandanalyst.schemas import IntegrationApproval

    return service.approve_integration(
        course["id"],
        course["teacher_id"],
        IntegrationApproval(
            run_id=run.id,
            expected_candidate_revision=run.candidate_revision,
            expected_selection_revision=run.selection_revision,
            review_digest=review.integration_review["review_digest"],
            approved_candidate_ids=[c["candidate_id"] for c in candidates],
        ),
    )


def test_real_graph_projects_and_retries_without_duplicate_bindings(
    db_session, client, teacher_auth_headers, graph_driver
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    seed_graph(graph_driver, course["id"])
    review = prepare(
        service,
        course,
        revision,
        candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{course['id']}"],
    )
    approve_sql(service, course, run, review, candidates)
    from app.modules.marketdemandanalyst.projection_service import (
        SkillEvidenceProjector,
    )
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    projector = SkillEvidenceProjector(
        MarketReviewRepository(db_session), graph_repo(graph_driver)
    )
    assert projector.project(course["id"], 1, run_id=run.id) == "projected"
    assert projector.project(course["id"], 1, run_id=run.id) == "projected"
    with graph_driver.session(database="neo4j") as session:
        row = session.run(
            "MATCH (r:COURSE_SKILL_REFERENCE) RETURN count(r) AS refs, COLLECT {MATCH (b:SKILL_EVIDENCE_BINDING) RETURN b.id} AS bindings, COLLECT {MATCH (s:CAREER_SKILL) RETURN s.id} AS skills"
        ).single()
        assert (
            row["refs"] == 1 and len(row["bindings"]) == 1 and len(row["skills"]) == 1
        )
        assert (
            session.run(
                "MATCH (:CAREER_SKILL)-[:SOURCED_FROM]->(j:JOB_POSTING) RETURN j.url AS url"
            ).single()["url"]
            == candidates[0]["evidence_references"][0]["original_url"]
        )


def test_graph_resolver_rejects_foreign_target_and_preserves_book_identity(
    db_session, client, teacher_auth_headers, graph_driver
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    seed_graph(graph_driver, course["id"])
    seed_graph(graph_driver, course["id"] + 500)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        prepare(
            service,
            course,
            revision,
            candidates,
            graph=graph_repo(graph_driver),
            disposition="covered",
            source="book",
            origin="book",
            graph_target_id=f"book-{course['id'] + 500}",
            chapter_ids=[f"chapter-{course['id']}"],
        )
    assert exc.value.status_code == 422
    db_session.rollback()
    review = prepare(
        service,
        course,
        revision,
        candidates,
        graph=graph_repo(graph_driver),
        disposition="covered",
        source="book",
        origin="book",
        graph_target_id=f"book-{course['id']}",
        chapter_ids=[f"chapter-{course['id']}"],
    )
    approve_sql(service, course, run, review, candidates)
    from app.modules.marketdemandanalyst.projection_service import (
        SkillEvidenceProjector,
    )
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    assert (
        SkillEvidenceProjector(
            MarketReviewRepository(db_session), graph_repo(graph_driver)
        ).project(course["id"], 1, run_id=run.id)
        == "projected"
    )
    with graph_driver.session(database="neo4j") as session:
        row = session.run(
            "MATCH (:SKILL_EVIDENCE_BINDING)-[:FOR_SKILL]->(s:BOOK_SKILL) RETURN s.id AS id, COLLECT {MATCH (x:CAREER_SKILL) RETURN x.id} AS skills"
        ).single()
        assert row["id"] == f"book-{course['id']}" and row["skills"] == []


@pytest.mark.parametrize("mutation", ["posting", "relation_rationale", "affected_ids"])
def test_inconsistent_sql_binding_refused_before_graph_write(
    db_session, client, teacher_auth_headers, graph_driver, mutation
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    seed_graph(graph_driver, course["id"])
    review = prepare(
        service,
        course,
        revision,
        candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{course['id']}"],
    )
    approve_sql(service, course, run, review, candidates)
    from app.modules.marketdemandanalyst.models import (
        CourseSkillEvidence,
        MarketSkillApproval,
        MarketVacancySnapshot,
    )
    from app.modules.marketdemandanalyst.projection_service import (
        SkillEvidenceProjector,
    )
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    binding = db_session.scalar(select(CourseSkillEvidence))
    if mutation == "posting":
        snapshot = db_session.get(MarketVacancySnapshot, binding.vacancy_snapshot_id)
        snapshot.skill_tags = ["Java"]
    elif mutation == "relation_rationale":
        binding.mapping_relation = "unreviewed"
        binding.rationale = "Changed after teacher approval"
    else:
        from uuid import uuid4

        approval = db_session.scalar(select(MarketSkillApproval))
        approval.affected_reference_ids = [str(uuid4())]
    db_session.commit()
    assert (
        SkillEvidenceProjector(
            MarketReviewRepository(db_session), graph_repo(graph_driver)
        ).project(course["id"], 1, run_id=run.id)
        == "error"
    )
    with graph_driver.session(database="neo4j") as session:
        assert (
            session.run(
                "MATCH (b:SKILL_EVIDENCE_BINDING) RETURN count(b) AS n"
            ).single()["n"]
            == 0
        )


def test_same_label_in_separate_courses_keeps_distinct_sql_metrics(
    db_session, client, teacher_auth_headers, graph_driver
):
    from copy import deepcopy

    from app.modules.marketdemandanalyst.models import CourseSkillReference
    from app.modules.marketdemandanalyst.projection_service import (
        SkillEvidenceProjector,
    )
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    reference_ids = []
    for index in range(2):
        course, run, candidates, service, revision = seed_review(
            db_session, client, teacher_auth_headers, title=f"Metric course {index}"
        )
        if index:
            manifest = deepcopy(run.candidate_manifest)
            manifest["candidates"][0]["job_metrics"].update(
                assessed_posting_count=2, selected_posting_count=2, percentage=50.0
            )
            run.candidate_manifest = manifest
            db_session.commit()
        seed_graph(graph_driver, course["id"])
        review = prepare(
            service,
            course,
            revision,
            candidates,
            graph=graph_repo(graph_driver),
            chapter_ids=[f"chapter-{course['id']}"],
        )
        result = approve_sql(service, course, run, review, candidates)
        reference_ids.append(result.review.approved_references[0]["reference_id"])
        assert (
            SkillEvidenceProjector(
                MarketReviewRepository(db_session), graph_repo(graph_driver)
            ).project(course["id"], 1, run_id=run.id)
            == "projected"
        )
    assert reference_ids[0] != reference_ids[1]
    rows = list(
        db_session.scalars(
            select(CourseSkillReference).order_by(CourseSkillReference.course_id)
        )
    )
    assert [row.display_data["job_metrics"]["percentage"] for row in rows] == [
        100.0,
        50.0,
    ]
    with graph_driver.session(database="neo4j") as session:
        skills = [
            dict(row)
            for row in session.run(
                "MATCH (s:CAREER_SKILL {name: 'Python'}) RETURN s.id AS id, s.frequency AS frequency, s.demand_pct AS demand_pct"
            )
        ]
        assert len(skills) == 2 and all(
            row["frequency"] is None and row["demand_pct"] is None for row in skills
        )


def test_retry_cli_projects_only_committed_intent(
    db_session, client, teacher_auth_headers, graph_driver
):
    import json
    import subprocess
    import sys

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    seed_graph(graph_driver, course["id"])
    review = prepare(
        service,
        course,
        revision,
        candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{course['id']}"],
    )
    approve_sql(service, course, run, review, candidates)
    command = [
        sys.executable,
        "/app/scripts/project_market_skill_evidence.py",
        "--course-id",
        str(course["id"]),
        "--run-id",
        str(run.id),
        "--revision",
        "1",
        "--test-graph",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr[-1000:]
    assert json.loads(result.stdout)["projection_status"] == "projected"
    result = subprocess.run(
        command[:-3] + ["--revision", "999", "--test-graph"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 1
    with graph_driver.session(database="neo4j") as session:
        assert (
            session.run(
                "MATCH (b:SKILL_EVIDENCE_BINDING) RETURN count(b) AS n"
            ).single()["n"]
            == 1
        )


def test_sql_approval_survives_actual_graph_stop_and_retry(
    db_session, client, teacher_auth_headers, graph_driver
):
    """Coordinator stops/restarts only the disposable graph at explicit markers."""
    import json
    import subprocess
    import sys
    import time
    from pathlib import Path

    from sqlalchemy import func

    from app.modules.marketdemandanalyst.models import (
        CourseSkillEvidence,
        CourseSkillReference,
        MarketEvidenceRedaction,
        MarketSkillApproval,
    )
    from app.modules.marketdemandanalyst.projection_service import (
        SkillEvidenceProjector,
    )
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    seed_graph(graph_driver, course["id"])
    review = prepare(
        service,
        course,
        revision,
        candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{course['id']}"],
    )
    approve_sql(service, course, run, review, candidates)
    (
        cleanup_course,
        cleanup_run,
        cleanup_candidates,
        cleanup_service,
        cleanup_revision,
    ) = seed_review(
        db_session,
        client,
        teacher_auth_headers,
        labels=("SQL",),
        title="Cleanup outage course",
    )
    seed_graph(graph_driver, cleanup_course["id"], label="SQL")
    cleanup_review = prepare(
        cleanup_service,
        cleanup_course,
        cleanup_revision,
        cleanup_candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{cleanup_course['id']}"],
    )
    approve_sql(
        cleanup_service, cleanup_course, cleanup_run, cleanup_review, cleanup_candidates
    )
    cleanup_projector = SkillEvidenceProjector(
        MarketReviewRepository(db_session), graph_repo(graph_driver)
    )
    assert (
        cleanup_projector.project(cleanup_course["id"], 1, run_id=cleanup_run.id)
        == "projected"
    )
    cleanup_snapshot_id = cleanup_candidates[0]["evidence_references"][0]["snapshot_id"]
    with graph_driver.session(database="neo4j") as session:
        session.run(
            "MATCH (s:CAREER_SKILL {course_id: $course}) MERGE (r:READING_RESOURCE {id: 'outage-saved-resource'}) MERGE (s)-[:HAS_RESOURCE]->(r)",
            course=cleanup_course["id"],
        ).consume()
    cleanup_command = [
        sys.executable,
        "/app/scripts/project_market_skill_evidence.py",
        "--course-id",
        str(cleanup_course["id"]),
        "--redact-only",
        "--test-graph",
    ]
    markers = Path("/tmp/market_skill_outage")
    markers.mkdir(exist_ok=True)
    for name in ("ready", "down", "failed", "up", "done"):
        (markers / name).unlink(missing_ok=True)
    (markers / "ready").write_text("Only disposable graph may be stopped")

    def await_marker(name, timeout=60):
        deadline = time.monotonic() + timeout
        while not (markers / name).exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert (markers / name).exists(), (
            f"Coordinator graph outage marker {name} required"
        )

    await_marker("down")
    projector = SkillEvidenceProjector(
        MarketReviewRepository(db_session), graph_repo(graph_driver)
    )
    assert projector.project(course["id"], 1, run_id=run.id) == "error"
    approval = db_session.scalar(
        select(MarketSkillApproval).where(MarketSkillApproval.run_id == run.id)
    )
    assert (
        approval.revision == 1
        and approval.is_active
        and approval.projection_status == "error"
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CourseSkillReference)
            .where(CourseSkillReference.course_id == course["id"])
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CourseSkillEvidence)
            .where(CourseSkillEvidence.course_id == course["id"])
        )
        == 1
    )
    repo = MarketReviewRepository(db_session)
    repo.purge_vacancy_content(
        cleanup_snapshot_id, reason="Provider removal during graph outage"
    )
    repo.commit()
    assert cleanup_projector.redact(cleanup_course["id"]) == "error"
    assert (
        db_session.scalar(select(MarketEvidenceRedaction.projection_status)) == "error"
    )
    repo.rollback()
    result = subprocess.run(cleanup_command, capture_output=True, text=True, timeout=90)
    assert result.returncode == 1, result.stderr[-1000:]
    assert json.loads(result.stdout)["projection_status"] == "error"
    (markers / "failed").write_text("SQL durable; graph unavailable")
    await_marker("up", timeout=180)
    result = subprocess.run(cleanup_command, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr[-1000:]
    assert json.loads(result.stdout)["projection_status"] == "projected"
    db_session.expire_all()
    assert (
        db_session.scalar(select(MarketEvidenceRedaction.projection_status))
        == "projected"
    )
    repo.rollback()
    assert projector.project(course["id"], 1, run_id=run.id) == "projected"
    assert projector.project(course["id"], 1, run_id=run.id) == "projected"
    with graph_driver.session(database="neo4j") as session:
        row = session.run(
            "MATCH (r:COURSE_SKILL_REFERENCE {course_id: $course}) RETURN count(r) AS refs, COLLECT {MATCH (b:SKILL_EVIDENCE_BINDING {course_id: $course}) RETURN b.id} AS bindings, COLLECT {MATCH (s:CAREER_SKILL {course_id: $course}) RETURN s.id} AS skills",
            course=course["id"],
        ).single()
        assert (
            row["refs"] == 1 and len(row["bindings"]) == 1 and len(row["skills"]) == 1
        )
        evidence = session.run(
            "MATCH (e:CAREER_EVIDENCE {id: $id}) RETURN e.public_json AS payload",
            id=f"jobs:{cleanup_snapshot_id}",
        ).single()
        assert json.loads(evidence["payload"])["content_removed"] is True
        assert "original_phrase" not in json.loads(evidence["payload"])
        assert (
            session.run(
                "MATCH (b:SKILL_EVIDENCE_BINDING {course_id: $course}) RETURN b.active AS active",
                course=cleanup_course["id"],
            ).single()["active"]
            is False
        )
        assert (
            session.run(
                "MATCH (:CAREER_SKILL {course_id: $course})-[:HAS_RESOURCE]->(r:READING_RESOURCE {id: 'outage-saved-resource'}) RETURN r.id AS id",
                course=cleanup_course["id"],
            ).single()["id"]
            == "outage-saved-resource"
        )
    (markers / "done").write_text("Retry projected once; counts unchanged")


@pytest.mark.anyio
@pytest.mark.parametrize("unsupported", [False, True])
async def test_actual_toolnode_linker_prepares_ids_and_insert_delegates_approved_sql(
    db_session, client, teacher_auth_headers, graph_driver, monkeypatch, unsupported
):
    import json
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    if unsupported:
        from copy import deepcopy

        manifest = deepcopy(run.candidate_manifest)
        manifest["candidates"][0]["job_metrics"] = {}
        manifest["candidates"][0]["evidence_references"] = []
        candidates[0] = deepcopy(manifest["candidates"][0])
        run.candidate_manifest = manifest
        db_session.commit()
    seed_graph(graph_driver, course["id"])
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    monkeypatch.setattr(tools, "_get_neo4j_driver", lambda **kwargs: graph_driver)
    monkeypatch.setenv("LAB_TUTOR_NEO4J_DATABASE", "neo4j")
    # The remote model is the only fake; SQL, targets, tools, ToolNode and graph
    # projection remain real. This fixture proposes one explicitly named concept.
    monkeypatch.setattr(
        tools,
        "_get_extraction_llm",
        lambda: SimpleNamespace(
            invoke=lambda *args, **kwargs: SimpleNamespace(
                content=json.dumps(
                    {
                        "existing_concepts": [],
                        "new_concepts": [
                            {"name": "Python expressions", "description": "Expressions"}
                        ],
                    }
                )
            )
        ),
    )
    builder = StateGraph(MessagesState)
    builder.add_node(
        "tools",
        ToolNode(
            tools.owned_sync_tools(
                [
                    tools.save_curriculum_mapping,
                    tools.finalize_cleaned_skills,
                    tools.extract_concepts_for_skills,
                    tools.insert_market_skills_to_neo4j,
                ]
            )
        ),
    )
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    compiled = builder.compile()
    state = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
    }
    state_service = ThreadStateService()
    lease = await state_service.claim(
        service.thread_id(course["id"], course["teacher_id"])
    )

    async def call(name, args):
        response = await compiled.ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": name, "args": args, "id": name}],
                    )
                ]
            }
        )
        return response["messages"][-1].content

    try:
        with bind_tool_store(state, tool_tasks=lease.tool_tasks):
            result = await call(
                "save_curriculum_mapping",
                {
                    "mapping_json": json.dumps(
                        [
                            {
                                "candidate_id": candidates[0]["candidate_id"],
                                "status": "covered",
                                "origin": "book",
                                "graph_target_id": f"book-{course['id']}",
                                "target_chapter": "Programming",
                            }
                        ]
                    )
                },
            )
            assert "Saved" in result, result
            assert "Finalized" in await call("finalize_cleaned_skills", {})
            result = await call("extract_concepts_for_skills", {})
            assert "Prepared final teacher review" in result, result
            db_session.expire_all()
            review = service.get_review(course["id"], course["teacher_id"])
            assert (
                review.integration_review["items"][0]["candidate_id"]
                == candidates[0]["candidate_id"]
            )
            assert (
                review.integration_review["items"][0]["target"]["identity"]
                == f"book:book-{course['id']}"
            )
            assert review.integration_review["items"][0]["concepts"] == [
                {"name": "Python expressions", "description": "Expressions"}
            ]
            assert (
                state["skill_concepts"][candidates[0]["candidate_id"]][
                    "evidence_references"
                ]
                == candidates[0]["evidence_references"]
            )
            assert "required" in await call("insert_market_skills_to_neo4j", {})
            if unsupported:
                from fastapi import HTTPException

                with pytest.raises(HTTPException) as error:
                    approve_sql(service, course, run, review, candidates)
                service.rollback()
                assert error.value.status_code == 422
                assert error.value.detail["code"] == "missing_job_evidence"
                # Expected exception frames retain the compiled ToolNode graph.
                # Release them after assertions; leave pytest GC checks enabled.
                error.value.__traceback__ = None
                del error
                return
            approve_sql(service, course, run, review, candidates)
            result = await call("insert_market_skills_to_neo4j", {})
            assert result == "Approved SQL evidence projection: projected."
        with graph_driver.session(database="neo4j") as session:
            row = session.run(
                "MATCH (s:BOOK_SKILL {id: $id})-[:REQUIRES_CONCEPT]->(c:CONCEPT) RETURN c.name AS name",
                id=f"book-{course['id']}",
            ).single()
            assert row["name"] == "Python expressions"
            assert (
                session.run("MATCH (s:CAREER_SKILL) RETURN count(s) AS n").single()["n"]
                == 0
            )
    finally:
        await state_service.release(lease)


@pytest.mark.parametrize("context", ["current", "missing", "stale"])
def test_durable_delete_preserves_targets_and_resources(
    db_session, client, teacher_auth_headers, graph_driver, monkeypatch, context
):
    from uuid import uuid4

    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run, _, _, _ = seed_review(db_session, client, teacher_auth_headers)
    seed_graph(graph_driver, course["id"])
    with graph_driver.session(database="neo4j") as session:
        session.run(
            "MATCH (c:CLASS {id: $id})-[:HAS_COURSE_CHAPTER]->(ch) "
            "MERGE (s:MARKET_SKILL:SKILL {name: 'Retained competency'}) "
            "MERGE (s)-[:MAPPED_TO]->(ch) "
            "MERGE (r:READING_RESOURCE {id: 'saved-resource'}) "
            "MERGE (s)-[:HAS_RESOURCE]->(r)",
            id=course["id"],
        ).consume()
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    monkeypatch.setattr(tools, "_get_neo4j_driver", lambda **kwargs: graph_driver)
    monkeypatch.setenv("LAB_TUTOR_NEO4J_DATABASE", "neo4j")
    state = {"course_id": course["id"], "teacher_id": course["teacher_id"]}
    if context != "missing":
        state["run_id"] = str(run.id if context == "current" else uuid4())
    with bind_tool_store(state):
        result = tools.delete_market_skills.invoke({"skill_names": "all"})
    assert "withdraw" in result.lower(), result
    with graph_driver.session(database="neo4j") as session:
        row = session.run(
            "MATCH (:MARKET_SKILL {name: 'Retained competency'})-[:HAS_RESOURCE]->(r:READING_RESOURCE) RETURN r.id AS id"
        ).single()
        assert row and row["id"] == "saved-resource"
