"""TypedDict state definitions for the chapter extraction LangGraph workflow."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

# ── Outer graph: book-level pipeline with parallel chapter workers ──


class BookPipelineState(TypedDict):
    run_id: int
    selected_book_id: int
    course_subject: str
    book_name: str
    book_label: str
    chapters: list[dict]  # chapter dicts from pdf_parser
    total_chapters: int
    completed_chapters: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]


class ChapterWorkerInput(TypedDict):
    run_id: int
    selected_book_id: int
    course_subject: str
    book_name: str
    book_label: str
    chapter_number: int
    chapter_title: str
    chapter_content: str
    total_chapters: int
    completed_chapters: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]


# ── Constants ──

MAX_JUDGE_ITERATIONS = 1  # one revision pass if judge rejects
BOOK_PIPELINE_MAX_CONCURRENCY = 5
BOOK_PIPELINE_RECURSION_LIMIT = 200
