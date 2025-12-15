from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..database import get_db
from ..models import Course, CourseEnrollment, ExtractionStatus, User, UserRole
from ..schemas import CourseCreate, CourseRead, EnrollmentRead
from ..services.blob_service import blob_service

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(
    course_in: CourseCreate,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
) -> Course:
    course = Course(
        title=course_in.title,
        description=course_in.description,
        teacher_id=teacher.id,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("", response_model=list[CourseRead])
def list_courses(db: Session = Depends(get_db)) -> list[Course]:
    return db.query(Course).order_by(Course.created_at.desc()).all()


@router.get("/{course_id}", response_model=CourseRead)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    return course


@router.post(
    "/{course_id}/join",
    response_model=EnrollmentRead,
    status_code=status.HTTP_201_CREATED,
)
def join_course(
    course_id: int,
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
) -> CourseEnrollment:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    existing = (
        db.query(CourseEnrollment)
        .filter(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == student.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Already joined this course"
        )

    enrollment = CourseEnrollment(course_id=course_id, student_id=student.id)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


@router.put("/{course_id}", response_model=CourseRead)
def update_course(
    course_id: int,
    course_update: CourseCreate,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    if course.teacher_id != teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this course",
        )

    course.title = course_update.title
    course.description = course_update.description
    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    if course.teacher_id != teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this course",
        )

    db.delete(course)
    db.commit()


@router.post("/{course_id}/presentations", status_code=status.HTTP_201_CREATED)
async def upload_presentations(
    course_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    if course.teacher_id != teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload files for this course",
        )

    if course.extraction_status == ExtractionStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot upload files while extraction is in progress",
        )

    uploaded_urls = []
    for file in files:
        # Sanitize course title for folder name
        safe_course_title = (
            "".join(c for c in course.title if c.isalnum() or c in (" ", "_", "-"))
            .strip()
            .replace(" ", "_")
        )
        destination_path = f"{safe_course_title}/teacher_uploads/{file.filename}"

        try:
            url = await blob_service.upload_file(file, destination_path)
            uploaded_urls.append(url)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file {file.filename}: {str(e)}",
            ) from e

    return {"uploaded_files": uploaded_urls}


@router.get("/{course_id}/presentations", response_model=list[str])
async def list_presentations(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    # Allow both teachers and students (if enrolled) to view presentations
    # For now, we'll just check if they are authenticated, which is handled by Depends(get_current_user)
    # You might want to add stricter checks (e.g. must be the teacher OR enrolled student)

    safe_course_title = (
        "".join(c for c in course.title if c.isalnum() or c in (" ", "_", "-"))
        .strip()
        .replace(" ", "_")
    )
    folder_path = f"{safe_course_title}/teacher_uploads/"

    try:
        files = await blob_service.list_files(folder_path)
        # Return only filenames, not full paths, to make it easier for frontend
        return [f.split("/")[-1] for f in files]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list presentations: {str(e)}",
        ) from e


@router.delete(
    "/{course_id}/presentations/{filename}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_presentation(
    course_id: int,
    filename: str,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    if course.teacher_id != teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete files for this course",
        )

    if course.extraction_status == ExtractionStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete files while extraction is in progress",
        )

    safe_course_title = (
        "".join(c for c in course.title if c.isalnum() or c in (" ", "_", "-"))
        .strip()
        .replace(" ", "_")
    )
    blob_path = f"{safe_course_title}/teacher_uploads/{filename}"

    try:
        await blob_service.delete_file(blob_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file {filename}: {str(e)}",
        ) from e


@router.delete("/{course_id}/presentations", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_presentations(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    if course.teacher_id != teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete files for this course",
        )

    if course.extraction_status == ExtractionStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete files while extraction is in progress",
        )

    safe_course_title = (
        "".join(c for c in course.title if c.isalnum() or c in (" ", "_", "-"))
        .strip()
        .replace(" ", "_")
    )
    folder_path = f"{safe_course_title}/teacher_uploads/"

    try:
        await blob_service.delete_folder(folder_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete presentations: {str(e)}",
        ) from e


@router.post("/{course_id}/extract", status_code=status.HTTP_202_ACCEPTED)
async def start_extraction(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role(UserRole.TEACHER)),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    if course.teacher_id != teacher.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to start extraction for this course",
        )

    if course.extraction_status == ExtractionStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Extraction already in progress",
        )

    # Update status
    course.extraction_status = ExtractionStatus.IN_PROGRESS
    db.commit()

    # TODO: Call extraction service
    # await extraction_service.start_extraction(course.id, db)

    return {"message": "Extraction started", "status": course.extraction_status}
