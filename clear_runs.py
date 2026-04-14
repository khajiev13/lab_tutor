from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.modules.curricularalignmentarchitect.models import BookExtractionRun

engine = create_engine("postgresql://khajievroma@localhost:5432/lab_tutor_test")
with Session(engine) as session:
    runs = session.query(BookExtractionRun).all()
    print(f"Deleting {len(runs)} extraction runs...")
    for run in runs:
        session.delete(run)
    session.commit()
    print("Done clearing extraction runs.")
