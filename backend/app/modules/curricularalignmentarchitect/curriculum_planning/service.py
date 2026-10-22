from __future__ import annotations

import json

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
    model = settings.llm_model
    extra_body = {}
    if model.lower().startswith("deepseek"):
        extra_body = {"thinking": {"type": "disabled"}}
    elif model.lower().startswith("qwen"):
        extra_body = {"enable_thinking": False}
    return ChatOpenAI(
        model=model,
        base_url=settings.llm_base_url,
        api_key=SecretStr(settings.llm_api_key),
        temperature=0,
        timeout=90,
        max_retries=0,
        max_completion_tokens=8192,
        extra_body=extra_body,
    )


def _validate_plan(chapters: list[ChapterPlan], valid_ids: set[str]) -> None:
    titles: set[str] = set()
    assigned: set[str] = set()
    for number, chapter in enumerate(chapters, 1):
        title = chapter.title.strip()
        if not title or title.casefold() in {t.casefold() for t in titles}:
            raise ValueError("Chapter titles must be nonempty and unique")
        if chapter.number != number:
            raise ValueError("Chapter numbers must be consecutive, starting at 1")
        if any(prerequisite not in titles for prerequisite in chapter.prerequisites):
            raise ValueError("Prerequisites must name an earlier chapter exactly")
        titles.add(title)
        chapter.title = title
        for document_id in chapter.assigned_documents:
            if document_id not in valid_ids:
                raise ValueError(f"Unknown course document ID: {document_id}")
            if document_id in assigned:
                raise ValueError(f"Document assigned more than once: {document_id}")
            assigned.add(document_id)
    if assigned != valid_ids:
        raise ValueError(
            "Assign every course document exactly once; missing document IDs: "
            + ", ".join(sorted(valid_ids - assigned))
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
        chain = CHAPTER_PLAN_PROMPT | llm.with_structured_output(
            CourseChapterPlan, method="json_mode", include_raw=True
        )
        valid_ids = {d.id for d in docs}
        feedback = ""
        for attempt in range(2):
            result = chain.invoke(
                {
                    "course_title": course_title,
                    "documents": documents_text,
                    "schema": json.dumps(CourseChapterPlan.model_json_schema()),
                    "validation_feedback": feedback,
                },
                config={"callbacks": [], "tags": ["nostream"]},
            )
            try:
                if result["raw"].response_metadata.get("finish_reason") == "length":
                    raise ValueError(
                        "The chapter plan was truncated; use concise descriptions"
                    )
                plan = result["parsed"]
                if result.get("parsing_error") or not isinstance(
                    plan, CourseChapterPlan
                ):
                    raise ValueError(
                        "Return a valid JSON object matching the chapter plan schema"
                    )
                _validate_plan(plan.chapters, valid_ids)
                break
            except ValueError as exc:
                if attempt:
                    raise ValueError(
                        f"Could not generate a complete chapter plan: {exc}"
                    ) from exc
                feedback = f"Correct the previous invalid plan: {exc}. Return the entire corrected plan."

        self.repo.save_plan(course_id, plan.chapters)
        return self.repo.get_plan(course_id)

    def get_plan(self, course_id: int) -> ChapterPlanResponse:
        return self.repo.get_plan(course_id)

    def save_plan(
        self, course_id: int, chapters: list[ChapterPlan]
    ) -> ChapterPlanResponse:
        self.repo.save_plan(course_id, chapters)
        return self.repo.get_plan(course_id)
