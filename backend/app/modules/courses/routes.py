from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
from fastapi.responses import StreamingResponse

from app.modules.auth.dependencies import (
    current_active_user,
    require_role,
)
from app.modules.auth.models import User, UserRole
from app.modules.embeddings.schemas import CourseEmbeddingStatusResponse

from .curriculum_schemas import CurriculumWithChangelog, SkillBanksResponse
from .curriculum_service import CurriculumService, get_curriculum_service
from .schemas import (
    CourseCreate,
    CourseFileRead,
    CourseRead,
    EnrollmentRead,
    StartExtractionResponse,
    UploadPresentationsResponse,
)
from .service import CourseService, get_course_service

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(
    course_in: CourseCreate,
    service: CourseService = Depends(get_course_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return service.create_course(course_in, teacher)


@router.get("", response_model=list[CourseRead])
def list_courses(service: CourseService = Depends(get_course_service)):
    return service.list_courses()


@router.get("/my", response_model=list[CourseRead])
def list_my_courses(
    service: CourseService = Depends(get_course_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return service.list_teacher_courses(teacher)


@router.get("/enrolled", response_model=list[CourseRead])
def list_enrolled_courses(
    service: CourseService = Depends(get_course_service),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    return service.list_enrolled_courses(student)


@router.get("/{course_id}", response_model=CourseRead)
def get_course(
    course_id: int,
    service: CourseService = Depends(get_course_service),
    current_user: User = Depends(current_active_user),
):
    return service.get_course(course_id)


@router.post(
    "/{course_id}/join",
    response_model=EnrollmentRead,
    status_code=status.HTTP_201_CREATED,
)
def join_course(
    course_id: int,
    service: CourseService = Depends(get_course_service),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    return service.join_course(course_id, student)


@router.delete("/{course_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_course(
    course_id: int,
    service: CourseService = Depends(get_course_service),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    service.leave_course(course_id, student)


@router.get("/{course_id}/enrollment", response_model=EnrollmentRead | None)
def get_enrollment(
    course_id: int,
    service: CourseService = Depends(get_course_service),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    return service.get_enrollment(course_id, student)


@router.put("/{course_id}", response_model=CourseRead)
def update_course(
    course_id: int,
    course_update: CourseCreate,
    service: CourseService = Depends(get_course_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return service.update_course(course_id, course_update, teacher)


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: int,
    service: CourseService = Depends(get_course_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    service.delete_course(course_id, teacher)


@router.post(
    "/{course_id}/presentations",
    response_model=UploadPresentationsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_presentations(
    course_id: int,
    files: list[UploadFile] = File(...),
    service: CourseService = Depends(get_course_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    uploaded_urls = await service.upload_presentations(course_id, files, teacher)
    return UploadPresentationsResponse(uploaded_files=uploaded_urls)


@router.get("/{course_id}/presentations", response_model=list[str])
async def list_presentations(
    course_id: int,
    service: CourseService = Depends(get_course_service),
    current_user: User = Depends(current_active_user),
):
    return await service.list_presentations(course_id)


@router.get("/{course_id}/presentations/status", response_model=list[CourseFileRead])
def list_presentation_statuses(
    course_id: int,
    service: CourseService = Depends(get_course_service),
    current_user: User = Depends(current_active_user),
):
    return service.list_presentation_statuses(course_id)


@router.get(
    "/{course_id}/embeddings/status", response_model=CourseEmbeddingStatusResponse
)
def get_embeddings_status(
    course_id: int,
    background_tasks: BackgroundTasks,
    service: CourseService = Depends(get_course_service),
    current_user: User = Depends(current_active_user),
):
    return service.get_course_embedding_status(
        course_id, background_tasks=background_tasks
    )


@router.delete(
    "/{course_id}/presentations/{filename}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_presentation(
    course_id: int,
    filename: str,
    service: CourseService = Depends(get_course_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    await service.delete_presentation(course_id, filename, teacher)


@router.delete("/{course_id}/presentations", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_presentations(
    course_id: int,
    service: CourseService = Depends(get_course_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    await service.delete_all_presentations(course_id, teacher)


@router.post(
    "/{course_id}/extract",
    response_model=StartExtractionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_extraction(
    course_id: int,
    background_tasks: BackgroundTasks,
    service: CourseService = Depends(get_course_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    extraction_status = service.start_extraction(course_id, teacher, background_tasks)
    return StartExtractionResponse(
        message="Extraction started", status=extraction_status
    )


@router.get("/{course_id}/extract/stream")
async def stream_extraction_progress(
    course_id: int,
    service: CourseService = Depends(get_course_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    """SSE endpoint that streams extraction progress.

    - If extraction is not running, starts it in a background thread.
    - If extraction is already running (e.g., page refresh), joins and streams
      the existing progress.
    - Keeps the HTTP connection alive, preventing Azure scale-to-zero.
    """
    import asyncio
    import json
    import logging
    import threading

    from app.modules.document_extraction.service import (
        run_course_extraction_background,
    )

    logger = logging.getLogger(__name__)

    started = service.start_extraction_if_idle(course_id, teacher)
    if started:
        extraction_thread = threading.Thread(
            target=run_course_extraction_background,
            kwargs={"course_id": course_id, "teacher_id": teacher.id},
            daemon=True,
        )
        extraction_thread.start()

    async def event_generator():
        poll_interval = 2  # seconds
        keepalive_interval = 25  # seconds
        ticks_since_keepalive = 0
        previous_terminal = -1

        # Emit initial progress immediately
        try:
            progress = await asyncio.to_thread(
                service.get_extraction_progress, course_id
            )
            previous_terminal = progress["terminal"]
            yield f"event: progress\ndata: {json.dumps(progress)}\n\n"
        except Exception:
            logger.exception("Failed to get initial extraction progress")

        while True:
            await asyncio.sleep(poll_interval)
            ticks_since_keepalive += poll_interval

            try:
                progress = await asyncio.to_thread(
                    service.get_extraction_progress, course_id
                )
            except Exception:
                logger.exception("Failed to poll extraction progress")
                yield f"event: error\ndata: {json.dumps({'error': 'Failed to read progress'})}\n\n"
                break

            # Emit progress if anything changed
            if progress["terminal"] != previous_terminal:
                previous_terminal = progress["terminal"]
                ticks_since_keepalive = 0
                yield f"event: progress\ndata: {json.dumps(progress)}\n\n"

            # All files reached terminal state — emit final event and close
            if progress["total"] > 0 and progress["terminal"] >= progress["total"]:
                # Re-read the course to get the final extraction_status
                try:
                    course = await asyncio.to_thread(service.get_course, course_id)
                    final_status = course.extraction_status.value
                except Exception:
                    final_status = "finished" if progress["failed"] == 0 else "failed"
                complete_payload = {
                    "status": final_status,
                    **progress,
                }
                yield f"event: complete\ndata: {json.dumps(complete_payload)}\n\n"
                break

            # Send keep-alive comment to prevent TCP idle timeout
            if ticks_since_keepalive >= keepalive_interval:
                ticks_since_keepalive = 0
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{course_id}/curriculum", response_model=CurriculumWithChangelog)
def get_course_curriculum(
    course_id: int,
    service: CurriculumService = Depends(get_curriculum_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return service.get_curriculum(course_id=course_id, teacher=teacher)


@router.get("/{course_id}/skill-banks", response_model=SkillBanksResponse)
def get_course_skill_banks(
    course_id: int,
    service: CurriculumService = Depends(get_curriculum_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return service.get_skill_banks(course_id=course_id, teacher=teacher)
