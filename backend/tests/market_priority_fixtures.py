"""Real saved job passages and reference data for priority assessment tests."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.marketdemandanalyst import schemas
from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState
from app.modules.marketdemandanalyst.repository import MarketReviewRepository
from app.modules.occupation_reference.models import (
    OnetEvidence,
    OnetOccupation,
    OnetRelease,
)
from tests.market_skill_fixtures import seed_review


def seed_priority_case(db_session, client, headers, *, skill_count: int = 5):
    course, run, candidates, service, revision = seed_review(
        db_session,
        client,
        headers,
        labels=tuple(f"Competency {i + 1}" for i in range(skill_count)),
    )
    repo = MarketReviewRepository(db_session)
    snapshots = repo.vacancy_evidence(run)
    jobs = []
    for candidate in candidates:
        ref = candidate["evidence_references"][0]
        snapshot = snapshots[ref["snapshot_id"]]
        ref.update(
            evidence_kind="extracted_text",
            excerpt=snapshot.description_text,
            excerpt_start=0,
            excerpt_end=len(snapshot.description_text),
        )
        jobs.append({"snapshot_id": str(snapshot.id), "title": snapshot.title})
    run.candidate_manifest = {
        **deepcopy(run.candidate_manifest),
        "candidates": candidates,
        "categories": [{"category_id": "programming", "label": "Programming"}],
    }
    run.config = {**run.config, "onet_release": "31.0"}
    thread_id = service.thread_id(course["id"], course["teacher_id"])
    thread = db_session.get(MDAThreadState, thread_id)
    thread.state_json = {
        **thread.state_json,
        "selected_jobs": jobs,
        "fetched_jobs": jobs,
        "job_groups": {"Developer": list(range(len(jobs)))},
    }
    release = OnetRelease(version="31.0", active=True, manifest={}, attribution="O*NET")
    db_session.add(release)
    db_session.flush()
    db_session.add(
        OnetOccupation(
            release="31.0",
            soc_code="15-1252.00",
            title="Software Developers",
            description="Develop software.",
        )
    )
    db_session.flush()
    reference_id = uuid4()
    db_session.add(
        OnetEvidence(
            id=reference_id,
            release="31.0",
            soc_code="15-1252.00",
            family="essential",
            element_id="2.B.3.e",
            label="Programming",
            definition="Writing computer programs.",
            ratings={"IM": {"value": 4.5, "status": "reported"}},
            flags={},
            source_rows=[],
            source_key="priority-programming",
        )
    )
    db_session.commit()
    selected = candidates[:-1] if len(candidates) > 1 else candidates
    excluded = candidates[-1:] if len(candidates) > 1 else []
    repo.save_draft(
        run.id,
        course["id"],
        course["teacher_id"],
        expected_candidate_revision=run.candidate_revision,
        expected_selection_revision=run.selection_revision,
        selected_candidate_ids=[c["candidate_id"] for c in selected],
        excluded_candidate_ids=[c["candidate_id"] for c in excluded],
    )
    db_session.commit()
    revision = schemas.SkillReviewRevision(
        run_id=run.id,
        expected_candidate_revision=run.candidate_revision,
        expected_selection_revision=run.selection_revision,
    )
    service.confirm_selection(course["id"], course["teacher_id"], revision)
    scope = schemas.PriorityScope(
        run_id=run.id,
        course_id=course["id"],
        teacher_id=course["teacher_id"],
        expected_candidate_revision=run.candidate_revision,
    )
    now = datetime.now(UTC)
    assessment = schemas.PriorityAssessment(
        assessment_id=uuid4(),
        run_id=run.id,
        candidate_revision=run.candidate_revision,
        input_fingerprint="test-fingerprint",
        model_id="test-model",
        release="31.0",
        started_at=now,
        updated_at=now,
        deadline_at=now + timedelta(seconds=60),
        status="running",
        posting_hashes={key: item.content_hash for key, item in snapshots.items()},
    )
    engine = db_session.get_bind()

    def reload():
        with Session(bind=engine) as fresh:
            return fresh.get(MarketAnalysisRun, scope.run_id)

    def teacher_decisions():
        restored = reload()
        return {
            "selected": restored.selected_candidate_ids,
            "excluded": restored.excluded_candidate_ids,
            "candidate_revision": restored.candidate_revision,
            "selection_revision": restored.selection_revision,
            "publication_revision": restored.publication_revision,
            "manifest": restored.candidate_manifest,
            "confirmation": restored.selection_confirmation,
        }

    return SimpleNamespace(
        course=course,
        run=run,
        candidates=candidates,
        snapshots=snapshots,
        repo=repo,
        scope=scope,
        assessment=assessment,
        reference_id=reference_id,
        thread_id=thread_id,
        reload=reload,
        teacher_decisions=teacher_decisions,
        before=teacher_decisions(),
        revision=revision,
        service=service,
        engine=engine,
    )
