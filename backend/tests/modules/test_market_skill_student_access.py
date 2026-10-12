"""Student publication consumers against real SQL and disposable graph."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.neo4j import get_neo4j_driver, require_neo4j_session
from app.modules.auth.models import User
from app.modules.courses.models import CourseEnrollment
from app.modules.marketdemandanalyst.models import CourseSkillReference
from app.modules.marketdemandanalyst.projection_service import SkillEvidenceProjector
from app.modules.marketdemandanalyst.repository import MarketReviewRepository
from main import app
from tests.market_skill_fixtures import prepare, seed_review
from tests.modules.test_market_skill_projection import (
    approve_sql,
    graph_repo,
    seed_graph,
)

pytest_plugins = ["tests.fixtures.market_skill_graph"]


@pytest.fixture
def offering(
    db_session, client, teacher_auth_headers, student_auth_headers, graph_driver
):
    course, run, candidates, review_service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    seed_graph(graph_driver, course["id"], label="Legacy book skill")
    student = db_session.scalar(select(User).where(User.email == "student@example.com"))
    db_session.add(CourseEnrollment(course_id=course["id"], student_id=student.id))
    db_session.commit()
    with graph_driver.session(database="neo4j") as session:
        session.run("MERGE (:USER:STUDENT {id:$id})", id=student.id).consume()
        session.run(
            "MATCH (c:CLASS {id:$id}) SET c.title='Approval course', c.selection_min_skills=1, c.selection_max_skills=20 WITH c MATCH (c)-[:HAS_COURSE_CHAPTER]->(ch) SET ch.chapter_index=1",
            id=course["id"],
        ).consume()
    review = prepare(
        review_service,
        course,
        revision,
        candidates,
        graph=graph_repo(graph_driver),
        chapter_ids=[f"chapter-{course['id']}"],
        concepts=[{"name": "Variables", "description": "Store values"}],
    )
    approve_sql(review_service, course, run, review, candidates)
    projector = SkillEvidenceProjector(
        MarketReviewRepository(db_session), graph_repo(graph_driver)
    )

    def real_session():
        with graph_driver.session(database="neo4j") as session:
            yield session

    app.dependency_overrides[require_neo4j_session] = real_session
    app.dependency_overrides[get_neo4j_driver] = lambda: graph_driver
    yield dict(
        course=course,
        run=run,
        candidates=candidates,
        review_service=review_service,
        revision=revision,
        projector=projector,
        student=student,
        headers=student_auth_headers,
        driver=graph_driver,
    )
    app.dependency_overrides.pop(require_neo4j_session, None)
    app.dependency_overrides[get_neo4j_driver] = lambda: None


def bank(client, o):
    response = client.get(
        f"/student-learning-path/{o['course']['id']}/skill-banks", headers=o["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()


def publish(o):
    assert (
        o["projector"].project(o["course"]["id"], 1, run_id=o["run"].id) == "projected"
    )


def select_id(client, o, ids):
    return client.post(
        f"/student-learning-path/{o['course']['id']}/select-skills",
        json={"skill_reference_ids": ids},
        headers=o["headers"],
    )


def test_pending_then_projected_bank_and_id_selection(client, offering):
    o = offering
    row = bank(client, o)["career_skill_bank"][0]
    assert row["label"] == "Python"
    assert row["source"] == "market"
    assert row["projection_status"] == "pending"
    assert row["available_for_new_selection"] is False
    assert row["qualifying_posting_links"] == [
        o["candidates"][0]["evidence_references"][0]["original_url"]
    ]
    response = select_id(client, o, [row["skill_reference_id"]])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "skill_unavailable"
    publish(o)
    row = bank(client, o)["career_skill_bank"][0]
    assert (
        row["projection_status"] == "projected" and row["available_for_new_selection"]
    )
    assert row["job_metrics"]["supporting_posting_count"] == 1
    assert select_id(client, o, [row["skill_reference_id"]]).status_code == 200
    result = bank(client, o)
    assert result["selected_skill_reference_ids"] == [row["skill_reference_id"]]
    assert result["career_skill_bank"][0]["is_selected"]
    posting = next(
        p
        for p in result["market_skill_bank"]
        if p["url"] == row["qualifying_posting_links"][0]
    )
    assert posting["skills"][0]["skill_reference_id"] == row["skill_reference_id"]


@pytest.mark.parametrize("failure", ["unknown", "pending", "purged", "withdrawn"])
def test_mixed_explicit_selection_is_atomic_and_names_do_not_bypass(
    client, db_session, offering, failure
):
    o = offering
    if failure != "pending":
        publish(o)
    reference = db_session.scalar(
        select(CourseSkillReference).where(CourseSkillReference.source == "market")
    )
    ref_id = str(reference.id)
    if failure == "unknown":
        ref_id = str(uuid4())
    elif failure == "purged":
        MarketReviewRepository(db_session).purge_vacancy_content(
            o["candidates"][0]["evidence_references"][0]["snapshot_id"],
            reason="Provider removal",
        )
        db_session.commit()
    elif failure == "withdrawn":
        review = o["review_service"].prepare_withdrawal_review(
            o["course"]["id"], o["course"]["teacher_id"], o["revision"]
        )
        approve_sql(o["review_service"], o["course"], o["run"], review, [])
    response = client.post(
        f"/student-learning-path/{o['course']['id']}/build",
        json={
            "skill_reference_ids": [ref_id],
            "selected_skills": [{"name": "Legacy book skill", "source": "book"}],
        },
        headers=o["headers"],
    )
    assert response.status_code == (422 if failure == "unknown" else 409), response.text
    assert bank(client, o)["selected_skill_names"] == []
    if failure != "unknown":
        response = client.post(
            f"/student-learning-path/{o['course']['id']}/select-skills",
            json={
                "skill_names": ["Python"],
                "source": "market",
                "legacy_exemption": True,
            },
            headers=o["headers"],
        )
        assert response.status_code == 409, response.text


def test_same_label_legacy_book_and_career_market_keep_distinct_ids(client, offering):
    o = offering
    with o["driver"].session(database="neo4j") as session:
        session.run("MATCH (s:BOOK_SKILL) SET s.name='Python'").consume()
    publish(o)
    response = client.post(
        f"/student-learning-path/{o['course']['id']}/select-skills",
        json={"skill_names": ["Python"], "source": "book"},
        headers=o["headers"],
    )
    assert response.status_code == 200, response.text
    market = bank(client, o)["career_skill_bank"][0]
    assert not market["is_selected"]
    assert select_id(client, o, [market["skill_reference_id"]]).status_code == 200
    result = bank(client, o)
    assert len(set(result["selected_skill_reference_ids"])) == 2
    assert result["career_skill_bank"][0]["peer_count"] == 1


def test_resources_and_questions_write_only_reference_target_and_recovery_survives_withdrawal(
    client, db_session, offering, monkeypatch
):
    from app.core.resource_pipeline.schemas import CandidateResource, ResourceScore
    from app.modules.question_generation.schemas import GeneratedQuestion
    from app.modules.student_learning_path import graph
    from app.modules.student_learning_path import service as student_service

    o = offering
    publish(o)
    row = bank(client, o)["career_skill_bank"][0]
    assert select_id(client, o, [row["skill_reference_id"]]).status_code == 200
    # An unrelated same-name node must never receive this target's resources.
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "CREATE (:BOOK_SKILL:SKILL {id:'unrelated', name:'Python'})"
        ).consume()
    import json
    from types import SimpleNamespace

    from app.core.resource_pipeline import pipeline
    from app.modules.question_generation import service as question_service

    # Only provider/model outputs are deterministic: real query construction,
    # filtering, rubric parsing, coverage selection and question parsing run.
    score = ResourceScore(
        recency_score=1,
        concept_coverage_score=1,
        pedagogy_score=1,
        depth_score=1,
        extra_score=1,
        concepts_covered=["Variables"],
    )

    def chat(messages, **kwargs):
        if "CANDIDATES" in messages[-1]["content"]:
            return json.dumps({"scores": [score.model_dump()]})
        return json.dumps(
            {
                "queries": [
                    "python variables tutorial",
                    "python examples",
                    "python introductory guide",
                    "python variables lesson",
                ]
            }
        )

    def search(queries, **kwargs):
        if kwargs.get("video_only"):
            return [
                CandidateResource(
                    url="https://www.youtube.com/watch?v=task9",
                    title="Python video",
                    domain="youtube.com",
                    snippet="Variables",
                    source_engine="test",
                    video_id="task9",
                )
            ]
        return [
            CandidateResource(
                url="https://example.org/python",
                title="Python reading",
                domain="example.org",
                snippet="Variables",
                source_engine="test",
            )
        ]

    monkeypatch.setattr(pipeline, "_chat", chat)
    monkeypatch.setattr(
        pipeline, "_embed_texts", lambda texts, **kwargs: [[1.0, 0.0] for _ in texts]
    )
    monkeypatch.setattr(pipeline, "search_for_skill", search)
    questions = [
        GeneratedQuestion(
            text=f"Question {d}",
            difficulty=d,
            options=["a", "b", "c", "d"],
            correct_option="A",
            answer="a",
        ).model_dump()
        for d in ("easy", "medium", "hard")
    ]

    class Completion:
        def create(self, **kwargs):
            assert "Skill: Python" in kwargs["messages"][-1]["content"]
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps({"questions": questions})
                        )
                    )
                ]
            )

    monkeypatch.setattr(
        question_service,
        "_get_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=Completion())),
    )
    state = {
        "student_id": o["student"].id,
        "course_id": o["course"]["id"],
        "neo4j_driver": o["driver"],
        "skills_to_process": [],
        "results": [],
    }
    events = list(graph.learning_path_graph.stream(state, stream_mode="custom"))
    assert not any(e.get("phase") == "question_error" for e in events), events
    with o["driver"].session(database="neo4j") as session:
        actual = session.run(
            "MATCH (s:CAREER_SKILL)-[:HAS_READING]->(r) RETURN r.id AS id"
        ).single()
        assert actual
        reading_id = actual["id"]
        assert (
            session.run(
                "MATCH (:BOOK_SKILL {id:'unrelated'})-[r:HAS_READING|HAS_QUESTION]->() RETURN count(r) AS n"
            ).single()["n"]
            == 0
        )
        assert (
            session.run(
                "MATCH (:CAREER_SKILL)-[:HAS_QUESTION]->(q) RETURN count(q) AS n"
            ).single()["n"]
            == 3
        )
    from app.core.resource_pipeline.neo4j_repository import get_resources_for_course

    with o["driver"].session(database="neo4j") as session:
        readings = get_resources_for_course(
            session, o["course"]["id"], "READING_RESOURCE", "HAS_READING"
        )
        assert (
            len(readings) == 1
            and readings[0]["resources"][0]["url"] == "https://example.org/python"
        )
    quiz = client.get(
        f"/student-learning-path/{o['course']['id']}/chapters/1/quiz",
        headers=o["headers"],
    )
    assert quiz.status_code == 200, quiz.text
    easy_id = quiz.json()["questions"][0]["id"]
    submitted = client.post(
        f"/student-learning-path/{o['course']['id']}/chapters/1/quiz/submit",
        json={"answers": [{"question_id": easy_id, "selected_option": "A"}]},
        headers=o["headers"],
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["skills_known"] == ["Python"]
    review = o["review_service"].prepare_withdrawal_review(
        o["course"]["id"], o["course"]["teacher_id"], o["revision"]
    )
    approve_sql(o["review_service"], o["course"], o["run"], review, [])
    assert (
        o["projector"].project(o["course"]["id"], 2, run_id=o["run"].id) == "projected"
    )
    path = client.get(
        f"/student-learning-path/{o['course']['id']}/path", headers=o["headers"]
    )
    assert path.status_code == 200, path.text
    skill = path.json()["chapters"][0]["selected_skills"][0]
    assert skill["skill_reference_id"] == row["skill_reference_id"]
    assert skill["readings"][0]["id"] == reading_id
    assert skill["videos"][0]["video_id"] == "task9"
    assert not skill["available_for_new_selection"] and skill["is_known"]
    assert skill["questions"][0]["id"] == easy_id

    # Run the real compiled graph synchronously; avoid a detached TestClient task.
    async def run_pipeline(self, run_id, student_id, course_id, driver, queue):
        for event in graph.learning_path_graph.stream(state, stream_mode="custom"):
            await queue.put(event)
        await queue.put(None)
        student_service._active_runs.pop(run_id, None)

    monkeypatch.setattr(
        student_service.StudentLearningPathService, "_run_pipeline", run_pipeline
    )
    recovery = client.post(
        f"/student-learning-path/{o['course']['id']}/build", headers=o["headers"]
    )
    assert recovery.status_code == 202, recovery.text
    assert select_id(client, o, [row["skill_reference_id"]]).status_code == 409


def test_cross_run_support_union_metrics_null_then_surviving_run_fallback(
    client, db_session, teacher_auth_headers, offering
):
    o = offering
    publish(o)
    _, second, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, course=o["course"]
    )
    review = prepare(
        service,
        o["course"],
        revision,
        candidates,
        graph=graph_repo(o["driver"]),
        chapter_ids=[f"chapter-{o['course']['id']}"],
    )
    approve_sql(service, o["course"], second, review, candidates)
    assert o["projector"].project(o["course"]["id"], 1, run_id=second.id) == "projected"
    row = bank(client, o)["career_skill_bank"][0]
    assert len(row["qualifying_posting_links"]) == 2
    assert row["job_metrics"] is None
    withdrawal = service.prepare_withdrawal_review(
        o["course"]["id"], o["course"]["teacher_id"], revision
    )
    approve_sql(service, o["course"], second, withdrawal, [])
    assert o["projector"].project(o["course"]["id"], 2, run_id=second.id) == "projected"
    row = bank(client, o)["career_skill_bank"][0]
    assert row["job_metrics"]["supporting_posting_count"] == 1
    assert row["qualifying_posting_links"] == [
        o["candidates"][0]["evidence_references"][0]["original_url"]
    ]
    assert row["available_for_new_selection"]


def test_same_source_same_label_is_ambiguous_and_foreign_ids_rejected(
    client, db_session, teacher_auth_headers, offering
):
    o = offering
    publish(o)
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (ch:COURSE_CHAPTER {id:$chapter}) CREATE (s:MARKET_SKILL:SKILL {name:'Python', evidence_target_id:'legacy-python'}) CREATE (s)-[:MAPPED_TO]->(ch)",
            chapter=f"chapter-{o['course']['id']}",
        ).consume()
    response = client.post(
        f"/student-learning-path/{o['course']['id']}/select-skills",
        json={"skill_names": ["Python"], "source": "market"},
        headers=o["headers"],
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "ambiguous_skill_name"
    foreign, _, _, _, _ = seed_review(
        db_session, client, teacher_auth_headers, title="Foreign course"
    )
    foreign_ref = CourseSkillReference(
        course_id=foreign["id"],
        target_identity=f"career:{uuid4()}",
        label="Python",
        source="market",
        origin="market_demand",
    )
    db_session.add(foreign_ref)
    db_session.commit()
    response = select_id(client, o, [str(foreign_ref.id)])
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "invalid_skill_reference"
    assert bank(client, o)["selected_skill_names"] == []


def test_posting_bulk_selects_available_targets_using_canonical_book_source(
    client, db_session, teacher_auth_headers, offering
):
    o = offering
    # Cover the verified legacy book target with a new job approval.
    with o["driver"].session(database="neo4j") as session:
        session.run("MATCH (s:BOOK_SKILL) SET s.name='Python'").consume()
    _, covered_run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, course=o["course"]
    )
    review = prepare(
        service,
        o["course"],
        revision,
        candidates,
        graph=graph_repo(o["driver"]),
        disposition="covered",
        graph_target_id=f"book-{o['course']['id']}",
        chapter_ids=[f"chapter-{o['course']['id']}"],
    )
    approve_sql(service, o["course"], covered_run, review, candidates)
    # Pending attached evidence must not block an independently usable book target.
    rows = bank(client, o)["career_skill_bank"]
    covered = next(row for row in rows if row["source"] == "book")
    assert (
        covered["available_for_new_selection"]
        and covered["projection_status"] == "projected"
    )
    publish(o)
    assert (
        o["projector"].project(o["course"]["id"], 1, run_id=covered_run.id)
        == "projected"
    )
    url = candidates[0]["evidence_references"][0]["original_url"]
    response = client.post(
        f"/student-learning-path/{o['course']['id']}/select-job-postings",
        json={"posting_urls": [url]},
        headers=o["headers"],
    )
    assert response.status_code == 200, response.text
    rows = bank(client, o)["career_skill_bank"]
    assert next(row for row in rows if row["source"] == "book")["is_selected"]
    assert not next(row for row in rows if row["source"] == "market")["is_selected"]
    with o["driver"].session(database="neo4j") as session:
        assert (
            session.run(
                "MATCH (:STUDENT {id:$id})-[s:SELECTED_SKILL]->(:BOOK_SKILL) RETURN s.source AS source",
                id=o["student"].id,
            ).single()["source"]
            == "book"
        )

    def remove_posting(posting_url):
        response = client.request(
            "DELETE",
            f"/student-learning-path/{o['course']['id']}/deselect-job-posting",
            json={"posting_url": posting_url},
            headers=o["headers"],
        )
        assert response.status_code == 200, response.text

    remove_posting(url)
    assert not next(
        row for row in bank(client, o)["career_skill_bank"] if row["source"] == "book"
    )["is_selected"]
    # Two genuine legacy posting links to the same book target preserve the other origin.
    second_url = "https://example.org/second-posting"
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (s:BOOK_SKILL) MERGE (jp:JOB_POSTING {url:$url}) MERGE (s)-[:SOURCED_FROM]->(jp)",
            url=second_url,
        ).consume()
    response = client.post(
        f"/student-learning-path/{o['course']['id']}/select-job-postings",
        json={"posting_urls": [url, second_url]},
        headers=o["headers"],
    )
    assert response.status_code == 200, response.text
    remove_posting(url)
    assert next(
        row for row in bank(client, o)["career_skill_bank"] if row["source"] == "book"
    )["is_selected"]
    remove_posting(second_url)
    assert not next(
        row for row in bank(client, o)["career_skill_bank"] if row["source"] == "book"
    )["is_selected"]
    assert select_id(client, o, [covered["skill_reference_id"]]).status_code == 200
    response = client.post(
        f"/student-learning-path/{o['course']['id']}/select-job-postings",
        json={"posting_urls": [url]},
        headers=o["headers"],
    )
    assert response.status_code == 200, response.text
    remove_posting(url)
    assert next(
        row for row in bank(client, o)["career_skill_bank"] if row["source"] == "book"
    )["is_selected"]


def test_explicit_build_replaces_saved_selection_and_deduplicates_resolved_target(
    client, offering, monkeypatch
):
    from app.modules.student_learning_path.service import StudentLearningPathService

    o = offering
    publish(o)
    row = bank(client, o)["career_skill_bank"][0]
    assert select_id(client, o, [row["skill_reference_id"]]).status_code == 200

    async def provider_free_pipeline(self, *args):
        return None

    monkeypatch.setattr(
        StudentLearningPathService, "_run_pipeline", provider_free_pipeline
    )
    response = client.post(
        f"/student-learning-path/{o['course']['id']}/build",
        json={
            "selected_skills": [
                {"name": "Legacy book skill", "source": "book"},
                {"name": "Legacy book skill", "source": "book"},
            ]
        },
        headers=o["headers"],
    )
    assert response.status_code == 202, response.text
    result = bank(client, o)
    assert result["selected_skill_names"] == ["Legacy book skill"]
    assert not result["career_skill_bank"][0]["is_selected"]


@pytest.mark.parametrize("entry", ["route", "service", "cli"])
def test_projected_approval_updates_readiness_once_across_recovery_entrypoints(
    client, db_session, teacher_auth_headers, offering, entry
):
    import subprocess
    import sys

    from app.modules.courses.models import Course, CourseMarketGateStatus
    from app.modules.curricularalignmentarchitect.skill_prerequisites.review_models import (
        PrerequisiteReview,
    )
    from app.modules.curricularalignmentarchitect.skill_prerequisites.schemas import (
        PrerequisiteReviewStatus,
    )

    o = offering
    review = PrerequisiteReview(
        course_id=o["course"]["id"], review_status=PrerequisiteReviewStatus.APPROVED
    )
    db_session.add(review)
    db_session.commit()
    assert (
        db_session.get(Course, o["course"]["id"]).market_gate_status
        != CourseMarketGateStatus.COMPLETED
    )
    assert (
        SkillEvidenceProjector(MarketReviewRepository(db_session), None).project(
            o["course"]["id"], 1, run_id=o["run"].id
        )
        == "pending"
    )
    db_session.expire_all()
    assert (
        db_session.get(PrerequisiteReview, o["course"]["id"]).review_status
        == PrerequisiteReviewStatus.APPROVED
    )
    if entry == "route":
        response = client.post(
            f"/courses/{o['course']['id']}/market-demand/integration-approval",
            json={
                "run_id": str(o["run"].id),
                "expected_candidate_revision": 1,
                "expected_selection_revision": 1,
                "review_digest": o["run"].integration_review["review_digest"],
                "approved_candidate_ids": [o["candidates"][0]["candidate_id"]],
            },
            headers=teacher_auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["projection_status"] == "projected"
    elif entry == "cli":
        command = [
            sys.executable,
            "/app/scripts/project_market_skill_evidence.py",
            "--course-id",
            str(o["course"]["id"]),
            "--run-id",
            str(o["run"].id),
            "--revision",
            "1",
            "--test-graph",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stderr[-500:]
    else:
        publish(o)
    db_session.expire_all()
    assert (
        db_session.get(Course, o["course"]["id"]).market_gate_status
        == CourseMarketGateStatus.COMPLETED
    )
    review = db_session.get(PrerequisiteReview, o["course"]["id"])
    assert review.review_status == PrerequisiteReviewStatus.STALE
    invalidated = review.last_invalidated_at
    review.review_status = PrerequisiteReviewStatus.APPROVED
    db_session.commit()
    publish(o)
    db_session.expire_all()
    review = db_session.get(PrerequisiteReview, o["course"]["id"])
    assert review.review_status == PrerequisiteReviewStatus.APPROVED
    assert review.last_invalidated_at == invalidated


def test_prerequisite_discovery_preserves_reference_targets_when_names_collide(
    db_session, offering
):
    from app.modules.curricularalignmentarchitect.skill_prerequisites.repository import (
        load_all_skills_for_course,
        merge_skill_into_canonical,
    )

    o = offering
    publish(o)
    ref = db_session.scalar(
        select(CourseSkillReference).where(CourseSkillReference.source == "market")
    )
    ref.label = "Different SQL display label"
    db_session.commit()
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (s:CAREER_SKILL) MERGE (r:READING_RESOURCE {url:'https://example.org/protected'}) ON CREATE SET r.id='protected-reading' MERGE (s)-[:HAS_READING]->(r)"
        ).consume()
        session.run(
            "CREATE (:SKILL:BOOK_SKILL {id:'foreign-alias',name:'Python'})"
        ).consume()
    skills = load_all_skills_for_course(o["driver"], o["course"]["id"])
    assert any(s["name"] == "Python" and s.get("reference_bound") for s in skills)
    merge_skill_into_canonical(o["driver"], "Legacy book skill", ["Python"])
    with o["driver"].session(database="neo4j") as session:
        assert (
            session.run(
                "MATCH (:CAREER_SKILL {name:'Python'})-[:HAS_READING]->(r {id:'protected-reading'}) RETURN count(r) AS n"
            ).single()["n"]
            == 1
        )
        assert (
            session.run(
                "MATCH (:BOOK_SKILL {id:'foreign-alias'}) RETURN count(*) AS n"
            ).single()["n"]
            == 1
        )


def test_mixed_onet_context_is_safe_and_onet_only_reference_is_not_published(
    client, db_session, teacher_auth_headers, offering
):
    from copy import deepcopy

    from app.modules.occupation_reference.models import (
        OnetEvidence,
        OnetOccupation,
        OnetRelease,
    )

    o = offering
    _, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, course=o["course"], mixed=True
    )
    release = OnetRelease(
        version="31.0", manifest={"files": {}}, attribution="O*NET 31.0 attribution"
    )
    occupation = OnetOccupation(
        release="31.0",
        soc_code="15-1252.00",
        title="Software Developers",
        description="Develop software",
    )
    evidence = OnetEvidence(
        id=uuid4(),
        release="31.0",
        soc_code="15-1252.00",
        family="transferable",
        element_id="2.B.2.i",
        label="Programming",
        definition="Writing programs",
        ratings={
            "IM": {
                "scale_id": "IM",
                "value": None,
                "minimum": 1,
                "maximum": 5,
                "status": "missing",
                "date": None,
                "quality": {},
            }
        },
        flags={},
        source_rows=[{"private_raw": "Not for students"}],
        source_key="programming",
    )
    db_session.add(release)
    db_session.flush()
    db_session.add(occupation)
    db_session.flush()
    db_session.add(evidence)
    db_session.flush()
    association = {
        "relation": "broader",
        "mapping_method": "reference_context",
        "rationale": "Context only",
        "evidence": {
            "id": str(evidence.id),
            "release": "31.0",
            "soc_code": "15-1252.00",
            "occupation_title": "Software Developers",
            "family": "transferable",
            "element_id": "2.B.2.i",
            "label": "Programming",
            "definition": "Writing programs",
            "workplace_example": None,
            "ratings": evidence.ratings,
            "flags": {},
            "source_url": "https://www.onetonline.org/link/summary/15-1252.00",
            "attribution": "O*NET 31.0 attribution",
        },
    }
    manifest = deepcopy(run.candidate_manifest)
    manifest["candidates"][0]["onet_associations"] = [association]
    run.candidate_manifest = manifest
    run.config = {
        **run.config,
        "onet_release": "31.0",
        "selected_onet_occupations": [{"soc_code": "15-1252.00"}],
    }
    unsupported = CourseSkillReference(
        course_id=o["course"]["id"],
        target_identity=f"career:{uuid4()}",
        label="Unsupported O*NET",
        source="market",
        origin="onet",
    )
    db_session.add(unsupported)
    db_session.commit()
    review = prepare(
        service,
        o["course"],
        revision,
        candidates,
        graph=graph_repo(o["driver"]),
        chapter_ids=[f"chapter-{o['course']['id']}"],
    )
    approve_sql(service, o["course"], run, review, candidates)
    assert o["projector"].project(o["course"]["id"], 1, run_id=run.id) == "projected"
    rows = bank(client, o)["career_skill_bank"]
    assert len(rows) == 1
    association = rows[0]["onet_associations"][0]
    assert association["relation"] == "broader"
    assert association["evidence"]["ratings"]["IM"]["status"] == "missing"
    assert association["evidence"]["occupation_title"] == "Software Developers"
    assert "private_raw" not in str(rows) and "source_rows" not in str(rows)
    assert select_id(client, o, [str(unsupported.id)]).status_code == 409


def test_teacher_bank_and_student_insight_share_ids_and_safe_overlays(
    client, teacher_auth_headers, offering
):
    o = offering
    publish(o)
    career = bank(client, o)["career_skill_bank"][0]
    assert select_id(client, o, [career["skill_reference_id"]]).status_code == 200
    response = client.get(
        f"/courses/{o['course']['id']}/skill-banks", headers=teacher_auth_headers
    )
    assert response.status_code == 200, response.text
    teacher = response.json()["career_skill_bank"][0]
    assert teacher["skill_reference_id"] == career["skill_reference_id"]
    assert not teacher["is_selected"] and teacher["peer_count"] == 0
    response = client.get(
        f"/courses/{o['course']['id']}/student-insights/{o['student'].id}",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200, response.text
    overlay = response.json()["skill_banks"]
    assert overlay["selected_skill_reference_ids"] == [career["skill_reference_id"]]
    assert overlay["career_skill_bank"][0]["is_selected"]
    assert (
        overlay["peer_selection_counts_by_reference"][career["skill_reference_id"]] == 1
    )
    response = client.request(
        "DELETE",
        f"/student-learning-path/{o['course']['id']}/deselect-skills",
        json={"skill_reference_ids": [career["skill_reference_id"]]},
        headers=o["headers"],
    )
    assert response.status_code == 200, response.text
    assert bank(client, o)["selected_skill_reference_ids"] == []


def _assert_readiness_upgrade_databases(fixture_database, application_database):
    assert fixture_database in {"lab_tutor_test", "lab_tutor_workspace_test"}
    assert application_database == fixture_database


@pytest.mark.parametrize("database", ["lab_tutor_test", "lab_tutor_workspace_test"])
def test_readiness_upgrade_database_guard_accepts_exact_disposable_pair(database):
    _assert_readiness_upgrade_databases(database, database)


@pytest.mark.parametrize(
    "fixture_database,application_database",
    [
        ("lab_tutor_test_copy", "lab_tutor_test_copy"),
        ("production_lab_tutor_test", "production_lab_tutor_test"),
        ("lab_tutor", "lab_tutor"),
        ("configured_database", "configured_database"),
        ("lab_tutor_test", "lab_tutor_workspace_test"),
        ("lab_tutor_workspace_test", "lab_tutor_test"),
        ("lab_tutor_workspace_test", "lab_tutor"),
    ],
)
def test_readiness_upgrade_database_guard_rejects_unsafe_or_mismatched_pair(
    fixture_database, application_database
):
    with pytest.raises(AssertionError):
        _assert_readiness_upgrade_databases(fixture_database, application_database)


@pytest.mark.parametrize("gate", ["completed", "waived", "not_started"])
def test_readiness_marker_upgrade_preserves_old_projected_and_never_rewrites_new_marker(
    db_session, offering, gate
):
    from sqlalchemy import text

    from app.modules.courses.models import Course, CourseMarketGateStatus
    from app.modules.marketdemandanalyst.models import MarketSkillApproval
    from main import _ensure_sql_schema_upgrades, engine

    o = offering
    publish(o)
    db_session.get(
        Course, o["course"]["id"]
    ).market_gate_status = CourseMarketGateStatus(gate)
    db_session.commit()
    with engine.connect() as connection:
        application_database = connection.scalar(text("SELECT current_database()"))
    fixture_database = db_session.scalar(text("SELECT current_database()"))
    # Only disposable PostgreSQL schema; production/main is never a fallback.
    _assert_readiness_upgrade_databases(fixture_database, application_database)
    db_session.execute(
        text("ALTER TABLE market_skill_approvals DROP COLUMN readiness_applied")
    )
    db_session.commit()
    _ensure_sql_schema_upgrades()
    db_session.expire_all()
    approval = db_session.scalar(select(MarketSkillApproval))
    assert approval.readiness_applied is (gate != "not_started")
    if gate == "not_started":
        publish(o)
        db_session.expire_all()
        assert approval.readiness_applied is True
        assert (
            db_session.get(Course, o["course"]["id"]).market_gate_status
            == CourseMarketGateStatus.COMPLETED
        )
    approval.readiness_applied = False
    db_session.commit()
    _ensure_sql_schema_upgrades()
    db_session.expire_all()
    assert db_session.get(MarketSkillApproval, approval.id).readiness_applied is False


def shared_book_course(client, db_session, teacher_auth_headers, o):
    response = client.post(
        "/courses", json={"title": "Second shared course"}, headers=teacher_auth_headers
    )
    assert response.status_code == 201, response.text
    second = response.json()
    db_session.add(CourseEnrollment(course_id=second["id"], student_id=o["student"].id))
    db_session.commit()
    seed_graph(o["driver"], second["id"], label="Second book skill")
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (c:CLASS {id:$id}) SET c.title='Second shared course'",
            id=second["id"],
        ).consume()
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (s:BOOK_SKILL {id:$book}), (ch:COURSE_CHAPTER {id:$chapter}) MERGE (s)-[:MAPPED_TO]->(ch) WITH s MERGE (q:QUESTION {id:'shared-easy'}) SET q.difficulty='easy', q.text='Shared question', q.options=['a','b','c','d'], q.correct_option='A' MERGE (s)-[:HAS_QUESTION]->(q)",
            book=f"book-{o['course']['id']}",
            chapter=f"chapter-{second['id']}",
        ).consume()
        session.run(
            "MATCH (ch:COURSE_CHAPTER {id:$chapter}) SET ch.chapter_index=1",
            chapter=f"chapter-{second['id']}",
        ).consume()
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (s:BOOK_SKILL {id:$skill}) MERGE (b:BOOK {id:'shared-candidate-book'}) SET b.title='Shared book' MERGE (ch:BOOK_CHAPTER {id:'shared-book-chapter'}) SET ch.title='Shared chapter',ch.chapter_index=1 MERGE (b)-[:HAS_CHAPTER]->(ch) MERGE (ch)-[:HAS_SKILL]->(s) WITH b MATCH (course:CLASS) WHERE course.id IN $courses MERGE (course)-[:CANDIDATE_BOOK]->(b)",
            skill=f"book-{o['course']['id']}",
            courses=[o["course"]["id"], second["id"]],
        ).consume()
    return second


def test_legacy_selection_upgrade_preserves_one_path_question_and_other_course(
    client, db_session, teacher_auth_headers, offering
):
    o = offering
    second = shared_book_course(client, db_session, teacher_auth_headers, o)
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (u:STUDENT {id:$student}), (s:BOOK_SKILL {id:$book}) MERGE (u)-[r:SELECTED_SKILL]->(s) SET r.source='book'",
            student=o["student"].id,
            book=f"book-{o['course']['id']}",
        ).consume()
    legacy = bank(client, o)["book_skill_banks"][0]["chapters"][0]["skills"][0]
    assert select_id(client, o, [legacy["skill_reference_id"]]).status_code == 200
    path = client.get(
        f"/student-learning-path/{o['course']['id']}/path", headers=o["headers"]
    )
    assert path.status_code == 200, path.text
    assert len(path.json()["chapters"][0]["selected_skills"]) == 1
    quiz = client.get(
        f"/student-learning-path/{o['course']['id']}/chapters/1/quiz",
        headers=o["headers"],
    )
    assert quiz.status_code == 200, quiz.text
    assert len(quiz.json()["questions"]) == 1
    response = client.request(
        "DELETE",
        f"/student-learning-path/{o['course']['id']}/deselect-skills",
        json={"skill_reference_ids": [legacy["skill_reference_id"]]},
        headers=o["headers"],
    )
    assert response.status_code == 200, response.text
    path = client.get(
        f"/student-learning-path/{second['id']}/path", headers=o["headers"]
    )
    assert path.status_code == 200, path.text
    assert len(path.json()["chapters"][0]["selected_skills"]) == 1


def test_course_scoped_quiz_get_submission_and_progress_do_not_leak_shared_target(
    client, db_session, teacher_auth_headers, offering
):
    from app.modules.student_learning_path import neo4j_repository as repository

    o = offering
    second = shared_book_course(client, db_session, teacher_auth_headers, o)
    legacy = bank(client, o)["book_skill_banks"][0]["chapters"][0]["skills"][0]
    assert select_id(client, o, [legacy["skill_reference_id"]]).status_code == 200
    with o["driver"].session(database="neo4j") as session:
        assert (
            repository.get_chapter_easy_questions(
                session, o["student"].id, second["id"], 1
            )["questions"]
            == []
        )
        assert (
            repository.get_chapter_quiz_progress(session, o["student"].id, second["id"])
            == []
        )
        assert (
            repository.submit_chapter_answers(
                session,
                o["student"].id,
                second["id"],
                1,
                [{"question_id": "shared-easy", "selected_option": "A"}],
            )
            == []
        )
        assert (
            session.run(
                "MATCH (:STUDENT {id:$student})-[r:ANSWERED]->(:QUESTION {id:'shared-easy'}) RETURN count(r) AS n",
                student=o["student"].id,
            ).single()["n"]
            == 0
        )
    response = client.get(
        f"/student-learning-path/{second['id']}/chapters/1/quiz", headers=o["headers"]
    )
    assert response.status_code == 404, response.text
    response = client.post(
        f"/student-learning-path/{second['id']}/chapters/1/quiz/submit",
        json={"answers": [{"question_id": "shared-easy", "selected_option": "A"}]},
        headers=o["headers"],
    )
    assert response.status_code == 404, response.text
    response = client.post(
        f"/student-learning-path/{o['course']['id']}/chapters/1/quiz/submit",
        json={"answers": [{"question_id": "shared-easy", "selected_option": "A"}]},
        headers=o["headers"],
    )
    assert response.status_code == 200, response.text


def test_additive_banks_retain_legacy_market_metadata_without_new_metrics(
    client, teacher_auth_headers, offering
):
    o = offering
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (ch:COURSE_CHAPTER {id:$chapter}) MERGE (s:SKILL:MARKET_SKILL {name:'Legacy metadata'}) SET s.category='programming',s.status='uncovered',s.priority='high',s.demand_pct=42.5 MERGE (s)-[:MAPPED_TO]->(ch) MERGE (jp:JOB_POSTING {url:'https://example.org/legacy-metadata'}) SET jp.title='Legacy posting' MERGE (s)-[:SOURCED_FROM]->(jp)",
            chapter=f"chapter-{o['course']['id']}",
        ).consume()
    student = bank(client, o)
    skill = next(
        p
        for p in student["market_skill_bank"]
        if p["url"] == "https://example.org/legacy-metadata"
    )["skills"][0]
    assert skill["category"] == "programming"
    assert skill["job_metrics"] is None
    response = client.get(
        f"/courses/{o['course']['id']}/skill-banks", headers=teacher_auth_headers
    )
    assert response.status_code == 200, response.text
    skill = next(
        p
        for p in response.json()["market_skill_bank"]
        if p["url"] == "https://example.org/legacy-metadata"
    )["skills"][0]
    assert (
        skill["category"],
        skill["status"],
        skill["priority"],
        skill["demand_pct"],
    ) == ("programming", "uncovered", "high", 42.5)
    assert skill["job_metrics"] is None


def test_teacher_posting_dto_serializes_with_teacher_skill_type(db_session, offering):
    import json

    from app.modules.courses.curriculum_schemas import (
        MarketSkillBankJobPosting,
        MarketSkillBankSkill,
        SkillBanksResponse,
        SkillSelectionRange,
    )
    from app.modules.student_learning_path.skill_catalog_service import (
        SkillCatalogService,
    )

    o = offering
    publish(o)
    with o["driver"].session(database="neo4j") as session:
        result = SkillCatalogService(db_session, session).enrich_banks(
            o["course"]["id"],
            SkillBanksResponse(
                selection_range=SkillSelectionRange(
                    min_skills=1, max_skills=20, is_default=False
                )
            ),
        )
    posting = result.market_skill_bank[0]
    assert isinstance(posting, MarketSkillBankJobPosting)
    assert isinstance(posting.skills[0], MarketSkillBankSkill)
    payload = json.loads(result.model_dump_json(warnings="error"))
    assert (
        payload["market_skill_bank"][0]["skills"][0]["skill_reference_id"]
        == payload["career_skill_bank"][0]["skill_reference_id"]
    )


def test_career_remap_current_union_preserves_saved_path_chapters_and_recovery(
    client, db_session, teacher_auth_headers, offering, monkeypatch
):
    from app.modules.curricularalignmentarchitect.skill_prerequisites import (
        repository as prerequisites,
    )
    from app.modules.student_learning_path import neo4j_repository as student_graph
    from app.modules.student_learning_path import service as student_service
    from app.modules.student_learning_path.skill_catalog_service import (
        SkillCatalogService,
    )

    o = offering
    course, first = o["course"], o["run"]
    a, b = f"chapter-{course['id']}", f"chapter-b-{course['id']}"
    publish(o)
    ref = bank(client, o)["career_skill_bank"][0]["skill_reference_id"]
    assert select_id(client, o, [ref]).status_code == 200
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (course:CLASS {id:$course}) MERGE (b:COURSE_CHAPTER {id:$b}) SET b.title='Advanced', b.chapter_index=2 MERGE (course)-[:HAS_COURSE_CHAPTER]->(b)",
            course=course["id"],
            b=b,
        ).consume()
        session.run(
            "MATCH (a:COURSE_CHAPTER {id:$a}) MERGE (s:MARKET_SKILL:SKILL {name:'Independent legacy market'}) SET s.course_id=$course MERGE (s)-[:MAPPED_TO]->(a)",
            a=a,
            course=course["id"],
        ).consume()
        # Simulate a saved selection created before chapter snapshots existed.
        session.run(
            "MATCH (u:STUDENT {id:$student})-[choice:SELECTED_SKILL]->(s:CAREER_SKILL) REMOVE choice.chapter_ids SET choice.course_id=null "
            "MERGE (r:READING_RESOURCE {id:'remap-reading'}) SET r.url='https://example.org/retained', r.resource_type='article' MERGE (s)-[:HAS_READING]->(r) "
            "MERGE (q:QUESTION {id:'remap-question'}) SET q.text='Variables?',q.difficulty='easy',q.options=['a','b','c','d'],q.correct_option='A' MERGE (s)-[:HAS_QUESTION]->(q)",
            student=o["student"].id,
        ).consume()
        assert student_graph.submit_chapter_answers(
            session,
            o["student"].id,
            course["id"],
            1,
            [{"question_id": "remap-question", "selected_option": "A"}],
        )[0]["answered_right"]
    review = prepare(
        o["review_service"],
        course,
        o["revision"],
        o["candidates"],
        graph=graph_repo(o["driver"]),
        chapter_ids=[b],
    )
    approve_sql(o["review_service"], course, first, review, o["candidates"])
    assert o["projector"].project(course["id"], 2, run_id=first.id) == "projected"
    reference = db_session.get(CourseSkillReference, UUID(ref))
    assert [ch["chapter_id"] for ch in reference.chapters] == [b]
    rows = prerequisites.load_all_skills_for_course(o["driver"], course["id"])
    assert [
        row["chapter_title"]
        for row in rows
        if (row.get("target_identity") or "").startswith("career:")
    ] == ["Advanced"]
    with o["driver"].session(database="neo4j") as session:
        selected = SkillCatalogService(db_session, session).resolve(
            course["id"], ids=[ref]
        )
        session.run("MERGE (:USER:STUDENT {id:70002})").consume()
        student_graph.select_skill_targets(session, 70002, course["id"], selected)
        assert [
            row["chapter_index"]
            for row in student_graph.get_selected_skills(session, 70002, course["id"])
        ] == [2]
        assert [
            row["chapter_index"]
            for row in student_graph.get_selected_skills(
                session, o["student"].id, course["id"]
            )
        ] == [1]
        saved = student_graph.get_learning_path(session, o["student"].id, course["id"])
        assert saved["chapters"][0]["selected_skills"][0]["is_known"]
        assert (
            saved["chapters"][0]["selected_skills"][0]["readings"][0]["id"]
            == "remap-reading"
        )
        assert saved["chapters"][1]["selected_skills"] == []
        assert [
            question["id"]
            for question in student_graph.get_chapter_easy_questions(
                session, o["student"].id, course["id"], 1
            )["questions"]
        ] == ["remap-question"]
        assert (
            student_graph.get_chapter_easy_questions(session, 70002, course["id"], 1)[
                "questions"
            ]
            == []
        )
        assert [
            question["id"]
            for question in student_graph.get_chapter_easy_questions(
                session, 70002, course["id"], 2
            )["questions"]
        ] == ["remap-question"]
        assert (
            student_graph.get_chapter_easy_questions(
                session, o["student"].id, course["id"], 2
            )["questions"]
            == []
        )
        assert (
            student_graph.get_chapter_quiz_progress(
                session, o["student"].id, course["id"]
            )[0]["correct_count"]
            == 1
        )
        assert student_graph.get_accessible_reading_resource(
            session,
            student_id=o["student"].id,
            course_id=course["id"],
            resource_id="remap-reading",
        )
    _, second, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, course=course
    )
    second_review = prepare(
        service,
        course,
        revision,
        candidates,
        graph=graph_repo(o["driver"]),
        chapter_ids=[a],
    )
    approve_sql(service, course, second, second_review, candidates)
    assert o["projector"].project(course["id"], 1, run_id=second.id) == "projected"
    rows = prerequisites.load_all_skills_for_course(o["driver"], course["id"])
    assert sorted(
        row["chapter_title"]
        for row in rows
        if (row.get("target_identity") or "").startswith("career:")
    ) == ["Advanced", "Programming"]
    withdrawal = service.prepare_withdrawal_review(
        course["id"], course["teacher_id"], revision
    )
    approve_sql(service, course, second, withdrawal, [])
    assert o["projector"].project(course["id"], 2, run_id=second.id) == "projected"
    rows = prerequisites.load_all_skills_for_course(o["driver"], course["id"])
    assert [
        row["chapter_title"]
        for row in rows
        if (row.get("target_identity") or "").startswith("career:")
    ] == ["Advanced"]
    repo = MarketReviewRepository(db_session)
    repo.save_configuration_snapshot(
        service.thread_id(course["id"], course["teacher_id"]), {"run_id": str(first.id)}
    )
    repo.commit()
    withdrawal = o["review_service"].prepare_withdrawal_review(
        course["id"], course["teacher_id"], o["revision"]
    )
    approve_sql(o["review_service"], course, first, withdrawal, [])
    assert o["projector"].project(course["id"], 3, run_id=first.id) == "projected"
    with o["driver"].session(database="neo4j") as session:
        assert (
            len(
                student_graph.get_selected_skills(
                    session, o["student"].id, course["id"]
                )
            )
            == 1
        )
        assert len(student_graph.get_selected_skills(session, 70002, course["id"])) == 1
        assert (
            session.run(
                "MATCH (s:CAREER_SKILL)-[mapping:MAPPED_TO]->() WHERE mapping.current_for_new_selection=true RETURN count(mapping) AS n"
            ).single()["n"]
            == 0
        )
        assert (
            session.run(
                "MATCH (s:BOOK_SKILL)-[:MAPPED_TO]->(ch) RETURN ch.id AS id"
            ).single()["id"]
            == a
        )
        assert session.run(
            "MATCH (s:MARKET_SKILL {name:'Independent legacy market'})-[m:MAPPED_TO]->(ch) RETURN ch.id AS id,m.current_for_new_selection AS current"
        ).single().data() == {"id": a, "current": None}

    async def recovered(self, run_id, *args):
        student_service._active_runs.pop(run_id, None)

    monkeypatch.setattr(
        student_service.StudentLearningPathService, "_run_pipeline", recovered
    )
    response = client.post(
        f"/student-learning-path/{course['id']}/build", headers=o["headers"]
    )
    assert response.status_code == 202


def test_redaction_reconciles_current_chapters_without_moving_saved_selection(
    client, db_session, teacher_auth_headers, offering
):
    from app.modules.curricularalignmentarchitect.skill_prerequisites import (
        repository as prerequisites,
    )
    from app.modules.student_learning_path import neo4j_repository as student_graph

    o = offering
    course = o["course"]
    publish(o)
    ref = bank(client, o)["career_skill_bank"][0]["skill_reference_id"]
    assert select_id(client, o, [ref]).status_code == 200
    b = f"redaction-b-{course['id']}"
    with o["driver"].session(database="neo4j") as session:
        session.run(
            "MATCH (c:CLASS {id:$course}) MERGE (b:COURSE_CHAPTER {id:$b}) SET b.title='Surviving', b.chapter_index=2 MERGE (c)-[:HAS_COURSE_CHAPTER]->(b)",
            course=course["id"],
            b=b,
        ).consume()
    _, second, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, course=course
    )
    review = prepare(
        service,
        course,
        revision,
        candidates,
        graph=graph_repo(o["driver"]),
        chapter_ids=[b],
    )
    approve_sql(service, course, second, review, candidates)
    assert o["projector"].project(course["id"], 1, run_id=second.id) == "projected"
    repo = MarketReviewRepository(db_session)
    repo.purge_vacancy_content(
        o["candidates"][0]["evidence_references"][0]["snapshot_id"],
        reason="Remove first run evidence",
    )
    repo.commit()
    assert o["projector"].redact(course["id"]) == "projected"
    rows = prerequisites.load_all_skills_for_course(o["driver"], course["id"])
    assert [
        row["chapter_title"]
        for row in rows
        if (row.get("target_identity") or "").startswith("career:")
    ] == ["Surviving"]
    assert [
        ch["chapter_id"] for ch in bank(client, o)["career_skill_bank"][0]["chapters"]
    ] == [b]
    with o["driver"].session(database="neo4j") as session:
        assert [
            r["chapter_index"]
            for r in student_graph.get_selected_skills(
                session, o["student"].id, course["id"]
            )
        ] == [1]
