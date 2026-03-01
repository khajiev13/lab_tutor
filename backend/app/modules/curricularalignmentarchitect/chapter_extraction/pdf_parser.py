"""PDF TOC extraction and chapter detection — backward-compat re-exports.

All functionality has been consolidated into the shared
``app.modules.curricularalignmentarchitect.pdf_extraction`` module.
This file re-exports the public API for any existing imports.
"""

from __future__ import annotations

from ..pdf_extraction import (
    clean_chapter_for_llm,
    clean_extracted_text,
    detect_chapter_indices,
    extract_full_markdown,
    extract_toc_entries,
    filter_pdf_pages,
    split_markdown_by_chapters,
    strip_book_matter,
    validate_extracted_chapters,
)
from ..pdf_extraction import (
    extract_book_chapters as load_book_chapters,
)

__all__ = [
    "clean_chapter_for_llm",
    "clean_extracted_text",
    "detect_chapter_indices",
    "extract_full_markdown",
    "extract_toc_entries",
    "filter_pdf_pages",
    "load_book_chapters",
    "split_markdown_by_chapters",
    "strip_book_matter",
    "validate_extracted_chapters",
]
