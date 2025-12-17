from fastapi import Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.models import User
from app.providers.storage import blob_service

from .models import Course, CourseEnrollment, ExtractionStatus
from .repository import CourseRepository
from .schemas import CourseCreate


def get_course_repository(db: Session = Depends(get_db)) -> CourseRepository:
    return CourseRepository(db)


class CourseService:
    def __init__(self, repo: CourseRepository):
        self.repo = repo

    def create_course(self, course_in: CourseCreate, teacher: User) -> Course:
        course = Course(
            title=course_in.title,
            description=course_in.description,
            teacher_id=teacher.id,
        )
        try:
            return self.repo.create(course)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    def list_courses(self) -> list[Course]:
        return list(self.repo.list())

    def list_enrolled_courses(self, student: User) -> list[Course]:
        return list(self.repo.list_enrolled(student.id))

    def get_course(self, course_id: int) -> Course:
        course = self.repo.get_by_id(course_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        return course

    def join_course(self, course_id: int, student: User) -> CourseEnrollment:
        course = self.get_course(course_id) # Re-use logic
        
        existing = self.repo.get_enrollment(course_id, student.id)
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already joined this course")

        enrollment = CourseEnrollment(course_id=course.id, student_id=student.id)
        return self.repo.create_enrollment(enrollment)

    def leave_course(self, course_id: int, student: User) -> None:
        existing = self.repo.get_enrollment(course_id, student.id)
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not enrolled in this course")
        
        self.repo.delete_enrollment(existing)

    def get_enrollment(self, course_id: int, student: User) -> CourseEnrollment | None:
        return self.repo.get_enrollment(course_id, student.id)

    def update_course(self, course_id: int, course_update: CourseCreate, teacher: User) -> Course:
        course = self.get_course(course_id)
        
        if course.teacher_id != teacher.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this course")
        
        course.title = course_update.title
        if course_update.description is not None:
            course.description = course_update.description
            
        try:
            return self.repo.update(course)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    def delete_course(self, course_id: int, teacher: User) -> None:
        course = self.get_course(course_id)
        
        if course.teacher_id != teacher.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this course")
        
        self.repo.delete(course)

    async def upload_presentations(self, course_id: int, files: list[UploadFile], teacher: User) -> list[str]:
        course = self.get_course(course_id)
        
        if course.teacher_id != teacher.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to upload files for this course")
        
        if course.extraction_status == ExtractionStatus.IN_PROGRESS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot upload files while extraction is in progress")
        
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
        return uploaded_urls

    async def list_presentations(self, course_id: int) -> list[str]:
        course = self.get_course(course_id)
        
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

    async def delete_presentation(self, course_id: int, filename: str, teacher: User) -> None:
        course = self.get_course(course_id)
        
        if course.teacher_id != teacher.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete files for this course")
        
        if course.extraction_status == ExtractionStatus.IN_PROGRESS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete files while extraction is in progress")
        
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

    async def delete_all_presentations(self, course_id: int, teacher: User) -> None:
        course = self.get_course(course_id)
        
        if course.teacher_id != teacher.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete files for this course")
        
        if course.extraction_status == ExtractionStatus.IN_PROGRESS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete files while extraction is in progress")
        
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

    def start_extraction(self, course_id: int, teacher: User) -> ExtractionStatus:
        course = self.get_course(course_id)
        
        if course.teacher_id != teacher.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to start extraction for this course")
        
        if course.extraction_status == ExtractionStatus.IN_PROGRESS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Extraction already in progress")
        
        course.extraction_status = ExtractionStatus.IN_PROGRESS
        self.repo.update(course)
        
        # TODO: Call extraction service
        # await extraction_service.start_extraction(course.id, db)
        
        return course.extraction_status


def get_course_service(repo: CourseRepository = Depends(get_course_repository)) -> CourseService:
    return CourseService(repo)
