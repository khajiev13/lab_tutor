from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.core.database import get_db
from app.core.neo4j import require_neo4j_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from .repository import ConceptNormalizationRepository
from .review_sql_repository import ConceptNormalizationReviewSqlRepository
from .schemas import (
    ApplyReviewResponse,
    NormalizationReview,
    NormalizationStreamEvent,
    UpdateMergeDecisionsRequest,
    UpdateMergeDecisionsResponse,
)
from .service import ConceptNormalizationService, get_concept_normalization_service

router = APIRouter(prefix="/normalization", tags=["concept_normalization"])


def _sse_format(*, event: str, data: str) -> str:
    # SSE format requires a blank line separator between events.
    return f"event: {event}\ndata: {data}\n\n"


def _stream_events(
    *,
    service: ConceptNormalizationService,
    course_id: int,
    created_by_user_id: int | None,
) -> Iterator[str]:
    # Initial handshake event (helps UI show a connected state).
    yield _sse_format(
        event="update",
        data=json.dumps(
            NormalizationStreamEvent(
                type="update",
                iteration=0,
                phase="generation",
                agent_activity="Connected",
                concepts_count=0,
            ).model_dump()
        ),
    )

    for evt in service.normalize_concepts_stream(
        course_id=course_id, created_by_user_id=created_by_user_id
    ):
        yield _sse_format(event=evt.type, data=evt.model_dump_json())


@router.get("/stream", status_code=status.HTTP_200_OK)
def stream_normalization(
    course_id: int,
    db: Session = Depends(get_db),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    service = get_concept_normalization_service(neo4j_session=neo4j_session, db=db)
    return StreamingResponse(
        _stream_events(
            service=service, course_id=course_id, created_by_user_id=teacher.id
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/concepts", response_model=list[str], status_code=status.HTTP_200_OK)
def list_course_concepts(
    course_id: int,
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
) -> list[str]:
    repo = ConceptNormalizationRepository(neo4j_session)
    return [c["name"] for c in repo.list_concepts_for_course(course_id=course_id)]


@router.post("/stream", status_code=status.HTTP_200_OK)
def stream_normalization_post(
    course_id: int,
    db: Session = Depends(get_db),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    # EventSource uses GET, but POST is provided for compatibility with the plan.
    service = get_concept_normalization_service(neo4j_session=neo4j_session, db=db)
    return StreamingResponse(
        _stream_events(
            service=service, course_id=course_id, created_by_user_id=teacher.id
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(
    "/reviews/{review_id}",
    response_model=NormalizationReview,
    status_code=status.HTTP_200_OK,
)
def get_normalization_review(
    review_id: str,
    course_id: int,
    db: Session = Depends(get_db),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
) -> NormalizationReview:
    sql_repo = ConceptNormalizationReviewSqlRepository(db)
    review = sql_repo.get_review(review_id=review_id, course_id=course_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )

    repo = ConceptNormalizationRepository(neo4j_session)
    concept_names: set[str] = set()
    for p in review.proposals:
        concept_names.update([p.concept_a, p.concept_b, p.canonical])

    review.definitions = repo.get_concept_definitions_for_course(
        names=sorted(concept_names), course_id=course_id
    )
    return review


@router.post(
    "/reviews/{review_id}/decisions",
    response_model=UpdateMergeDecisionsResponse,
    status_code=status.HTTP_200_OK,
)
def update_normalization_review_decisions(
    review_id: str,
    course_id: int,
    payload: UpdateMergeDecisionsRequest,
    db: Session = Depends(get_db),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
) -> UpdateMergeDecisionsResponse:
    sql_repo = ConceptNormalizationReviewSqlRepository(db)
    review = sql_repo.get_review(review_id=review_id, course_id=course_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )

    decisions = [
        {
            "proposal_id": d.proposal_id,
            "decision": d.decision.value,
            "comment": d.comment,
        }
        for d in payload.decisions
    ]
    updated = sql_repo.update_decisions(
        review_id=review_id,
        course_id=course_id,
        user_id=teacher.id,
        decisions=decisions,
    )
    return UpdateMergeDecisionsResponse(review_id=review_id, updated=updated)


@router.post(
    "/reviews/{review_id}/apply",
    response_model=ApplyReviewResponse,
    status_code=status.HTTP_200_OK,
)
def apply_normalization_review(
    review_id: str,
    course_id: int,
    db: Session = Depends(get_db),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
) -> ApplyReviewResponse:
    sql_repo = ConceptNormalizationReviewSqlRepository(db)
    review = sql_repo.get_review(review_id=review_id, course_id=course_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )

    approved = sql_repo.list_approved_proposals(review_id=review_id, course_id=course_id)
    total_approved = len(approved)

    graph_repo = ConceptNormalizationRepository(neo4j_session)
    applied = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    for row in approved:
        proposal_id = str(row.get("proposal_id") or "")
        canonical = str(row.get("canonical") or "")
        variants = row.get("variants") or []
        variants_list = [str(v) for v in variants if isinstance(v, str) and v]

        try:
            merged_flag = graph_repo.merge_concepts(
                canonical=canonical, variants=variants_list
            )
            if merged_flag:
                applied += 1
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            errors.append(f"{proposal_id}: {e}")

    # Delete staged rows only after fully successful apply.
    if failed == 0:
        sql_repo.delete_review(review_id=review_id, course_id=course_id)

    return ApplyReviewResponse(
        review_id=review_id,
        total_approved=total_approved,
        applied=applied,
        skipped=skipped,
        failed=failed,
        errors=errors,
    )
