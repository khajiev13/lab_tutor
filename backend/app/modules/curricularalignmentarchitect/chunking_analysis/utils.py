"""Utility helpers for chunking analysis phase."""

from __future__ import annotations

import re
from collections import Counter

import numpy as np
from neo4j import GraphDatabase

from app.core.settings import settings

from .state import CHUNK_OVERLAP, CHUNK_SIZE, MAX_TEXT_CHARS, MIN_TEXT_CHARS, SEPARATORS


def filter_pdf_pages(pdf_path: str) -> tuple[list[int], list[int]]:
    """Use fitz to inspect each page and return (good_pages, skipped_pages).

    good_pages  — page indices to pass to pymupdf4llm (text-rich, not anomalous)
    skipped_pages — image-only or malformed pages excluded from extraction
    """
    import fitz  # pymupdf (installed with pymupdf4llm)

    good: list[int] = []
    skipped: list[int] = []
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc):
            text_chars = len(page.get_text("text").strip())
            if text_chars < MIN_TEXT_CHARS or text_chars > MAX_TEXT_CHARS:
                skipped.append(i)
            else:
                good.append(i)
    finally:
        doc.close()
    return good, skipped


def strip_book_matter(text: str) -> str:
    """Strip front matter (TOC, preface) and back matter (index, bibliography)."""
    front_patterns = [
        r"(?m)^#{1,4}\s*(chapter|Chapter|CHAPTER)\s+[1iI]\b",
        r"(?m)^(Chapter|CHAPTER)\s+1\b",
        r"(?m)^#{1,4}\s*(Part|PART)\s+[1iI]\b",
        r"(?m)^(Part|PART)\s+[1iI]\b",
        r"(?m)^#{1,4}\s+1[\.\s]",
        r"(?m)^#{1,4}\s+\*\*1\*\*",
        r"(?m)^#{1,4}\s+Introduction\b",
    ]
    content_start = None
    for pat in front_patterns:
        m = re.search(pat, text)
        if m:
            candidate = m.start()
            if content_start is None or candidate < content_start:
                content_start = candidate
            break
    if content_start and content_start < len(text) * 0.25:
        text = text[content_start:]

    back_patterns = [
        r"(?m)^#{1,4}\s+(Index|INDEX)\s*$",
        r"(?m)^#{1,4}\s+(Bibliography|BIBLIOGRAPHY)\s*$",
        r"(?m)^#{1,4}\s+(References|REFERENCES)\s*$",
        r"(?m)^#{1,4}\s+(Glossary|GLOSSARY)\s*$",
        r"(?m)^(Index|INDEX)\s*$",
    ]
    content_end = None
    for pat in back_patterns:
        for m in re.finditer(pat, text):
            candidate = m.start()
            if candidate > len(text) * 0.80:
                content_end = candidate
    if content_end:
        text = text[:content_end]

    return text


def chunk_paragraphs_text(text: str) -> list[str]:
    """Paragraph-level chunking with RecursiveCharacterTextSplitter."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=SEPARATORS,
    )
    return splitter.split_text(text)


# ── Text cleaning (line-by-line, safe from catastrophic backtracking) ─────

_HEADER_REPEAT_FRACTION = 0.02
_PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$")
_DOT_LEADER_RE = re.compile(r"[.\s]{4,}")


def _is_toc_line(line: str) -> bool:
    """Return True if *line* looks like a table-of-contents entry."""
    s = line.strip()
    if not s or len(s) > 120:
        return False
    if not re.search(r"\d{1,4}\s*$", s):
        return False
    m = _DOT_LEADER_RE.search(s)
    return bool(m) and m.group().count(".") >= 2


def clean_extracted_text(text: str) -> str:
    """Remove TOC lines, lone page numbers, broken hyphens, noisy headers.

    All regex patterns operate on individual lines — no unbounded
    alternation or nested quantifiers that could cause backtracking.
    """
    # 1-2: TOC + lone page numbers
    lines = [
        line
        for line in text.splitlines()
        if not _PAGE_NUM_RE.fullmatch(line) and not _is_toc_line(line)
    ]
    text = "\n".join(lines)

    # 3: Broken hyphenation
    text = re.sub(r"-\n([a-z])", r"\1", text)

    # 4: Repeated running headers/footers
    lines = text.splitlines()
    non_empty = [row.strip() for row in lines if len(row.strip()) > 4]
    threshold = max(5, int(len(non_empty) * _HEADER_REPEAT_FRACTION))
    noisy = {val for val, cnt in Counter(non_empty).items() if cnt >= threshold}
    if noisy:
        lines = [row for row in lines if row.strip() not in noisy]
        text = "\n".join(lines)

    # 5: Excess blank lines + trailing whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip()


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return matrix / norms


def build_sim_distribution(max_sims: np.ndarray) -> list[dict]:
    if max_sims.size == 0:
        return []

    buckets: list[dict] = []
    for idx in range(20):
        start = idx * 0.05
        end = start + 0.05
        if idx == 19:
            count = int(np.sum((max_sims >= start) & (max_sims <= end)))
        else:
            count = int(np.sum((max_sims >= start) & (max_sims < end)))
        buckets.append(
            {
                "bucket_start": round(start, 2),
                "bucket_end": round(end, 2),
                "count": count,
            }
        )
    return buckets


def load_course_concepts(course_id: int) -> list[dict]:
    uri = settings.neo4j_uri
    username = settings.neo4j_username
    password = settings.neo4j_password
    if not (uri and username and password):
        raise ValueError("Neo4j is not configured; cannot score concept coverage")

    query = """
    MATCH (d:TEACHER_UPLOADED_DOCUMENT {course_id: $course_id})-[m:MENTIONS]->(c:CONCEPT)
    RETURN
      c.name AS concept_name,
      d.topic AS doc_topic,
      coalesce(m.text_evidence, m.definition, '') AS text_evidence,
      c.embedding AS name_embedding,
      coalesce(m.text_evidence_embedding, m.definition_embedding) AS evidence_embedding
    ORDER BY concept_name ASC
    """

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=settings.neo4j_database) as session:
            rows = session.run(query, {"course_id": course_id}).data()
    finally:
        driver.close()

    by_name: dict[str, dict] = {}
    for row in rows:
        concept_name = (row.get("concept_name") or "").strip()
        name_embedding = row.get("name_embedding")
        if not concept_name or not name_embedding:
            continue

        existing = by_name.get(concept_name)
        candidate = {
            "concept_name": concept_name,
            "doc_topic": row.get("doc_topic"),
            "text_evidence": row.get("text_evidence") or None,
            "name_embedding": [float(v) for v in name_embedding],
            "evidence_embedding": (
                [float(v) for v in row["evidence_embedding"]]
                if row.get("evidence_embedding")
                else None
            ),
        }
        if existing is None:
            by_name[concept_name] = candidate
            continue

        if not existing.get("text_evidence") and candidate.get("text_evidence"):
            by_name[concept_name] = candidate

    concepts = list(by_name.values())
    if not concepts:
        raise ValueError(f"No embedded course concepts found for course {course_id}")
    return concepts


__all__ = [
    "filter_pdf_pages",
    "strip_book_matter",
    "clean_extracted_text",
    "chunk_paragraphs_text",
    "l2_normalize",
    "build_sim_distribution",
    "load_course_concepts",
]
