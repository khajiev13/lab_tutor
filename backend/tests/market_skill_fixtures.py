"""Real SQL fixtures; graph doubles are confined to approval-only tests."""

from uuid import uuid4

from app.modules.marketdemandanalyst.repository import MarketReviewRepository
from app.modules.marketdemandanalyst.review_service import SkillReviewService
from app.modules.marketdemandanalyst.schemas import ProviderVacancy, SkillReviewRevision


class ReviewedTargets:
    def resolve_targets(self, course_id, proposals):
        return [
            {
                **proposal,
                "target": {
                    "identity": proposal.get(
                        "target_identity", f"new:{proposal['candidate_id']}"
                    ),
                    "label": proposal.get("target_label", proposal["name"]),
                    "source": proposal.get("source", "market"),
                    "origin": proposal.get("origin", "market_demand"),
                },
                "chapters": [{"chapter_id": "chapter-1", "title": "Programming"}],
            }
            for proposal in proposals
        ]


def seed_review(
    db,
    client,
    headers,
    *,
    labels=("Python",),
    mixed=False,
    title="Approval course",
    course=None,
):
    if course is None:
        response = client.post("/courses", json={"title": title}, headers=headers)
        assert response.status_code == 201
        course = response.json()
    repo = MarketReviewRepository(db)
    run = repo.create_run(
        course["id"],
        course["teacher_id"],
        {
            "sources": ["headhunter"],
            "evidence_sources": ["jobs", "onet"] if mixed else ["jobs"],
        },
    )
    candidates = []
    for label in labels:
        snapshot = repo.upsert_vacancy_snapshot(
            run.id,
            ProviderVacancy(
                provider="headhunter",
                native_id=str(uuid4()),
                title="Developer",
                original_url=f"https://hh.uz/vacancy/{uuid4().int}",
                original_description=f"Required: {label}.",
                description_text=f"Required: {label}.",
                skill_tags=[label],
                raw_payload={"key_skills": [{"name": label}]},
            ),
        )
        candidates.append(
            {
                "candidate_id": str(uuid4()),
                "display_name": label,
                "category_id": "programming",
                "identity_key": f"jobs:{label}",
                "original_labels": [label],
                "evidence_references": [
                    {
                        "snapshot_id": str(snapshot.id),
                        "provider": "headhunter",
                        "original_url": snapshot.original_url,
                        "original_phrase": label,
                        "evidence_kind": "provider_tag",
                        "excerpt": None,
                        "excerpt_start": None,
                        "excerpt_end": None,
                        "retrieved_at": snapshot.retrieved_at.isoformat(),
                        "status": snapshot.status,
                    }
                ],
                "job_metrics": {
                    "supporting_posting_count": 1,
                    "assessed_posting_count": 1,
                    "selected_posting_count": 1,
                    "percentage": 100.0,
                    "coverage_status": "full",
                },
            }
        )
    repo.update_manifest(
        run.id,
        course["id"],
        course["teacher_id"],
        expected_candidate_revision=0,
        candidates=candidates,
    )
    repo.save_draft(
        run.id,
        course["id"],
        course["teacher_id"],
        expected_candidate_revision=1,
        expected_selection_revision=0,
        selected_candidate_ids=[c["candidate_id"] for c in candidates],
        excluded_candidate_ids=[],
    )
    repo.save_configuration_snapshot(
        SkillReviewService.thread_id(course["id"], course["teacher_id"]),
        {"run_id": str(run.id)},
    )
    repo.commit()
    service = SkillReviewService(repo)
    revision = SkillReviewRevision(
        run_id=run.id, expected_candidate_revision=1, expected_selection_revision=1
    )
    service.confirm_selection(course["id"], course["teacher_id"], revision)
    return course, run, candidates, service, revision


def prepare(service, course, revision, candidates, *, graph=None, **overrides):
    proposals = [
        {
            "candidate_id": c["candidate_id"],
            "name": c["display_name"],
            "disposition": "new",
            "chapter_ids": ["chapter-1"],
            "concepts": [],
            **overrides,
        }
        for c in candidates
    ]
    return service.prepare_integration_review(
        course["id"],
        course["teacher_id"],
        revision,
        proposals,
        graph=graph or ReviewedTargets(),
    )
