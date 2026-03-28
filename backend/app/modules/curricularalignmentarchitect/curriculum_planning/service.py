from __future__ import annotations

from langchain_openai import ChatOpenAI
from neo4j import Session as Neo4jSession
from pydantic import SecretStr

from app.core.settings import settings

from .prompts import CHAPTER_PLAN_PROMPT
from .repository import ChapterPlanRepository
from .schemas import ChapterPlan, ChapterPlanResponse, CourseChapterPlan


def _build_llm() -> ChatOpenAI:
    if not settings.llm_api_key:
        raise ValueError(
            "LLM API key is required (set LAB_TUTOR_LLM_API_KEY / OPENAI_API_KEY)"
        )
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=SecretStr(settings.llm_api_key),
        temperature=0,
        timeout=settings.llm_timeout_seconds,
        max_completion_tokens=settings.llm_max_completion_tokens,
    )


class TeacherCurriculumPlanner:
    def __init__(self, neo4j_session: Neo4jSession) -> None:
        self.repo = ChapterPlanRepository(neo4j_session)

    def generate_plan(self, course_id: int, course_title: str) -> ChapterPlanResponse:
        docs = self.repo.list_documents(course_id)
        if not docs:
            return ChapterPlanResponse(
                course_id=course_id,
                chapters=[],
                unassigned_documents=[],
                all_documents=[],
            )

        doc_lines = []
        for i, d in enumerate(docs, 1):
            parts = [f"{i}. ID: {d.id}", f"   Filename: {d.source_filename}"]
            if d.topic:
                parts.append(f"   Topic: {d.topic}")
            if d.summary:
                parts.append(f"   Summary: {d.summary[:300]}")
            doc_lines.append("\n".join(parts))
        documents_text = "\n\n".join(doc_lines)

        llm = _build_llm()
        chain = CHAPTER_PLAN_PROMPT | llm.with_structured_output(CourseChapterPlan)
        plan: CourseChapterPlan = chain.invoke(  # type: ignore[assignment]
            {"course_title": course_title, "documents": documents_text}
        )

        # Validate doc IDs — drop any hallucinated ones
        valid_ids = {d.id for d in docs}
        for ch in plan.chapters:
            ch.assigned_documents = [d for d in ch.assigned_documents if d in valid_ids]

        self.repo.save_plan(course_id, plan.chapters)

        assigned_ids = {
            doc_id for ch in plan.chapters for doc_id in ch.assigned_documents
        }
        unassigned = [d for d in docs if d.id not in assigned_ids]
        return ChapterPlanResponse(
            course_id=course_id,
            chapters=plan.chapters,
            unassigned_documents=unassigned,
            all_documents=docs,
        )

    def get_plan(self, course_id: int) -> ChapterPlanResponse:
        return self.repo.get_plan(course_id)

    def save_plan(
        self, course_id: int, chapters: list[ChapterPlan]
    ) -> ChapterPlanResponse:
        self.repo.save_plan(course_id, chapters)
        return self.repo.get_plan(course_id)
