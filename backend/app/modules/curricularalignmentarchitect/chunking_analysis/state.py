"""State and constants for chunking analysis phase."""

from .workflow import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COVERED_THRESHOLD,
    NOVEL_THRESHOLD,
    SEPARATORS,
    ChunkingState,
)

__all__ = [
    "ChunkingState",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "SEPARATORS",
    "NOVEL_THRESHOLD",
    "COVERED_THRESHOLD",
]
