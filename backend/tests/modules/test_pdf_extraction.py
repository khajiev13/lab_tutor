"""Tests for the PDF extraction module (3-strategy fallback chain).

Covers:
- clean_extracted_text — text cleaning pipeline
- clean_chapter_for_llm — LLM-ready text cleanup
- _is_boilerplate — boilerplate title detection
- detect_chapter_indices — chapter auto-detection (3-strategy cascade)
- extract_chapters_from_pdf — orchestrator (integration test with real PDF)
- extract_book_chapters — Azure entry point (mocked)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fpdf import FPDF

from app.modules.curricularalignmentarchitect.pdf_extraction import (
    _clean_title,
    _is_boilerplate,
    clean_chapter_for_llm,
    clean_extracted_text,
    detect_chapter_indices,
    extract_book_chapters,
    extract_chapters_from_pdf,
    validate_extracted_chapters,
)
from app.providers.storage import BlobService

# ── Helpers ────────────────────────────────────────────────────


def _make_pdf(
    tmp_path,
    *,
    chapters: dict[str, list[str]],
    add_bookmarks: bool = True,
    filename: str = "test_book.pdf",
) -> str:
    """Create a test PDF with chapter text and optional bookmarks via fpdf2."""
    pdf_path = str(tmp_path / filename)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    for ch_title, sections in chapters.items():
        for sec_idx, section_text in enumerate(sections):
            pdf.add_page()
            if add_bookmarks and sec_idx == 0:
                pdf.start_section(ch_title, level=0)
            if sec_idx == 0:
                pdf.set_font("Helvetica", "B", size=14)
                pdf.cell(0, 10, ch_title, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(0, 5, section_text)

    pdf.output(pdf_path)
    return pdf_path


def _make_minimal_pdf(
    tmp_path, text: str = "Minimal text content.", filename: str = "minimal.pdf"
) -> str:
    """Create a single-page PDF with no structure."""
    pdf_path = str(tmp_path / filename)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 5, text)
    pdf.output(pdf_path)
    return pdf_path


SAMPLE_CHAPTERS = {
    f"Chapter {i}: Topic {i}": [
        f"This is the introduction to chapter {i}. " * 40
        + "\n"
        + f"Section {i}.1: Subsection A\n"
        + f"Content for subsection A of chapter {i}. " * 30,
        f"Continued content for chapter {i}, page 2. " * 40,
        f"More content for chapter {i}, page 3. " * 40,
        f"Still more content for chapter {i}, page 4. " * 40,
        f"Final content for chapter {i}, page 5. " * 40,
    ]
    for i in range(1, 11)
}


# ── clean_extracted_text ───────────────────────────────────────


class TestCleanExtractedText:
    def test_removes_lone_page_numbers(self):
        text = "Hello world\n  42  \nGoodbye"
        result = clean_extracted_text(text)
        assert "42" not in result
        assert "Hello world" in result
        assert "Goodbye" in result

    def test_strips_nul_and_control_chars(self):
        text = "Hello\x00World\x01Foo\x0fBar"
        result = clean_extracted_text(text)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x0f" not in result
        assert "HelloWorldFooBar" in result

    def test_removes_toc_lines(self):
        text = "Chapter 1: Introduction ......... 15\nActual content here."
        result = clean_extracted_text(text)
        assert "Actual content here" in result
        assert "........." not in result

    def test_fixes_broken_hyphens(self):
        text = "This is a bro-\nken word in the text."
        result = clean_extracted_text(text)
        assert "broken" in result

    def test_collapses_excessive_newlines(self):
        text = "A\n\n\n\n\nB"
        result = clean_extracted_text(text)
        assert "\n\n\n" not in result
        assert result == "A\n\nB"

    def test_strips_trailing_whitespace(self):
        text = "Hello   \nWorld  "
        result = clean_extracted_text(text)
        assert result == "Hello\nWorld"

    def test_removes_noisy_headers(self):
        header = "My Book Title"
        lines = [header] * 20 + ["Real content. " * 50]
        text = "\n".join(lines)
        result = clean_extracted_text(text)
        assert header not in result
        assert "Real content" in result

    def test_empty_input(self):
        assert clean_extracted_text("") == ""
        assert clean_extracted_text("   ") == ""


# ── clean_chapter_for_llm ─────────────────────────────────────


class TestCleanChapterForLlm:
    def test_inherits_clean_extracted_text(self):
        """Page numbers and TOC lines removed (inherited)."""
        text = "Hello world\n  42  \nGoodbye"
        result = clean_chapter_for_llm(text)
        assert "42" not in result
        assert "Hello world" in result

    def test_fixes_uppercase_hyphen_breaks(self):
        text = "UP-\nPER case word"
        result = clean_chapter_for_llm(text)
        assert "UPPER" in result

    def test_fixes_mixed_case_hyphen_breaks(self):
        text = "some-\nthing else"
        result = clean_chapter_for_llm(text)
        assert "something" in result

    def test_normalizes_big_whitespace(self):
        text = "word1     word2"
        result = clean_chapter_for_llm(text)
        assert "     " not in result
        assert "word1" in result and "word2" in result

    def test_tabs_normalized(self):
        text = "col1\t\t\tcol2"
        result = clean_chapter_for_llm(text)
        assert "\t\t\t" not in result

    def test_empty_input(self):
        assert clean_chapter_for_llm("") == ""
        assert clean_chapter_for_llm("   ") == ""


# ── _is_boilerplate ───────────────────────────────────────────


class TestIsBoilerplate:
    @pytest.mark.parametrize(
        "title",
        [
            "Index",
            "BIBLIOGRAPHY",
            "  References  ",
            "Table of Contents",
            "Acknowledgements",
            "foreword",
            "Glossary",
        ],
    )
    def test_boilerplate_titles(self, title: str):
        assert _is_boilerplate(title)

    @pytest.mark.parametrize(
        "title",
        [
            "Chapter 1: Introduction",
            "Data Structures",
            "Machine Learning Basics",
            "1. Overview",
        ],
    )
    def test_non_boilerplate_titles(self, title: str):
        assert not _is_boilerplate(title)


# ── detect_chapter_indices ─────────────────────────────────────


class TestDetectChapterIndices:
    def test_keyword_strategy(self):
        entries = [{"level": 1, "title": f"Chapter {i}: Topic"} for i in range(1, 11)]
        indices = detect_chapter_indices(entries)
        assert indices == list(range(10))

    def test_numbered_prefix_strategy(self):
        entries = [{"level": 1, "title": f"{i}. Some Topic"} for i in range(1, 6)]
        indices = detect_chapter_indices(entries)
        assert indices == list(range(5))

    def test_all_toplevel_fallback(self):
        entries = [
            {"level": 1, "title": "Getting Started"},
            {"level": 1, "title": "Data Models"},
            {"level": 1, "title": "Index"},
        ]
        indices = detect_chapter_indices(entries)
        assert 0 in indices
        assert 1 in indices
        assert 2 not in indices

    def test_empty_entries(self):
        assert detect_chapter_indices([]) == []

    def test_includes_appendices(self):
        entries = [
            {"level": 1, "title": "Chapter 1: Intro"},
            {"level": 1, "title": "Chapter 2: Methods"},
            {"level": 1, "title": "Appendix A: Extra Material"},
        ]
        indices = detect_chapter_indices(entries, include_appendices=True)
        assert 2 in indices

    def test_excludes_boilerplate(self):
        entries = [
            {"level": 1, "title": "Chapter 1: Intro"},
            {"level": 1, "title": "Chapter 2: Methods"},
            {"level": 1, "title": "Index"},
        ]
        indices = detect_chapter_indices(entries)
        titles = [entries[i]["title"] for i in indices]
        assert "Index" not in titles

    def test_false_positives_excluded(self):
        entries = [
            {"level": 1, "title": "Chapter 1: Intro"},
            {"level": 1, "title": "Chapter 2: Methods"},
            {"level": 1, "title": "Chapter 1 Summary"},
            {"level": 1, "title": "Chapter 2 Quiz"},
        ]
        indices = detect_chapter_indices(entries)
        assert 0 in indices
        assert 1 in indices
        assert 2 not in indices
        assert 3 not in indices

    def test_mixed_levels(self):
        entries = [
            {"level": 1, "title": "Getting Started"},
            {"level": 2, "title": "Sub Section A"},
            {"level": 1, "title": "Advanced Topics"},
            {"level": 2, "title": "Sub Section B"},
        ]
        indices = detect_chapter_indices(entries)
        assert 0 in indices
        assert 2 in indices
        assert 1 not in indices
        assert 3 not in indices


# ── extract_chapters_from_pdf (integration) ───────────────────


class TestExtractChaptersFromPdf:
    @pytest.fixture
    def simple_pdf(self, tmp_path):
        return _make_pdf(tmp_path, chapters=SAMPLE_CHAPTERS, add_bookmarks=True)

    @pytest.fixture
    def minimal_pdf(self, tmp_path):
        return _make_minimal_pdf(tmp_path)

    def test_extracts_chapters(self, simple_pdf):
        chapters, method = extract_chapters_from_pdf(simple_pdf, title="Test Book")
        assert len(chapters) >= 1
        assert method in (
            "bookmarks",
            "heading_detection",
            "page_chunks",
            "fallback",
        )

        for ch in chapters:
            assert "chapter_number" in ch
            assert "title" in ch
            assert "sections" in ch
            assert "content" in ch
            assert len(ch["content"]) > 0

    def test_returns_valid_method(self, simple_pdf):
        _, method = extract_chapters_from_pdf(simple_pdf)
        assert method in {
            "bookmarks",
            "heading_detection",
            "page_chunks",
            "fallback",
        }

    def test_output_contract(self, simple_pdf):
        chapters, _ = extract_chapters_from_pdf(simple_pdf, title="Test Book")
        required_keys = {
            "chapter_number",
            "title",
            "level",
            "start_page",
            "end_page",
            "sections",
            "content",
        }
        for ch in chapters:
            assert required_keys.issubset(ch.keys())
            assert isinstance(ch["sections"], list)
            assert isinstance(ch["content"], str)
            assert isinstance(ch["start_page"], int) and ch["start_page"] >= 1
            assert (
                isinstance(ch["end_page"], int) and ch["end_page"] >= ch["start_page"]
            )

    def test_fallback_for_minimal_pdf(self, minimal_pdf):
        chapters, method = extract_chapters_from_pdf(minimal_pdf, title="Empty Book")
        assert method in ("page_chunks", "fallback")
        assert len(chapters) == 1

    def test_content_cleaned(self, simple_pdf):
        chapters, _ = extract_chapters_from_pdf(simple_pdf, title="Test Book")
        for ch in chapters:
            assert "\n\n\n" not in ch["content"]

    def test_sections_have_content(self, simple_pdf):
        chapters, _ = extract_chapters_from_pdf(simple_pdf, title="Test Book")
        for ch in chapters:
            for sec in ch["sections"]:
                assert "title" in sec
                assert isinstance(sec["content"], str)


# ── extract_book_chapters (mocked Azure) ──────────────────────


class TestExtractBookChapters:
    def _pdf_bytes(self, tmp_path) -> bytes:
        pdf_path = _make_pdf(tmp_path, chapters=SAMPLE_CHAPTERS, add_bookmarks=True)
        with open(pdf_path, "rb") as f:
            return f.read()

    def test_downloads_and_extracts(self, tmp_path):
        pdf_bytes = self._pdf_bytes(tmp_path)

        mock_blob = MagicMock(spec=BlobService)
        mock_blob.download_file.return_value = pdf_bytes

        progress_messages: list[str] = []

        with patch(
            "app.modules.curricularalignmentarchitect.pdf_extraction.BlobService",
            return_value=mock_blob,
        ):
            chapters = extract_book_chapters(
                "books/test.pdf",
                on_progress=progress_messages.append,
            )

        assert len(chapters) >= 1
        assert len(progress_messages) >= 2
        mock_blob.download_file.assert_called_once_with("books/test.pdf")

        for ch in chapters:
            required = {
                "chapter_number",
                "title",
                "level",
                "start_page",
                "end_page",
                "sections",
                "content",
            }
            assert required.issubset(ch.keys())

    def test_progress_callback(self, tmp_path):
        pdf_bytes = self._pdf_bytes(tmp_path)

        mock_blob = MagicMock(spec=BlobService)
        mock_blob.download_file.return_value = pdf_bytes

        msgs: list[str] = []
        with patch(
            "app.modules.curricularalignmentarchitect.pdf_extraction.BlobService",
            return_value=mock_blob,
        ):
            extract_book_chapters("test.pdf", on_progress=msgs.append)

        assert any("Downloading" in m or "downloading" in m.lower() for m in msgs)
        assert any(
            "extract" in m.lower() or "fallback" in m.lower() or "tier" in m.lower()
            for m in msgs
        )


# ── _clean_title ──────────────────────────────────────────────


class TestCleanTitle:
    def test_strips_carriage_return(self):
        assert _clean_title("1\rWhat is Data Science?") == "1 What is Data Science?"

    def test_strips_tabs(self):
        assert _clean_title("Refresher\t 153") == "Refresher 153"

    def test_collapses_whitespace(self):
        assert _clean_title("  Big   Data  ") == "Big Data"

    def test_combined_junk(self):
        assert _clean_title("12\rBig\tData:\t Achieving\r Scale") == (
            "12 Big Data: Achieving Scale"
        )

    def test_already_clean(self):
        assert _clean_title("Chapter 1") == "Chapter 1"


# ── validate_extracted_chapters ───────────────────────────────


def _ch(num, title="Chapter", content="x" * 2000, pages=(1, 50)):
    """Minimal chapter dict for validation tests."""
    return {
        "chapter_number": num,
        "title": f"{title} {num}",
        "level": 1,
        "start_page": pages[0],
        "end_page": pages[1],
        "sections": [{"title": f"{title} {num}", "content": content}],
        "content": content,
    }


class TestValidateExtractedChapters:
    def test_valid_book(self):
        chapters = [_ch(i, pages=(i * 30, (i + 1) * 30)) for i in range(1, 8)]
        is_valid, reason = validate_extracted_chapters(chapters)
        assert is_valid
        assert reason == ""

    def test_empty_chapters(self):
        is_valid, reason = validate_extracted_chapters([])
        assert not is_valid
        assert "No chapters" in reason

    def test_too_few_chapters_large_book(self):
        chapters = [
            _ch(1, pages=(1, 100)),
            _ch(2, pages=(101, 200)),
        ]
        is_valid, reason = validate_extracted_chapters(chapters)
        assert not is_valid
        assert "Only 2 chapter(s)" in reason
        assert "200-page" in reason

    def test_few_chapters_small_book_is_ok(self):
        """A short PDF (< 50 pages) with 2 chapters is fine."""
        chapters = [
            _ch(1, pages=(1, 20)),
            _ch(2, pages=(21, 40)),
        ]
        is_valid, reason = validate_extracted_chapters(chapters)
        assert is_valid

    def test_toc_artifact_in_first_chapter(self):
        toc_content = "\n".join([f"Section {i}\t\t {100 + i}" for i in range(10)])
        chapters = [
            _ch(1, content=toc_content, pages=(1, 30)),
            _ch(2, pages=(31, 60)),
            _ch(3, pages=(61, 90)),
        ]
        is_valid, reason = validate_extracted_chapters(chapters)
        assert not is_valid
        assert "table-of-contents" in reason.lower()

    def test_toc_style_chapter_title(self):
        chapters = [
            {**_ch(1, pages=(1, 30)), "title": "Refresher\t 153"},
            _ch(2, pages=(31, 60)),
            _ch(3, pages=(61, 90)),
        ]
        is_valid, reason = validate_extracted_chapters(chapters)
        assert not is_valid
        assert "TOC entries" in reason

    def test_very_short_content(self):
        chapters = [
            _ch(i, content="short", pages=(i * 20, (i + 1) * 20)) for i in range(1, 5)
        ]
        is_valid, reason = validate_extracted_chapters(chapters)
        assert not is_valid
        assert "characters" in reason
