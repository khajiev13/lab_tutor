"""One-shot script: wipe all book-selection data for a course (SQL + Azure)."""

import asyncio
import sys

sys.path.insert(0, ".")

from app.core.database import SessionLocal
from app.modules.curricularalignmentarchitect.models import (
    BookSelectionSession,
    CourseBook,
    CourseSelectedBook,
)
from app.providers.storage import blob_service

COURSE_ID = 1


def cleanup_sql(db):
    selected_count = (
        db.query(CourseSelectedBook)
        .filter(CourseSelectedBook.course_id == COURSE_ID)
        .count()
    )
    books_count = (
        db.query(CourseBook).filter(CourseBook.course_id == COURSE_ID).count()
    )
    sessions_count = (
        db.query(BookSelectionSession)
        .filter(BookSelectionSession.course_id == COURSE_ID)
        .count()
    )
    print(
        f"Deleting: {selected_count} selected books, "
        f"{books_count} course books, {sessions_count} sessions"
    )

    db.query(CourseSelectedBook).filter(
        CourseSelectedBook.course_id == COURSE_ID
    ).delete()
    db.query(CourseBook).filter(CourseBook.course_id == COURSE_ID).delete()
    db.query(BookSelectionSession).filter(
        BookSelectionSession.course_id == COURSE_ID
    ).delete()
    db.commit()
    print("SQL cleanup done")


async def cleanup_blobs():
    try:
        folder = f"courses/{COURSE_ID}/books/"
        files = await blob_service.list_files(folder)
        print(f"Azure blobs to delete: {files}")
        await blob_service.delete_folder(folder)
        print("Azure blob cleanup done")
    except Exception as e:
        print(f"Azure cleanup note: {e}")


def main():
    db = SessionLocal()
    try:
        cleanup_sql(db)
    finally:
        db.close()

    asyncio.run(cleanup_blobs())
    print("All done! You can now start book selection fresh.")


if __name__ == "__main__":
    main()
