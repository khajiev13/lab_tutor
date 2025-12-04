from contextlib import asynccontextmanager

from fastapi import FastAPI

from lab_tutor_backend.database import Base, engine
from lab_tutor_backend.routes import auth as auth_routes
from lab_tutor_backend.routes import courses as course_routes
from lab_tutor_backend.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_routes.router)
app.include_router(course_routes.router)


@app.get("/")
def read_root():
    return {"message": "Welcome to Lab Tutor"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}

