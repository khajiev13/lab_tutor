
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_role
from ..database import get_db
from ..models import Course, CourseEnrollment, User, UserRole
from ..schemas import CourseCreate, CourseRead, EnrollmentRead

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


@router.post("/{course_id}/join", response_model=EnrollmentRead, status_code=status.HTTP_201_CREATED)
def join_course(
    course_id: int,
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
) -> CourseEnrollment:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    existing = (
        db.query(CourseEnrollment)
        .filter(CourseEnrollment.course_id == course_id, CourseEnrollment.student_id == student.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already joined this course")

    enrollment = CourseEnrollment(course_id=course_id, student_id=student.id)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment

