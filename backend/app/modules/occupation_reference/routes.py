from fastapi import APIRouter, Depends, HTTPException, Query

from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.marketdemandanalyst.schemas import SkillReview
from app.modules.marketdemandanalyst.thread_state_service import (
    ThreadBusy,
    ThreadStateService,
    get_thread_state_service,
)

from .schemas import (
    OccupationSearch,
    OccupationSelection,
    OccupationSkills,
    ReleaseList,
    ReleaseVersion,
    SocCode,
)
from .service import OccupationReferenceService, get_occupation_reference_service

router = APIRouter(prefix="/courses", tags=["occupation-reference"])


@router.get("/{course_id}/occupation-reference/releases", response_model=ReleaseList)
def list_releases(
    course_id: int,
    teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: OccupationReferenceService = Depends(get_occupation_reference_service),
):
    return service.list_releases(course_id, teacher.id)


@router.get(
    "/{course_id}/occupation-reference/occupations", response_model=OccupationSearch
)
def search_occupations(
    course_id: int,
    q: str = Query(min_length=2, max_length=120),
    release: ReleaseVersion | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: OccupationReferenceService = Depends(get_occupation_reference_service),
):
    return service.search_occupations(course_id, teacher.id, release, q, offset, limit)


@router.get(
    "/{course_id}/occupation-reference/occupations/{soc_code}/skills",
    response_model=OccupationSkills,
)
def get_occupation_skills(
    course_id: int,
    soc_code: SocCode,
    release: ReleaseVersion | None = None,
    teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: OccupationReferenceService = Depends(get_occupation_reference_service),
):
    return service.get_occupation_skills(course_id, teacher.id, release, soc_code)


@router.post("/{course_id}/market-demand/occupations", response_model=SkillReview)
async def confirm_occupations(
    course_id: int,
    body: OccupationSelection,
    teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: OccupationReferenceService = Depends(get_occupation_reference_service),
    state_service: ThreadStateService = Depends(get_thread_state_service),
):
    service.require_teacher(course_id, teacher.id)
    thread_id = f"mda-{teacher.id}-course-{course_id}"
    try:
        lease = await state_service.claim(thread_id)
    except ThreadBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    try:
        persisted = await state_service.load(thread_id) or {}
        if persisted.get("run_id") != str(body.run_id):
            raise HTTPException(
                409, "Occupation selection must belong to the active analysis"
            )
        review, confirmation = service.confirm_occupations(course_id, teacher.id, body)
        service.save_confirmation_snapshot(
            thread_id,
            body.run_id,
            {
                **persisted,
                **confirmation,
                "selected_onet_occupations": body.soc_codes,
                "run_id": str(review.run_id),
                "candidate_revision": review.candidate_revision,
            },
        )
        service.commit()
        return review
    except BaseException:
        service.rollback()
        raise
    finally:
        await state_service.release(lease)
