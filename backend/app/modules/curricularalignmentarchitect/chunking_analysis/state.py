"""State and constants for chunking analysis phase."""

from typing import TypedDict

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
SEPARATORS = ["\n\n", "\n", ". "]
NOVEL_THRESHOLD = 0.35
COVERED_THRESHOLD = 0.55
# Pages whose fitz text-char count falls outside [MIN_TEXT_CHARS, MAX_TEXT_CHARS]
# are skipped before pymupdf4llm — image-only pages and malformed/index pages
# that can cause pymupdf4llm to hang indefinitely.
MIN_TEXT_CHARS = 50
MAX_TEXT_CHARS = 15_000


class ChunkingState(TypedDict, total=False):
    run_id: int
    course_id: int
    books: list[dict]


__all__ = [
    "ChunkingState",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "SEPARATORS",
    "NOVEL_THRESHOLD",
    "COVERED_THRESHOLD",
    "MIN_TEXT_CHARS",
    "MAX_TEXT_CHARS",
]
