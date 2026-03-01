"""Shared PDF extraction module — extract once, consume twice.

Downloads PDFs from Azure Blob Storage, extracts chapter structure using
a 4-tier TOC fallback chain (Bookmarks → Printed TOC → Page Scan →
Whole-book) via pure **pypdf**.

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

import pypdf

from app.providers.storage import BlobService

logger = logging.getLogger(__name__)


# ── Type aliases ───────────────────────────────────────────────

TocEntry = tuple[int, str, int]  # (level, title, page_1based)

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
    """Normalise a chapter title extracted from PDF metadata.

    Strips carriage-returns, tab characters, and collapsed whitespace that
    leak from buggy bookmark / outline entries in some PDFs.
    """
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

    1. **Too few chapters** for a large book (< 3 chapters from 50+ pages).
    2. **TOC artifacts in content** — the first chapter's opening text
       contains many "title<tab>page-number" lines typical of a table of
       contents rather than real prose.
    3. **TOC-style chapter titles** — titles ending in a tab/spaces +
       page number (e.g. ``"Refresher\\t 153"``) which indicates the
       extraction picked up TOC lines instead of real chapter headings.
    4. **Very short chapters on average** (< 500 characters) — the PDF
       likely has no extractable text layer.
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

    return True, ""


def clean_chapter_for_llm(text: str) -> str:
    """Lightweight cleanup of raw pypdf chapter text before sending to an LLM.

    Composes on top of ``clean_extracted_text`` and additionally:
    - Rejoins remaining uppercase-starting hyphenated line breaks
    - Normalises runs of 3+ spaces/tabs to a single space
    """
    text = clean_extracted_text(text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # catch remaining uppercase hyphens
    text = re.sub(r"[ \t]{3,}", " ", text)  # normalize big whitespace runs
    return text


# ════════════════════════════════════════════════════════════════
# TOC Extraction — 4-Tier Fallback Chain
# ════════════════════════════════════════════════════════════════
#
#   Tier 1: PDF bookmarks  (pypdf outline)        — fast, most modern PDFs
#   Tier 2: Printed TOC     (text parsing)         — dvips / Ghostscript PDFs
#   Tier 3: Page-scan       (in-text headings)     — "Chapter N" at page tops
#   Tier 4: Whole-book      (single chapter)       — ultimate fallback
#
# ``get_toc()`` handles tiers 1-3; the caller handles tier 4.


def get_toc(
    reader: pypdf.PdfReader,
) -> tuple[list[TocEntry], int, str]:
    """Extract TOC + page count from an open PdfReader.

    Tries 3 tiers of extraction; the caller handles tier 4.

    Returns ``(toc, page_count, toc_source)`` where *toc_source* is one
    of ``"bookmarks"``, ``"printed_toc"``, ``"page_scan"``, or ``"none"``.
    """
    page_count = len(reader.pages)

    # ── Tier 1: PDF bookmarks ──────────────────────────────────
    outline = reader.outline if reader.outline else []

    def _flatten(items: list, level: int = 1) -> list[TocEntry]:
        results: list[TocEntry] = []
        for item in items:
            if isinstance(item, list):
                results.extend(_flatten(item, level + 1))
            else:
                title = item.get("/Title", "")
                try:
                    page = reader.get_destination_page_number(item) + 1
                except Exception:
                    page = 0
                results.append((level, title, page))
        return results

    toc = _flatten(outline)
    toc = [(lvl, t, p) for lvl, t, p in toc if p > 0 and t.strip()]
    if toc:
        logger.info("Tier 1 (bookmarks) → %d entries", len(toc))
        return toc, page_count, "bookmarks"

    # ── Tier 2: Printed TOC pages ──────────────────────────────
    toc = _parse_toc_from_text(reader, page_count)
    if toc:
        logger.info("Tier 2 (printed TOC) → %d entries", len(toc))
        return toc, page_count, "printed_toc"

    # ── Tier 3: In-text chapter headings ───────────────────────
    toc = _scan_chapter_headings(reader, page_count)
    if toc:
        logger.info("Tier 3 (page scan) → %d entries", len(toc))
        return toc, page_count, "page_scan"

    logger.warning("No TOC found by any tier")
    return [], page_count, "none"


# ────────────────────────────────────────────────────────────────
# Tier 2: Printed TOC Parser
# ────────────────────────────────────────────────────────────────

_TOC_CHAPTER_LINE = re.compile(
    r"^(\d{1,2})\s+"
    r"([A-Z][\s\S]+?)"
    r"\s+(\d{1,4})\s*$",
    re.MULTILINE,
)
_TOC_SECTION_LINE = re.compile(
    r"^(\d+\.\d+(?:\.\d+)*)\s+"
    r"(.+?)"
    r"\s*\.{3,}\s*"
    r"(\d{1,4})\s*$",
    re.MULTILINE,
)
_TOC_APPENDIX_LINE = re.compile(
    r"^([A-Z])\s{2,}"
    r"([A-Z][\s\S]+?)"
    r"\s+(\d{1,4})\s*$",
    re.MULTILINE,
)


def _parse_toc_from_text(
    reader: pypdf.PdfReader,
    page_count: int,
) -> list[TocEntry]:
    """Parse printed table-of-contents pages into ``(level, title, page)``."""

    # Step 1: identify TOC pages
    toc_page_indices: list[int] = []
    toc_started = False

    for pn in range(min(40, page_count)):
        text = reader.pages[pn].extract_text() or ""
        lines = text.strip().split("\n")
        if not lines:
            continue

        has_contents = any(
            re.search(r"\bcontents\b", line, re.IGNORECASE) for line in lines[:5]
        )
        dot_leaders = sum(1 for line in lines if re.search(r"\.{3,}\s*\d+", line))
        numbered = sum(1 for line in lines if re.match(r"\s*\d+\.\d+\s+", line))

        is_toc = (has_contents and (dot_leaders > 2 or numbered > 2)) or (
            toc_started and (dot_leaders > 3 or numbered > 3)
        )

        if is_toc:
            toc_started = True
            toc_page_indices.append(pn)
        elif toc_started:
            if not toc_page_indices or pn - toc_page_indices[-1] > 2:
                break

    if not toc_page_indices:
        return []

    # Step 2: join text + repair dvips artefacts
    raw_parts = [reader.pages[pn].extract_text() or "" for pn in toc_page_indices]
    toc_text = "\n".join(raw_parts)

    # Repair page numbers split across lines by dvips
    toc_text = re.sub(
        r"(\.{3,}\s*\d+)\s*\n(\d+)\s*$",
        r"\1\2",
        toc_text,
        flags=re.MULTILINE,
    )
    toc_text = re.sub(
        r"(\b[A-Z][\w\s,'-]+?\s+\d{1,3})\s*\n(\d{1,2})\s*$",
        r"\1\2",
        toc_text,
        flags=re.MULTILINE,
    )

    # Step 3: extract entries
    entries: list[TocEntry] = []
    seen: set[tuple[int, str]] = set()

    def _add(level: int, title: str, page: int) -> None:
        key = (level, title)
        if key not in seen and 0 < page <= page_count:
            seen.add(key)
            entries.append((level, title, page))

    def _clean(s: str) -> str:
        """Fix dvips broken spaces: 'F requent' → 'Frequent'."""
        return re.sub(r"([A-Z])\s([a-z])", r"\1\2", s.strip())

    for m in _TOC_CHAPTER_LINE.finditer(toc_text):
        _add(1, _clean(m.group(2)), int(m.group(3)))

    for m in _TOC_APPENDIX_LINE.finditer(toc_text):
        _add(1, f"Appendix {m.group(1)}: {_clean(m.group(2))}", int(m.group(3)))

    for m in _TOC_SECTION_LINE.finditer(toc_text):
        num_str = m.group(1)
        depth = num_str.count(".") + 1
        _add(depth, f"{num_str} {_clean(m.group(2))}", int(m.group(3)))

    entries.sort(key=lambda e: (e[2], e[0]))

    # Step 4: calibrate logical → physical page numbers
    entries = _calibrate_printed_toc(entries, reader, page_count, toc_page_indices)

    return entries


# ────────────────────────────────────────────────────────────────
# Printed TOC Page Calibration
# ────────────────────────────────────────────────────────────────
#
# Printed TOC pages show the book's OWN page numbering (e.g. "Chapter 1 … 1").
# In the physical PDF these are offset by front-matter pages (cover, preface,
# TOC itself).  We detect the offset by searching for the first chapter heading
# on the actual PDF pages and comparing its physical position to the logical
# page number from the TOC.

_CHAPTER_HEADING_RE = re.compile(
    r"^\s*(?:chapter|ch\.?)\s+(\d+|[IVXLC]+)",
    re.IGNORECASE,
)


def _calibrate_printed_toc(
    entries: list[TocEntry],
    reader: pypdf.PdfReader,
    page_count: int,
    toc_page_indices: list[int],
) -> list[TocEntry]:
    """Convert logical page numbers from a printed TOC to physical PDF pages.

    Searches for the first chapter heading (e.g. "Chapter 1") on physical
    pages after the TOC, compares that physical page to the logical page
    number from the TOC entry, and applies the offset to all entries.

    Returns the original entries unchanged if no offset is detectable.
    """
    if not entries:
        return entries

    ch_entries = [e for e in entries if e[0] == 1]
    if not ch_entries:
        return entries

    first_ch = ch_entries[0]
    target_logical_page = first_ch[2]
    target_title = first_ch[1].strip()
    title_words = [w.lower() for w in re.findall(r"[a-zA-Z]{3,}", target_title)]

    search_start = (max(toc_page_indices) + 1) if toc_page_indices else 0

    # Pass 1: look for "Chapter N" heading + title word match
    for phys_idx in range(search_start, min(page_count, search_start + 60)):
        text = reader.pages[phys_idx].extract_text() or ""
        first_lines = text.split("\n")[:8]
        combined = " ".join(first_lines).lower()

        has_heading = any(
            _CHAPTER_HEADING_RE.match(ln.strip()) for ln in first_lines[:5]
        )
        word_hits = sum(1 for w in title_words if w in combined) if title_words else 0
        title_match = word_hits >= max(1, min(len(title_words), 2))

        if has_heading and title_match:
            physical_page = phys_idx + 1  # convert to 1-based
            offset = physical_page - target_logical_page
            if offset > 0:
                calibrated = [
                    (lvl, title, page + offset)
                    for lvl, title, page in entries
                    if 1 <= page + offset <= page_count
                ]
                if calibrated:
                    logger.info(
                        "Printed TOC calibration: offset=%+d "
                        "(logical p.%d → physical p.%d for '%s')",
                        offset,
                        target_logical_page,
                        physical_page,
                        target_title,
                    )
                    return calibrated
            break  # if offset is 0, no calibration needed

    # Pass 2: title-only fallback (no "Chapter N" heading required)
    for phys_idx in range(search_start, min(page_count, search_start + 40)):
        text = reader.pages[phys_idx].extract_text() or ""
        first_lines = text.split("\n")[:5]
        combined = " ".join(first_lines).lower()

        if title_words and len(title_words) >= 2:
            word_hits = sum(1 for w in title_words if w in combined)
            if word_hits >= min(len(title_words), 3):
                physical_page = phys_idx + 1
                offset = physical_page - target_logical_page
                if offset > 0:
                    calibrated = [
                        (lvl, title, page + offset)
                        for lvl, title, page in entries
                        if 1 <= page + offset <= page_count
                    ]
                    if calibrated:
                        logger.info(
                            "Printed TOC calibration (title-only): offset=%+d",
                            offset,
                        )
                        return calibrated
                break

    return entries  # No calibration possible or needed


# ────────────────────────────────────────────────────────────────
# Tier 3: In-text Chapter Heading Scanner
# ────────────────────────────────────────────────────────────────

_HEADING_CHAPTER = re.compile(
    r"^\s*(?:chapter|ch\.?)\s+"
    r"(\d+|[IVXLC]+|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
    r"[\s:.\-—]*"
    r"(.+)?",
    re.IGNORECASE,
)
_HEADING_PART = re.compile(
    r"^\s*part\s+"
    r"(\d+|[IVXLC]+|one|two|three|four|five)"
    r"[\s:.\-—]*"
    r"(.+)?",
    re.IGNORECASE,
)
_HEADING_APPENDIX = re.compile(
    r"^\s*appendix\s+([A-Z\d])" r"[\s:.\-—]*" r"(.+)?",
    re.IGNORECASE,
)
_HEADING_NUMBERED = re.compile(
    r"^\s*(\d{1,2})\s*[.\s]\s*([A-Z][A-Za-z\s,'\-]{3,})\s*$",
)


def _scan_chapter_headings(
    reader: pypdf.PdfReader,
    page_count: int,
) -> list[TocEntry]:
    """Scan pages for chapter-heading patterns at the top of each page."""
    entries: list[TocEntry] = []
    seen_titles: set[str] = set()

    for pn in range(page_count):
        text = reader.pages[pn].extract_text() or ""
        lines = [line.strip() for line in text.split("\n")[:8] if line.strip()]
        if not lines:
            continue

        for line in lines[:5]:
            entry: TocEntry | None = None

            m = _HEADING_CHAPTER.match(line)
            if m:
                title = (m.group(2) or "").strip() or f"Chapter {m.group(1)}"
                entry = (1, title, pn + 1)

            if not entry:
                m = _HEADING_PART.match(line)
                if m:
                    title = (m.group(2) or "").strip() or f"Part {m.group(1)}"
                    entry = (
                        1,
                        f"Part {m.group(1)}: {title}" if m.group(2) else title,
                        pn + 1,
                    )

            if not entry:
                m = _HEADING_APPENDIX.match(line)
                if m:
                    title = (m.group(2) or "").strip() or f"Appendix {m.group(1)}"
                    entry = (1, f"Appendix {m.group(1)}: {title}", pn + 1)

            if not entry and line == lines[0]:
                m = _HEADING_NUMBERED.match(line)
                if m:
                    entry = (1, m.group(2).strip(), pn + 1)

            if entry:
                norm = entry[1].lower()
                if norm not in seen_titles:
                    seen_titles.add(norm)
                    entries.append(entry)
                break

    return entries if len(entries) >= 2 else []


# ════════════════════════════════════════════════════════════════
# Chapter Detection — 3-Strategy Cascade
# ════════════════════════════════════════════════════════════════

# Match "Chapter" only at the START of a title.
# Prevents false positives like "1.8 Chapter Notes" (a subsection, not a chapter).
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

MIN_CHAPTERS = 5
MAX_CHAPTERS = 30


def extract_chapters_from_pdf(
    pdf_path: str,
    title: str = "Untitled",
) -> tuple[list[dict], str]:
    """Extract structured chapters from a local PDF file.

    Uses the 4-tier TOC fallback chain:
      Tier 1 bookmarks → Tier 2 printed TOC → Tier 3 page scan
      → Tier 4 whole-book

    Returns ``(chapters, extraction_method)`` where *chapters* is a list
    of dicts with keys: ``chapter_number``, ``title``, ``level``,
    ``start_page``, ``end_page``, ``sections`` (``[{title, content}]``),
    ``content``.

    All chapter content is cleaned via ``clean_chapter_for_llm()``.
    """
    reader = pypdf.PdfReader(pdf_path)
    page_count = len(reader.pages)
    page_texts = [reader.pages[pn].extract_text() or "" for pn in range(page_count)]

    toc, _, toc_source = get_toc(reader)

    # ── Tier 4: Whole-book fallback ────────────────────────────
    if not toc:
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

    # ── Build hierarchy entries with content ───────────────────
    items: list[dict] = []
    for i, (level, entry_title, start_page) in enumerate(toc):
        end_page = toc[i + 1][2] - 1 if i + 1 < len(toc) else page_count
        end_page = max(start_page, end_page)
        items.append(
            {
                "level": int(level),
                "title": _clean_title(str(entry_title)),
                "start_page": int(start_page),
                "end_page": int(end_page),
            }
        )

    # Attach page text to each entry
    entries: list[dict] = []
    for item in items:
        start_idx = max(0, item["start_page"] - 1)
        end_idx = min(item["end_page"], page_count)
        content = "\n\n".join(page_texts[start_idx:end_idx])
        entries.append({**item, "content": content})

    # ── Detect chapters ────────────────────────────────────────
    chapter_indices = detect_chapter_indices(entries)

    if not chapter_indices:
        min_level = min(e["level"] for e in entries)
        chapter_indices = [i for i, e in enumerate(entries) if e["level"] == min_level]

    if not chapter_indices:
        full_text = clean_chapter_for_llm("\n\n".join(page_texts))
        logger.warning("No chapters detected for '%s' — whole-book fallback", title)
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

    # ── Build chapter dicts with sections ──────────────────────
    chapters: list[dict] = []

    for pos, ch_idx in enumerate(chapter_indices):
        ch_entry = entries[ch_idx]
        boundary = (
            chapter_indices[pos + 1] if pos + 1 < len(chapter_indices) else len(entries)
        )
        children = entries[ch_idx + 1 : boundary]
        last_entry = children[-1] if children else ch_entry

        # Build sections from children; if no children, the chapter itself
        # is a single section.
        if children:
            sections = [
                {"title": c["title"], "content": clean_chapter_for_llm(c["content"])}
                for c in children
            ]
            # Prepend an intro section if the chapter's own page range extends
            # before its first child.
            if ch_entry["start_page"] < children[0]["start_page"]:
                intro_start = max(0, ch_entry["start_page"] - 1)
                intro_end = min(children[0]["start_page"] - 1, page_count)
                intro_text = "\n\n".join(page_texts[intro_start:intro_end])
                cleaned_intro = clean_chapter_for_llm(intro_text)
                if cleaned_intro:
                    sections.insert(
                        0, {"title": ch_entry["title"], "content": cleaned_intro}
                    )
        else:
            sections = [
                {
                    "title": ch_entry["title"],
                    "content": clean_chapter_for_llm(ch_entry["content"]),
                }
            ]

        combined = "\n\n".join(s["content"] for s in sections if s["content"])
        if len(combined) < 100:
            continue

        chapters.append(
            {
                "chapter_number": pos + 1,
                "title": ch_entry["title"],
                "level": ch_entry["level"],
                "start_page": ch_entry["start_page"],
                "end_page": last_entry["end_page"],
                "sections": sections,
                "content": combined,
            }
        )

    if chapters:
        logger.info("%s → %d chapters from '%s'", toc_source, len(chapters), title)
        return chapters, toc_source

    # Edge-case: TOC found but no viable chapters after filtering
    full_text = clean_chapter_for_llm("\n\n".join(page_texts))
    logger.warning("TOC found but 0 viable chapters for '%s' — fallback", title)
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

    try:
        _report("Extracting chapters (4-tier TOC fallback)…")
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
# These were part of the old API surface. Keep them importable but
# they are no longer used by the main extraction pipeline.


def extract_toc_entries(pdf_path: str) -> list[dict]:
    """Extract TOC metadata from a PDF file (legacy compat).

    Returns list of dicts: ``{level, title, start_page, end_page}``
    """
    reader = pypdf.PdfReader(pdf_path)
    toc, page_count, _ = get_toc(reader)
    items: list[dict] = []
    for i, (level, entry_title, start_page) in enumerate(toc):
        end_page = toc[i + 1][2] - 1 if i + 1 < len(toc) else page_count
        end_page = max(start_page, end_page)
        items.append(
            {
                "level": int(level),
                "title": _clean_title(str(entry_title)),
                "start_page": int(start_page),
                "end_page": int(end_page),
            }
        )
    return items


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
