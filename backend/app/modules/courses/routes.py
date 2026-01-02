from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status

from app.modules.auth.dependencies import (
    current_active_user,
    require_role,
)
from app.modules.auth.models import User, UserRole

from .graph_schemas import CourseGraphResponse, GraphNodeKind
from .graph_service import CourseGraphService, get_course_graph_service
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


@router.get("/{course_id}/graph", response_model=CourseGraphResponse)
def get_course_graph(
    course_id: int,
    max_documents: int = 100,
    max_concepts: int = 750,
    service: CourseGraphService = Depends(get_course_graph_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return service.get_snapshot(
        course_id=course_id,
        teacher=teacher,
        max_documents=max_documents,
        max_concepts=max_concepts,
    )


@router.get("/{course_id}/graph/expand", response_model=CourseGraphResponse)
def expand_course_graph(
    course_id: int,
    node_kind: GraphNodeKind,
    node_key: str = "",
    limit: int = 200,
    max_concepts: int = 750,
    service: CourseGraphService = Depends(get_course_graph_service),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    return service.expand(
        course_id=course_id,
        teacher=teacher,
        node_kind=node_kind,
        node_key=node_key,
        limit=limit,
        max_concepts=max_concepts,
    )
