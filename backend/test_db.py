import json

from app.core.database import SessionLocal
from app.modules.courses.models import CourseFile

db = SessionLocal()
files = (
    db.query(CourseFile).filter(CourseFile.course_id == 1).order_by(CourseFile.id).all()
)
print(
    json.dumps(
        [
            {
                "name": f.filename,
                "status": f.status.value,
                "processed": str(f.processed_at),
            }
            for f in files[:3]
        ],
        indent=2,
    )
)
