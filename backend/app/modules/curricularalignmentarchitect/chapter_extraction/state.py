"""TypedDict state definitions for the chapter extraction LangGraph workflow."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from .schemas import ChapterConceptsResult, ExtractionFeedback

# ── Inner graph: extract → evaluate → revise loop for one chapter ──


class ChapterExtractionState(TypedDict):
    book_name: str
    chapter_title: str
    section_titles: list[str]
    chapter_content: str
    extraction: ChapterConceptsResult | None
    feedback: ExtractionFeedback | None
    iteration: int
    max_iterations: int
    approved: bool


# ── Outer graph: book-level pipeline with parallel chapter workers ──


class BookPipelineState(TypedDict):
    run_id: int
    selected_book_id: int
    book_name: str
    book_label: str
    chapters: list[dict]  # chapter dicts from pdf_parser
    total_chapters: int
    completed_chapters: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]


class ChapterWorkerInput(TypedDict):
    run_id: int
    selected_book_id: int
    book_name: str
    book_label: str
    chapter_number: int
    chapter_title: str
    section_titles: list[str]
    chapter_content: str
    total_chapters: int
    completed_chapters: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]


# ── Constants ──

MAX_ITERATIONS = 2
CHAPTER_GRAPH_MAX_CONCURRENCY = 2
CHAPTER_GRAPH_RECURSION_LIMIT = 10
BOOK_PIPELINE_MAX_CONCURRENCY = 5
BOOK_PIPELINE_RECURSION_LIMIT = 200
