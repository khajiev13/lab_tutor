"""Shared PDF extraction module — extract once, consume twice.

Downloads PDFs from Azure Blob Storage, extracts chapter structure using
a 3-strategy fallback chain (Bookmarks → Heading Detection → Page Chunking)
via **pypdf** + **pdfplumber**.

Each chapter contains sections with **populated text content**, cleaned
via ``clean_chapter_for_llm()`` before being returned.

Both the chunking pipeline and the agentic extraction pipeline read from
the stored BookChapter rows instead of re-downloading and re-extracting.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import tempfile
from collections import Counter
from collections.abc import Callable

import pdfplumber
import pypdf

from app.providers.storage import BlobService

logger = logging.getLogger(__name__)


# ── Boilerplate / skip titles ──────────────────────────────────

_BOILERPLATE_TITLES = frozenset(
    {
        "index",
        "bibliography",
        "references",
        "acknowledgements",
        "acknowledgments",
        "foreword",
        "preface",
        "appendix",
        "glossary",
        "about the author",
        "about the authors",
        "copyright",
        "dedication",
        "table of contents",
        "contents",
        "cover",
        "colophon",
        "about the publisher",
        "about the technical reviewer",
        "list of figures",
        "list of tables",
        "list of abbreviations",
        "contents at a glance",
        "title page",
        "about this book",
        "introduction",
        "notation",
        "symbols",
        "acronyms",
    }
)


def _is_boilerplate(title: str) -> bool:
    return title.strip().lower() in _BOILERPLATE_TITLES


# ── Text cleaning ──────────────────────────────────────────────

_PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$")
_DOT_LEADER_RE = re.compile(r"[.\s]{4,}")
_HEADER_REPEAT_FRACTION = 0.02


def _is_toc_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 120:
        return False
    if not re.search(r"\d{1,4}\s*$", s):
        return False
    m = _DOT_LEADER_RE.search(s)
    return bool(m) and m.group().count(".") >= 2


def clean_extracted_text(text: str) -> str:
    """Remove TOC lines, lone page numbers, broken hyphens, noisy headers."""
    # Strip NUL bytes and non-printable control chars (except \n, \r, \t)
    # that break PostgreSQL TEXT columns and pollute LLM context.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    lines = [
        line
        for line in text.splitlines()
        if not _PAGE_NUM_RE.fullmatch(line) and not _is_toc_line(line)
    ]
    text = "\n".join(lines)
    text = re.sub(r"-\n([a-z])", r"\1", text)

    lines = text.splitlines()
    non_empty = [row.strip() for row in lines if len(row.strip()) > 4]
    threshold = max(5, int(len(non_empty) * _HEADER_REPEAT_FRACTION))
    noisy = {val for val, cnt in Counter(non_empty).items() if cnt >= threshold}
    if noisy:
        lines = [row for row in lines if row.strip() not in noisy]
        text = "\n".join(lines)

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip()


def _clean_title(title: str) -> str:
    """Normalise a chapter title extracted from PDF metadata."""
    title = title.replace("\r", " ").replace("\t", " ")
    title = re.sub(r"\s+", " ", title)
    return title.strip()


# ── Chapter quality validation ─────────────────────────────────

# Regex: line ending in <tab-or-spaces><1-4 digit number> — TOC artifact
_TOC_LINE_ARTIFACT_RE = re.compile(r"^.+[\t ]{2,}\d{1,4}\s*$", re.MULTILINE)


def validate_extracted_chapters(
    chapters: list[dict],
) -> tuple[bool, str]:
    """Check whether extracted chapters represent a properly parsed book.

    Returns ``(is_valid, reason)``.  A book is flagged as corrupted when:

    1. **No chapters** extracted at all.
    2. **Too few chapters** for a large book (< 3 chapters from 50+ pages).
    3. **TOC artifacts in content** — the first chapter's opening text
       contains many "title<tab>page-number" lines typical of a table of
       contents rather than real prose.
    4. **TOC-style chapter titles** — titles ending in a tab/spaces +
       page number (e.g. ``"Refresher\\t 153"``) which indicates the
       extraction picked up TOC lines instead of real chapter headings.
    5. **Very short chapters on average** (< 500 characters) — the PDF
       likely has no extractable text layer.
    6. **Chapters missing sections** — every chapter must have at least
       one section with non-empty content.
    """
    if not chapters:
        return False, "No chapters extracted"

    page_count = max(ch.get("end_page", 0) for ch in chapters)

    # 1. Too few chapters for a sizeable book
    if len(chapters) < 3 and page_count > 50:
        return False, (
            f"Only {len(chapters)} chapter(s) extracted from a "
            f"{page_count}-page book — likely a corrupted or incomplete PDF"
        )

    # 2. TOC artifacts in the first chapter's opening text
    first_content = chapters[0].get("content", "")[:1500]
    toc_hits = _TOC_LINE_ARTIFACT_RE.findall(first_content)
    if len(toc_hits) >= 5:
        return False, (
            f"First chapter contains {len(toc_hits)} table-of-contents "
            f"artifact lines — PDF structure is corrupted"
        )

    # 3. Chapter titles that look like TOC entries
    bad_titles = [
        ch["title"]
        for ch in chapters
        if re.search(r"[\t ]{2,}\d{1,4}\s*$", ch.get("title", ""))
    ]
    if bad_titles:
        return False, (
            f"{len(bad_titles)} chapter title(s) look like TOC entries: "
            f"{bad_titles[0]!r}"
        )

    # 4. Average content too short — no real text layer
    avg_len = sum(len(ch.get("content", "")) for ch in chapters) / len(chapters)
    if avg_len < 500:
        return False, (
            f"Average chapter length is only {avg_len:.0f} characters — "
            f"PDF may not contain extractable text"
        )

    # 5. Every chapter must have sections with actual content
    empty_chapters: list[str] = []
    for ch in chapters:
        sections = ch.get("sections", [])
        has_content = any(len((s.get("content") or "").strip()) > 0 for s in sections)
        if not sections or not has_content:
            empty_chapters.append(ch.get("title", "?"))

    if empty_chapters:
        return False, (
            f"{len(empty_chapters)} chapter(s) have no sections with content: "
            f"{empty_chapters[0]!r}"
        )

    return True, ""


def clean_chapter_for_llm(text: str) -> str:
    """Lightweight cleanup of raw chapter text before sending to an LLM."""
    text = clean_extracted_text(text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]{3,}", " ", text)
    return text


# ════════════════════════════════════════════════════════════════
# RobustPDFExtractor — 3-strategy fallback chain
# ════════════════════════════════════════════════════════════════
#
#   Strategy 1: PDF bookmarks    (pypdf outline)  — most modern PDFs
#   Strategy 2: Heading detection (pdfplumber)     — text heading patterns
#   Strategy 3: Page chunking    (pypdf)           — ultimate fallback


_BACK_MATTER_RE = re.compile(
    r"^(bibliography|references|back\s*cover|index|glossary"
    r"|about\s+the\s+authors?|colophon)\b",
    re.IGNORECASE,
)


class _RobustPDFExtractor:
    """Multi-strategy PDF extractor that always produces structured output."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.filename = os.path.basename(pdf_path)
        self.reader: pypdf.PdfReader | None = None
        self.total_pages = 0

    def extract(self) -> dict:
        """Main extraction with fallback strategies."""
        try:
            self.reader = pypdf.PdfReader(self.pdf_path)
            self.total_pages = len(self.reader.pages)
        except Exception as e:
            return {"error": f"Failed to open PDF: {e!s}"}

        # Strategy 1: bookmark-based
        result = self._extract_from_bookmarks()
        if result and len(result["chapters"]) > 0:
            result["chapters"] = self._filter_to_real_chapters(result["chapters"])
            logger.info(
                "Strategy 1 (bookmarks) → %d chapters for '%s'",
                len(result["chapters"]),
                self.filename,
            )
            return result

        # Strategy 2: heading detection
        result = self._extract_from_headings()
        if result and len(result["chapters"]) > 0:
            result["chapters"] = self._filter_to_real_chapters(result["chapters"])
            logger.info(
                "Strategy 2 (headings) → %d chapters for '%s'",
                len(result["chapters"]),
                self.filename,
            )
            return result

        # Strategy 3: page chunking fallback
        result = self._extract_by_pages()
        logger.info(
            "Strategy 3 (page chunks) → %d chunks for '%s'",
            len(result["chapters"]),
            self.filename,
        )
        return result

    @staticmethod
    def _filter_to_real_chapters(chapters: list[dict]) -> list[dict]:
        """Drop front/back matter, keeping only real chapters."""
        while chapters and _BACK_MATTER_RE.match(chapters[-1]["title"].strip()):
            chapters.pop()

        start = 0
        for i, ch in enumerate(chapters):
            title = ch["title"].strip()
            if re.match(r"^(Chapter\s+1\b|CHAPTER\s+1\b|1[\s.:]\s*\S)", title):
                start = i
                break
        chapters = chapters[start:]

        if chapters:
            first_title = chapters[0]["title"].strip()
            if re.match(r"^(Chapter|CHAPTER)\s+\d+", first_title):
                pattern = re.compile(r"^(Chapter|CHAPTER)\s+\d+")
            elif re.match(r"^\d+[\s.:]", first_title):
                pattern = re.compile(r"^\d+[\s.:]")
            else:
                pattern = None

            if pattern:
                end = len(chapters)
                for j in range(len(chapters) - 1, -1, -1):
                    if pattern.match(chapters[j]["title"].strip()):
                        end = j + 1
                        break
                chapters = chapters[:end]

        return chapters

    # ── Strategy 1: Bookmarks ──────────────────────────────────

    def _extract_from_bookmarks(self) -> dict | None:
        try:
            assert self.reader is not None
            outline = self.reader.outline
            if not outline or len(outline) == 0:
                return None

            bookmarks = self._parse_outline(outline)
            if not bookmarks:
                return None

            chapters: list[dict] = []
            current_chapter: dict | None = None

            for bm in bookmarks:
                if bm["level"] == 1:
                    if current_chapter:
                        chapters.append(current_chapter)
                    current_chapter = {
                        "title": _clean_title(bm["title"]),
                        "start_page": bm["page_num"],
                        "sections": [],
                        "method": "bookmarks",
                    }
                elif bm["level"] == 2 and current_chapter:
                    current_chapter["sections"].append(
                        {
                            "title": _clean_title(bm["title"]),
                            "start_page": bm["page_num"],
                        }
                    )

            if current_chapter:
                chapters.append(current_chapter)

            # Merge split bookmark titles for numbered sections
            for chapter in chapters:
                secs = chapter["sections"]
                if not secs:
                    continue
                numbered_count = sum(
                    1 for s in secs if re.match(r"^\d+\.\d+", s["title"].strip())
                )
                if numbered_count < len(secs) * 0.5:
                    continue

                merged: list[dict] = []
                for sec in secs:
                    title = sec["title"].strip()
                    is_numbered = re.match(r"^\d+\.\d+", title)
                    if (
                        not is_numbered
                        and merged
                        and sec["start_page"] == merged[-1]["start_page"]
                    ):
                        merged[-1]["title"] = merged[-1]["title"].rstrip() + " " + title
                    else:
                        merged.append(sec)
                chapter["sections"] = merged

            # Extract text for each chapter/section
            for i, chapter in enumerate(chapters):
                end_page = (
                    chapters[i + 1]["start_page"]
                    if i + 1 < len(chapters)
                    else self.total_pages
                )

                if chapter["sections"]:
                    for j, section in enumerate(chapter["sections"]):
                        sec_start = section["start_page"]
                        sec_end = (
                            chapter["sections"][j + 1]["start_page"]
                            if j + 1 < len(chapter["sections"])
                            else end_page
                        )
                        sec_end = max(sec_start + 1, sec_end)
                        section["text"] = self._extract_text_range(sec_start, sec_end)
                else:
                    chapter["text"] = self._extract_text_range(
                        chapter["start_page"], end_page
                    )

            # If no level-2 sections found, detect from text
            has_any_sections = any(ch["sections"] for ch in chapters)
            if not has_any_sections:
                self._detect_sections_in_chapters(chapters)

            return {
                "filename": self.filename,
                "total_pages": self.total_pages,
                "extraction_method": "bookmarks",
                "chapters": chapters,
            }

        except Exception as e:
            logger.warning("Bookmark extraction error: %s", e)
            return None

    def _detect_sections_in_chapters(self, chapters: list[dict]) -> None:
        """Detect numbered sections (N.N) within each chapter using pdfplumber."""
        with pdfplumber.open(self.pdf_path) as pdf:
            for ch_idx, chapter in enumerate(chapters):
                start = chapter["start_page"]
                end = (
                    chapters[ch_idx + 1]["start_page"]
                    if ch_idx + 1 < len(chapters)
                    else self.total_pages
                )

                sections: list[dict] = []
                for page_num in range(start, min(end, len(pdf.pages))):
                    text = pdf.pages[page_num].extract_text()
                    if not text:
                        continue
                    for line in text.split("\n"):
                        line = line.strip()
                        if (
                            re.match(r"^(\d+\.\d+)\s+([A-Za-z].+)", line)
                            and len(line) < 100
                        ):
                            sections.append({"title": line, "start_page": page_num})

                if sections:
                    for j, sec in enumerate(sections):
                        sec_start = sec["start_page"]
                        sec_end = (
                            sections[j + 1]["start_page"]
                            if j + 1 < len(sections)
                            else end
                        )
                        sec_end = max(sec_start + 1, sec_end)
                        sec["text"] = self._extract_text_range(sec_start, sec_end)
                    chapter["sections"] = sections
                    chapter.pop("text", None)

    # ── Strategy 2: Heading Detection ──────────────────────────

    def _extract_from_headings(self) -> dict | None:
        try:
            chapters: list[dict] = []
            current_chapter: dict | None = None

            with pdfplumber.open(self.pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if not text:
                        continue

                    lines = text.split("\n")

                    for line_idx, line in enumerate(lines):
                        line = line.strip()

                        chapter_match = re.match(
                            r"^(Chapter\s+\d+|CHAPTER\s+\d+)\s*$"
                            r"|^(Chapter\s+\d+|CHAPTER\s+\d+)\s*[:.\-]\s*\S",
                            line,
                        )
                        if chapter_match and len(line) < 100:
                            title = line
                            is_standalone = re.match(
                                r"^(Chapter\s+\d+|CHAPTER\s+\d+)\s*$", line
                            )
                            if is_standalone and line_idx + 1 < len(lines):
                                next_line = lines[line_idx + 1].strip()
                                if next_line and len(next_line) < 80:
                                    title = f"{line}: {next_line}"

                            if current_chapter:
                                chapters.append(current_chapter)
                            current_chapter = {
                                "title": title,
                                "start_page": page_num,
                                "sections": [],
                                "text": "",
                                "method": "heading_detection",
                            }

                        elif current_chapter:
                            section_match = re.match(
                                r"^(\d+\.\d+)\s+([A-Za-z].+)", line
                            )
                            if section_match and len(line) < 100:
                                current_chapter["sections"].append(
                                    {
                                        "title": line,
                                        "start_page": page_num,
                                        "text": "",
                                    }
                                )

                    if current_chapter:
                        if current_chapter["sections"]:
                            current_chapter["sections"][-1]["text"] += text + "\n\n"
                        else:
                            current_chapter["text"] += text + "\n\n"

            if current_chapter:
                chapters.append(current_chapter)

            chapters = [
                ch for ch in chapters if len(ch.get("text", "")) > 100 or ch["sections"]
            ]

            # Fix 0-text sections
            for ch in chapters:
                for j, sec in enumerate(ch.get("sections", [])):
                    if sec.get("text", "").strip():
                        continue
                    sec_start = sec["start_page"]
                    sec_end = (
                        ch["sections"][j + 1]["start_page"]
                        if j + 1 < len(ch["sections"])
                        else sec_start + 1
                    )
                    sec_end = max(sec_start + 1, sec_end)
                    sec["text"] = self._extract_text_range(sec_start, sec_end)

            if len(chapters) < 3:
                return None

            return {
                "filename": self.filename,
                "total_pages": self.total_pages,
                "extraction_method": "heading_detection",
                "chapters": chapters,
            }

        except Exception as e:
            logger.warning("Heading detection error: %s", e)
            return None

    # ── Strategy 3: Page Chunking ──────────────────────────────

    def _extract_by_pages(self, pages_per_chunk: int = 15) -> dict:
        chapters: list[dict] = []

        for i in range(0, self.total_pages, pages_per_chunk):
            end_page = min(i + pages_per_chunk, self.total_pages)
            text = self._extract_text_range(i, end_page)

            chapters.append(
                {
                    "title": f"Pages {i + 1}-{end_page}",
                    "start_page": i,
                    "sections": [],
                    "text": text,
                    "method": "page_chunks",
                }
            )

        return {
            "filename": self.filename,
            "total_pages": self.total_pages,
            "extraction_method": "page_chunks",
            "chapters": chapters,
        }

    # ── Outline parsing ────────────────────────────────────────

    def _parse_outline(self, outline: list, level: int = 1) -> list[dict]:
        """Parse PDF outline recursively, flatten to 2 levels max."""
        items: list[dict] = []
        if not outline:
            return items

        for item in outline:
            if isinstance(item, list):
                if level < 2:
                    items.extend(self._parse_outline(item, level + 1))
            else:
                try:
                    title = (
                        item.title
                        if hasattr(item, "title")
                        else str(item.get("/Title", "Untitled"))
                    )
                    page_obj = item.page if hasattr(item, "page") else item.get("/Page")
                    page_num = self._get_page_number(page_obj)

                    if level <= 2:
                        items.append(
                            {
                                "level": level,
                                "title": title,
                                "page_num": page_num,
                            }
                        )
                except Exception:
                    continue

        return items

    def _get_page_number(self, page_obj: object) -> int:
        """Extract page number from page object."""
        if page_obj is None:
            return 0
        if isinstance(page_obj, int):
            return page_obj

        assert self.reader is not None
        try:
            for i, page in enumerate(self.reader.pages):
                if page == page_obj or str(page) == str(page_obj):
                    return i
        except Exception:
            pass
        return 0

    def _extract_text_range(self, start_page: int, end_page: int) -> str:
        """Extract text from page range using pypdf."""
        assert self.reader is not None
        text = ""
        try:
            for page_num in range(start_page, min(end_page, self.total_pages)):
                page = self.reader.pages[page_num]
                text += page.extract_text() or ""
                text += "\n\n---\n\n"
        except Exception as e:
            logger.warning("Error extracting pages %d-%d: %s", start_page, end_page, e)

        return text.strip()


# ════════════════════════════════════════════════════════════════
# Adapter: convert raw extractor output → consumer contract
# ════════════════════════════════════════════════════════════════


def _adapt_to_chapter_contract(raw_result: dict) -> tuple[list[dict], str]:
    """Convert _RobustPDFExtractor output to the standard chapter contract.

    Consumer contract per chapter:
      chapter_number, title, level, start_page (1-based), end_page (1-based),
      sections: [{title, content}], content
    """
    if "error" in raw_result:
        return [], "error"

    method = raw_result["extraction_method"]
    total_pages = raw_result["total_pages"]
    raw_chapters = raw_result["chapters"]

    chapters: list[dict] = []

    for idx, ch in enumerate(raw_chapters):
        sections: list[dict] = []
        if ch.get("sections"):
            for sec in ch["sections"]:
                sec_text = sec.get("text", "") or sec.get("content", "")
                cleaned = clean_chapter_for_llm(sec_text)
                if cleaned:
                    sections.append(
                        {"title": _clean_title(sec["title"]), "content": cleaned}
                    )
        else:
            ch_text = ch.get("text", "") or ch.get("content", "")
            cleaned = clean_chapter_for_llm(ch_text)
            if cleaned:
                sections.append(
                    {"title": _clean_title(ch["title"]), "content": cleaned}
                )

        if not sections:
            continue

        combined = "\n\n".join(s["content"] for s in sections)
        start_page_1 = ch.get("start_page", 0) + 1

        if idx + 1 < len(raw_chapters):
            end_page_1 = raw_chapters[idx + 1].get("start_page", total_pages)
        else:
            end_page_1 = total_pages
        end_page_1 = max(start_page_1, end_page_1)

        chapters.append(
            {
                "chapter_number": len(chapters) + 1,
                "title": _clean_title(ch["title"]),
                "level": 1,
                "start_page": start_page_1,
                "end_page": end_page_1,
                "sections": sections,
                "content": combined,
            }
        )

    return chapters, method


# ════════════════════════════════════════════════════════════════
# Chapter detection helpers (kept for API compatibility)
# ════════════════════════════════════════════════════════════════

_CHAPTER_TITLE_START = re.compile(
    r"^\s*(?:chapter|capítulo|chapitre|kapitel|capitolo|глава|bab|hoofdstuk)\b",
    re.IGNORECASE,
)
_CHAPTER_FALSE_POSITIVES = re.compile(
    r"\b(summary|quiz|review|exercises|problems|questions|objectives)\b",
    re.IGNORECASE,
)
_APPENDIX_KEYWORDS = re.compile(
    r"\b(appendix|appendice|anhang|annexe|apéndice|приложение)\b",
    re.IGNORECASE,
)
_ROMAN_NUMERAL = r"(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
_NUMBERED_PREFIX = re.compile(
    rf"^(?:\d+|{_ROMAN_NUMERAL}|[A-Z])[\.\s:\-]",
    re.IGNORECASE,
)


def detect_chapter_indices(
    entries: list[dict],
    *,
    include_appendices: bool = True,
) -> list[int]:
    """Auto-detect which TOC entries are chapters.

    Priority cascade:
      1. Chapter keyword (multilingual) — requires >= 2 matches
      2. Numbered top-level (Arabic / Roman / Letter)
      3. Fallback: all top-level, excluding front/back matter
    """
    if not entries:
        return []

    min_level = min(e["level"] for e in entries)

    # Strategy 1: chapter keyword at START of title
    chapter_idxs = [
        i
        for i, e in enumerate(entries)
        if _CHAPTER_TITLE_START.match(e["title"])
        and not _CHAPTER_FALSE_POSITIVES.search(e["title"])
        and not _is_boilerplate(e["title"])
    ]
    if len(chapter_idxs) >= 2:
        if include_appendices:
            app_idxs = [
                i
                for i, e in enumerate(entries)
                if _APPENDIX_KEYWORDS.search(e["title"])
                and not _is_boilerplate(e["title"])
                and i not in chapter_idxs
            ]
            chapter_idxs = sorted(chapter_idxs + app_idxs)
        return chapter_idxs

    # Strategy 2: numbered top-level
    chapter_idxs = [
        i
        for i, e in enumerate(entries)
        if e["level"] == min_level
        and _NUMBERED_PREFIX.match(e["title"])
        and not _is_boilerplate(e["title"])
    ]
    if chapter_idxs:
        if include_appendices:
            app_idxs = [
                i
                for i, e in enumerate(entries)
                if _APPENDIX_KEYWORDS.search(e["title"])
                and not _is_boilerplate(e["title"])
                and i not in chapter_idxs
            ]
            chapter_idxs = sorted(chapter_idxs + app_idxs)
        return chapter_idxs

    # Strategy 3: all top-level, excluding front/back matter
    return [
        i
        for i, e in enumerate(entries)
        if e["level"] == min_level and not _is_boilerplate(e["title"])
    ]


# ════════════════════════════════════════════════════════════════
# Orchestrator (local file)
# ════════════════════════════════════════════════════════════════


def extract_chapters_from_pdf(
    pdf_path: str,
    title: str = "Untitled",
) -> tuple[list[dict], str]:
    """Extract structured chapters from a local PDF file.

    Uses a 3-strategy fallback chain via ``_RobustPDFExtractor``:
      1. PDF bookmarks (pypdf outline)
      2. Heading detection (pdfplumber)
      3. Page chunking (pypdf)

    Returns ``(chapters, extraction_method)`` where *chapters* is a list
    of dicts with keys: ``chapter_number``, ``title``, ``level``,
    ``start_page``, ``end_page``, ``sections`` (``[{title, content}]``),
    ``content``.
    """
    extractor = _RobustPDFExtractor(pdf_path)
    raw_result = extractor.extract()

    chapters, method = _adapt_to_chapter_contract(raw_result)

    if not chapters:
        reader = pypdf.PdfReader(pdf_path)
        page_count = len(reader.pages)
        page_texts = [reader.pages[pn].extract_text() or "" for pn in range(page_count)]
        full_text = clean_chapter_for_llm("\n\n".join(page_texts))
        logger.warning("Fallback (whole-book) for '%s'", title)
        return [
            {
                "chapter_number": 1,
                "title": title,
                "level": 1,
                "start_page": 1,
                "end_page": page_count,
                "sections": [{"title": title, "content": full_text}],
                "content": full_text,
            }
        ], "fallback"

    logger.info("%s → %d chapters for '%s'", method, len(chapters), title)
    return chapters, method


# ════════════════════════════════════════════════════════════════
# Public entry point (Azure Blob download)
# ════════════════════════════════════════════════════════════════

ProgressCallback = Callable[[str], None]


def extract_book_chapters(
    blob_path: str,
    *,
    on_progress: ProgressCallback | None = None,
) -> list[dict]:
    """Download a book PDF from Azure Blob and extract chapters.

    Single extraction entry point for the entire application.

    Args:
        blob_path: Azure Blob path to the PDF.
        on_progress: Optional callback invoked with a human-readable
            progress message at each meaningful step.

    Returns list of chapter dicts with keys:
      chapter_number, title, level, start_page, end_page, sections, content
    """
    _report = on_progress or (lambda _msg: None)

    _report("Downloading PDF…")
    blob_service = BlobService()
    pdf_bytes = blob_service.download_file(blob_path)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        tmp_path = tmp.name

    # Free download buffer before extraction to reduce peak memory
    del pdf_bytes

    try:
        _report("Extracting chapters (bookmarks → headings → page chunks)…")
        title = os.path.splitext(os.path.basename(blob_path))[0].replace("_", " ")
        chapters, method = extract_chapters_from_pdf(tmp_path, title=title)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

    total_sections = sum(len(ch["sections"]) for ch in chapters)
    logger.info(
        "Extracted %d chapters (%d sections) via %s from '%s'",
        len(chapters),
        total_sections,
        method,
        blob_path,
    )

    for ch in chapters:
        _report(f"Chapter {ch['chapter_number']}/{len(chapters)}: {ch['title']}")

    return chapters


# ════════════════════════════════════════════════════════════════
# Backward-compat re-exports
# ════════════════════════════════════════════════════════════════


def extract_toc_entries(pdf_path: str) -> list[dict]:
    """Extract TOC metadata from a PDF file (legacy compat).

    Returns list of dicts: ``{level, title, start_page, end_page}``
    """
    chapters, _ = extract_chapters_from_pdf(pdf_path)
    return [
        {
            "level": ch["level"],
            "title": ch["title"],
            "start_page": ch["start_page"],
            "end_page": ch["end_page"],
        }
        for ch in chapters
    ]


def extract_full_markdown(pdf_path: str) -> str:
    """Legacy: read all pages as plain text."""
    reader = pypdf.PdfReader(pdf_path)
    page_texts = [page.extract_text() or "" for page in reader.pages]
    return clean_extracted_text("\n\n".join(page_texts))


def filter_pdf_pages(pdf_path: str) -> tuple[list[int], list[int]]:
    """Return ``(good_pages, skipped_pages)`` — legacy compat."""
    good: list[int] = []
    skipped: list[int] = []
    reader = pypdf.PdfReader(pdf_path)
    for i, page in enumerate(reader.pages):
        text_chars = len((page.extract_text() or "").strip())
        if text_chars < 50 or text_chars > 15_000:
            skipped.append(i)
        else:
            good.append(i)
    return good, skipped


def split_markdown_by_chapters(md_text: str, toc_entries: list[dict]) -> list[dict]:
    """Legacy: split text by TOC. Prefer ``extract_chapters_from_pdf``."""
    return [
        {
            "chapter_number": 1,
            "title": "Full Document",
            "level": 1,
            "start_page": 1,
            "end_page": 0,
            "sections": [],
            "content": md_text,
        }
    ]


def strip_book_matter(text: str) -> str:
    """Strip front/back matter — legacy compat (no-op)."""
    return text
