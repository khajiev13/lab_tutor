"""Final approval must qualify every candidate and target, atomically in SQL."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from tests.market_skill_fixtures import prepare, seed_review


def approve(client, headers, course, run, review, ids):
    return client.post(
        f"/courses/{course['id']}/market-demand/integration-approval",
        headers=headers,
        json={
            "run_id": str(run.id),
            "expected_candidate_revision": run.candidate_revision,
            "expected_selection_revision": run.selection_revision,
            "review_digest": review.integration_review["review_digest"],
            "approved_candidate_ids": ids,
        },
    )


def test_broader_tag_cannot_publish_specific_candidate_or_equal_named_target(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, labels=("Python machine learning",)
    )
    candidate = candidates[0]
    snapshot = db_session.get(
        MarketVacancySnapshot, candidate["evidence_references"][0]["snapshot_id"]
    )
    snapshot.skill_tags = ["Python"]
    candidate["evidence_references"][0]["original_phrase"] = "Python"
    run.candidate_manifest = {
        **deepcopy(run.candidate_manifest),
        "candidates": candidates,
    }
    db_session.commit()
    review = prepare(service, course, revision, candidates)
    response = approve(
        client, teacher_auth_headers, course, run, review, [candidate["candidate_id"]]
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "missing_job_evidence"
    db_session.refresh(run)
    assert run.publication_revision == 0


def test_server_validated_action_extraction_supports_candidate_and_target(
    db_session, client, teacher_auth_headers
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot
    from app.modules.marketdemandanalyst.schemas import SkillReviewRevision
    from app.modules.marketdemandanalyst.service import MarketSourceService

    course, run, candidates, service, _ = seed_review(
        db_session, client, teacher_auth_headers, labels=("Explain technical results",)
    )
    candidate = candidates[0]
    snapshot = db_session.get(
        MarketVacancySnapshot, candidate["evidence_references"][0]["snapshot_id"]
    )
    quote = "You must explain results to colleagues."
    snapshot.description_text = quote
    snapshot.original_description = quote
    snapshot.skill_tags = []
    ref = {
        **candidate["evidence_references"][0],
        "original_phrase": "explain results",
        "evidence_kind": "extracted_text",
        "excerpt": quote,
        "excerpt_start": 0,
        "excerpt_end": len(quote),
    }
    demand_identity = snapshot.demand_identity
    db_session.commit()
    source = MarketSourceService(
        session_factory=lambda: Session(bind=db_session.get_bind())
    )
    result = source.save_extraction(
        {
            "run_id": str(run.id),
            "course_id": course["id"],
            "teacher_id": course["teacher_id"],
        },
        [
            {
                "name": candidate["display_name"],
                "category": candidate["category_id"],
                "identity_key": candidate["identity_key"],
                "evidence_references": [ref],
            }
        ],
        [
            {
                "demand_identity": demand_identity,
                "assessed_chunks": 1,
                "total_chunks": 1,
                "status": "full",
                "warnings": [],
            }
        ],
    )
    db_session.expire_all()
    db_session.refresh(run)
    revision = SkillReviewRevision(
        run_id=run.id,
        expected_candidate_revision=run.candidate_revision,
        expected_selection_revision=run.selection_revision,
    )
    service.confirm_selection(course["id"], course["teacher_id"], revision)
    review = prepare(service, course, revision, result["candidates"])
    response = approve(
        client, teacher_auth_headers, course, run, review, [candidate["candidate_id"]]
    )
    assert response.status_code == 200, response.text
    assert response.json()["review"]["approved_references"][0][
        "qualifying_posting_links"
    ] == [ref["original_url"]]


@pytest.mark.parametrize("mixed", [False, True])
def test_job_backed_approval_is_sql_durable_even_without_graph(
    db_session, client, teacher_auth_headers, mixed
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, mixed=mixed
    )
    review = prepare(service, course, revision, candidates)
    response = approve(
        client,
        teacher_auth_headers,
        course,
        run,
        review,
        [c["candidate_id"] for c in candidates],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["projection_status"] in {"pending", "error"}
    assert data["review"]["publication_revision"] == 1
    refs = data["review"]["approved_references"]
    assert len(refs) == 1
    assert refs[0]["qualifying_posting_links"] == [
        candidates[0]["evidence_references"][0]["original_url"]
    ]
    from app.modules.marketdemandanalyst.models import (
        CourseSkillEvidence,
        CourseSkillReference,
    )

    assert (
        db_session.scalar(select(func.count()).select_from(CourseSkillReference)) == 1
    )
    assert db_session.scalar(select(func.count()).select_from(CourseSkillEvidence)) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "onet_only",
        "partial",
        "homepage",
        "foreign_run",
        "unselected_provider",
        "invalid_passage",
        "merged_neighbor",
        "covered_neighbor",
    ],
)
def test_unsupported_batch_rejected_without_partial_publication(
    db_session, client, teacher_auth_headers, mutation
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, labels=("Python", "SQL")
    )
    bad = deepcopy(run.candidate_manifest)
    target = bad["candidates"][1]
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot

    snapshot = db_session.get(
        MarketVacancySnapshot, target["evidence_references"][0]["snapshot_id"]
    )
    if mutation in {"onet_only", "partial"}:
        target["evidence_references"] = []
    elif mutation == "homepage":
        snapshot.original_url = "https://hh.uz/"
        target["evidence_references"][0]["original_url"] = snapshot.original_url
    elif mutation == "foreign_run":
        # Foreign existing run supplies genuine evidence, but never qualifies here.
        from app.modules.marketdemandanalyst.repository import MarketReviewRepository

        other = MarketReviewRepository(db_session).create_run(
            course["id"], course["teacher_id"], {"sources": ["headhunter"]}
        )
        snapshot.run_id = other.id
    elif mutation == "unselected_provider":
        snapshot.provider = "linkedin"
    elif mutation == "invalid_passage":
        target["evidence_references"][0].update(
            evidence_kind="extracted_text",
            excerpt="SQL",
            excerpt_start=0,
            excerpt_end=3,
        )
    elif mutation == "merged_neighbor":
        target["evidence_references"] = deepcopy(
            bad["candidates"][0]["evidence_references"]
        )
    run.candidate_manifest = bad
    db_session.commit()
    overrides = (
        {
            "disposition": "covered",
            "target_label": "Java",
            "source": "book",
            "origin": "book",
        }
        if mutation == "covered_neighbor"
        else {}
    )
    review = prepare(service, course, revision, candidates, **overrides)
    response = approve(
        client,
        teacher_auth_headers,
        course,
        run,
        review,
        [c["candidate_id"] for c in candidates],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "missing_job_evidence"
    assert candidates[1]["candidate_id"] in response.json()["detail"]["candidate_ids"]
    db_session.refresh(run)
    assert run.publication_revision == 0 and run.approved_references == []
    from app.modules.marketdemandanalyst.models import CourseSkillReference

    assert (
        db_session.scalar(select(func.count()).select_from(CourseSkillReference)) == 0
    )


def test_archived_posting_and_all_covered_candidates_still_approve(
    db_session, client, teacher_auth_headers
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot

    snapshot = db_session.get(
        MarketVacancySnapshot, candidates[0]["evidence_references"][0]["snapshot_id"]
    )
    snapshot.status = "archived"
    db_session.commit()
    review = prepare(
        service,
        course,
        revision,
        candidates,
        disposition="covered",
        source="book",
        origin="book",
        target_identity="book:existing",
    )
    assert len(review.integration_review["items"]) == 1
    response = approve(
        client,
        teacher_auth_headers,
        course,
        run,
        review,
        [candidates[0]["candidate_id"]],
    )
    assert response.status_code == 200, response.text
    assert response.json()["review"]["approved_references"][0]["source"] == "book"


def test_evidence_change_invalidates_digest_without_revision_change(
    db_session, client, teacher_auth_headers
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    review = prepare(service, course, revision, candidates)
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot

    snapshot = db_session.get(
        MarketVacancySnapshot, candidates[0]["evidence_references"][0]["snapshot_id"]
    )
    snapshot.skill_tags = []
    db_session.commit()
    response = approve(
        client,
        teacher_auth_headers,
        course,
        run,
        review,
        [candidates[0]["candidate_id"]],
    )
    assert response.status_code == 409, response.text
    db_session.refresh(run)
    assert run.publication_revision == 0


def test_withdrawal_has_explicit_server_digest_and_preserves_draft_and_evidence(
    db_session, client, teacher_auth_headers
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    review = prepare(service, course, revision, candidates)
    response = approve(
        client,
        teacher_auth_headers,
        course,
        run,
        review,
        [candidates[0]["candidate_id"]],
    )
    assert response.status_code == 200
    reference_id = response.json()["review"]["approved_references"][0]["reference_id"]
    from app.modules.marketdemandanalyst.models import CourseSkillEvidence
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    MarketReviewRepository(db_session).purge_vacancy_content(
        candidates[0]["evidence_references"][0]["snapshot_id"],
        reason="Provider removal",
    )
    db_session.commit()
    response = client.post(
        f"/courses/{course['id']}/market-demand/skill-review/withdrawal-review",
        headers=teacher_auth_headers,
        json=revision.model_dump(mode="json"),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert (
        data["integration_review"]["withdrawal"] is True
        and data["integration_review"]["items"] == []
    )
    assert data["selected_candidate_ids"] == [candidates[0]["candidate_id"]]
    from app.modules.marketdemandanalyst.schemas import SkillReview

    withdrawn = approve(
        client, teacher_auth_headers, course, run, SkillReview.model_validate(data), []
    )
    assert withdrawn.status_code == 200, withdrawn.text
    from app.modules.marketdemandanalyst.models import CourseSkillReference

    ref = db_session.get(CourseSkillReference, reference_id)
    db_session.refresh(ref)
    assert not ref.available_for_new_selection
    assert db_session.scalar(select(func.count()).select_from(CourseSkillEvidence)) == 1


def test_initial_empty_approval_and_foreign_candidate_rejected(
    db_session, client, teacher_auth_headers
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    review = prepare(service, course, revision, candidates)
    for ids in ([], [str(uuid4())]):
        response = approve(client, teacher_auth_headers, course, run, review, ids)
        assert response.status_code == 422, response.text
    with pytest.raises(HTTPException) as exc:
        service.prepare_withdrawal_review(course["id"], course["teacher_id"], revision)
    assert exc.value.status_code == 422


@pytest.mark.parametrize("source_shape", ["neither", "both"])
def test_evidence_database_requires_exactly_one_source_fk(
    db_session, client, teacher_auth_headers, source_shape
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    review = prepare(service, course, revision, candidates)
    assert (
        approve(
            client,
            teacher_auth_headers,
            course,
            run,
            review,
            [candidates[0]["candidate_id"]],
        ).status_code
        == 200
    )
    from sqlalchemy.exc import IntegrityError

    from app.modules.marketdemandanalyst.models import CourseSkillEvidence

    binding = db_session.scalar(select(CourseSkillEvidence))
    binding.onet_evidence_id = (
        binding.vacancy_snapshot_id if source_shape == "both" else None
    )
    if source_shape == "neither":
        binding.vacancy_snapshot_id = None
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert exc.value.orig.diag.constraint_name == "ck_course_skill_evidence_source"
    db_session.rollback()


def test_course_reference_composite_fk_refuses_foreign_course_binding(
    db_session, client, teacher_auth_headers
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    review = prepare(service, course, revision, candidates)
    assert (
        approve(
            client,
            teacher_auth_headers,
            course,
            run,
            review,
            [candidates[0]["candidate_id"]],
        ).status_code
        == 200
    )
    response = client.post(
        "/courses", json={"title": "Other binding course"}, headers=teacher_auth_headers
    )
    assert response.status_code == 201
    from sqlalchemy.exc import IntegrityError

    from app.modules.marketdemandanalyst.models import CourseSkillEvidence

    binding = db_session.scalar(select(CourseSkillEvidence))
    binding.course_id = response.json()["id"]
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert exc.value.orig.diag.constraint_name == "fk_course_skill_evidence_reference"
    db_session.rollback()


def test_mixed_approval_keeps_official_onet_data_separate_from_job_support(
    db_session, client, teacher_auth_headers
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, mixed=True
    )
    from app.modules.occupation_reference.models import (
        OnetEvidence,
        OnetOccupation,
        OnetRelease,
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
        family="software",
        element_id="2.C.3.a",
        label="Development environment software",
        definition="Development tools",
        workplace_example="Python",
        ratings={},
        flags={"hot_technology": True},
        source_rows=[{"Technology Example": "Python"}],
        source_key="python",
    )
    db_session.add(release)
    db_session.flush()
    db_session.add(occupation)
    db_session.flush()
    db_session.add(evidence)
    db_session.flush()
    manifest = deepcopy(run.candidate_manifest)
    manifest["candidates"][0]["onet_associations"] = [
        {
            "relation": "broader",
            "mapping_method": "reference_context",
            "rationale": "Original descriptor remains context",
            "evidence": {
                "id": str(evidence.id),
                "release": "31.0",
                "soc_code": "15-1252.00",
                "occupation_title": "Software Developers",
                "family": "software",
                "element_id": "2.C.3.a",
                "label": evidence.label,
                "definition": evidence.definition,
                "workplace_example": "Python",
                "ratings": {},
                "flags": {"hot_technology": True},
                "source_url": "https://www.onetonline.org/link/summary/15-1252.00",
                "attribution": "O*NET 31.0 attribution",
            },
        }
    ]
    run.candidate_manifest = manifest
    run.config = {
        **run.config,
        "onet_release": "31.0",
        "selected_onet_occupations": [{"soc_code": "15-1252.00"}],
    }
    db_session.commit()
    review = prepare(service, course, revision, candidates)
    response = approve(
        client,
        teacher_auth_headers,
        course,
        run,
        review,
        [candidates[0]["candidate_id"]],
    )
    assert response.status_code == 200, response.text
    from app.modules.marketdemandanalyst.models import CourseSkillEvidence

    bindings = list(db_session.scalars(select(CourseSkillEvidence)))
    assert len(bindings) == 2
    assert sum(b.vacancy_snapshot_id is not None for b in bindings) == 1
    contextual = next(b for b in bindings if b.onet_evidence_id is not None)
    assert (
        contextual.mapping_relation == "broader"
        and contextual.provenance["evidence"]["ratings"] == {}
    )
    db_session.refresh(evidence)
    assert evidence.source_rows == [
        {"Technology Example": "Python"}
    ] and evidence.flags == {"hot_technology": True}


def test_failed_snapshot_write_rolls_back_entire_approval(
    db_session, client, teacher_auth_headers
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    review = prepare(service, course, revision, candidates)
    from sqlalchemy import event

    def reject_snapshot(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE mda_thread_state"):
            raise RuntimeError("Injected approval snapshot failure")

    event.listen(db_session.get_bind(), "before_cursor_execute", reject_snapshot)
    try:
        with pytest.raises(RuntimeError, match="Injected approval"):
            approve(
                client,
                teacher_auth_headers,
                course,
                run,
                review,
                [candidates[0]["candidate_id"]],
            )
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", reject_snapshot)
    db_session.refresh(run)
    assert run.publication_revision == 0 and run.approved_references == []
    from app.modules.marketdemandanalyst.models import CourseSkillReference

    assert (
        db_session.scalar(select(func.count()).select_from(CourseSkillReference)) == 0
    )


def test_reference_reused_across_runs_and_withdrawal_preserves_other_offering(
    db_session, client, teacher_auth_headers
):
    course, first, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    review = prepare(
        service, course, revision, candidates, target_identity="career:stable-target"
    )
    response = approve(
        client,
        teacher_auth_headers,
        course,
        first,
        review,
        [candidates[0]["candidate_id"]],
    )
    assert response.status_code == 200
    reference_id = response.json()["review"]["approved_references"][0]["reference_id"]
    _, second, new_candidates, new_service, new_revision = seed_review(
        db_session, client, teacher_auth_headers, course=course
    )
    next_review = prepare(
        new_service,
        course,
        new_revision,
        new_candidates,
        target_identity="career:stable-target",
    )
    response = approve(
        client,
        teacher_auth_headers,
        course,
        second,
        next_review,
        [new_candidates[0]["candidate_id"]],
    )
    assert response.status_code == 200
    assert (
        response.json()["review"]["approved_references"][0]["reference_id"]
        == reference_id
    )
    from app.modules.marketdemandanalyst.models import (
        CourseSkillEvidence,
        CourseSkillReference,
        MarketSkillApproval,
    )

    assert (
        db_session.scalar(select(func.count()).select_from(CourseSkillReference)) == 1
    )
    assert db_session.scalar(select(func.count()).select_from(CourseSkillEvidence)) == 2
    withdrawal = new_service.prepare_withdrawal_review(
        course["id"], course["teacher_id"], new_revision
    )
    response = approve(client, teacher_auth_headers, course, second, withdrawal, [])
    assert (
        response.status_code == 200
        and response.json()["review"]["approved_references"] == []
    )
    active = list(
        db_session.scalars(
            select(MarketSkillApproval).where(MarketSkillApproval.is_active.is_(True))
        )
    )
    assert len(active) == 2 and any(
        row.run_id == first.id and row.items for row in active
    )
    assert db_session.scalar(select(func.count()).select_from(CourseSkillEvidence)) == 2


def test_retrying_identical_approval_is_idempotent(
    db_session, client, teacher_auth_headers
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    review = prepare(service, course, revision, candidates)
    for _ in range(2):
        response = approve(
            client,
            teacher_auth_headers,
            course,
            run,
            review,
            [candidates[0]["candidate_id"]],
        )
        assert response.status_code == 200, response.text
        assert response.json()["review"]["publication_revision"] == 1
    from app.modules.marketdemandanalyst.models import CourseSkillEvidence

    assert db_session.scalar(select(func.count()).select_from(CourseSkillEvidence)) == 1


def test_public_review_exposes_digest_bound_concepts(
    db_session, client, teacher_auth_headers
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    concepts = [{"name": "Python expressions", "description": None}]
    review = prepare(service, course, revision, candidates, concepts=concepts)
    assert review.integration_review["items"][0]["concepts"] == concepts
    response = client.get(
        f"/courses/{course['id']}/market-demand/skill-review",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["integration_review"]["items"][0]["concepts"] == concepts
    altered = deepcopy(run.integration_review)
    altered["_proposals"][0]["concepts"][0]["name"] = "Changed concept"
    run.integration_review = altered
    db_session.commit()
    response = approve(
        client,
        teacher_auth_headers,
        course,
        run,
        review,
        [candidates[0]["candidate_id"]],
    )
    assert response.status_code == 409
