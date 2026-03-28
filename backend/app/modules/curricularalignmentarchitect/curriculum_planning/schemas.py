from pydantic import BaseModel, Field


class DocumentInfo(BaseModel):
    id: str
    source_filename: str
    topic: str | None = None
    summary: str | None = None


class ChapterPlan(BaseModel):
    number: int
    title: str
    description: str
    learning_objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)  # chapter titles
    assigned_documents: list[str] = Field(default_factory=list)  # doc UUIDs


class CourseChapterPlan(BaseModel):
    """Structured output from LLM."""

    chapters: list[ChapterPlan]


class ChapterPlanResponse(BaseModel):
    course_id: int
    chapters: list[ChapterPlan]
    unassigned_documents: list[DocumentInfo]
    all_documents: list[DocumentInfo]


class SaveChapterPlanRequest(BaseModel):
    chapters: list[ChapterPlan]
