"""State and constants for chunking analysis phase."""

import operator
from typing import Annotated, TypedDict

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
SEPARATORS = ["\n\n", "\n", ". "]
NOVEL_THRESHOLD = 0.35
COVERED_THRESHOLD = 0.55


class ChunkingState(TypedDict, total=False):
    run_id: int
    course_id: int
    books: list[dict]
    embedded_books: Annotated[list[dict], operator.add]
    doc_summaries: Annotated[list[dict], operator.add]


__all__ = [
    "ChunkingState",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "SEPARATORS",
    "NOVEL_THRESHOLD",
    "COVERED_THRESHOLD",
]
