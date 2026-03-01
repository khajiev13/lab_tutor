"""Prompt templates for chapter-level concept extraction.

Copied verbatim from the chapter_level_extraction notebook.
"""

from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate

from .schemas import ChapterConceptsResult, ChapterSkillsResult, ExtractionFeedback


def _escape_for_template(s: str) -> str:
    """Escape curly braces so LangChain prompt templates treat them as literals."""
    return s.replace("{", "{{").replace("}", "}}")


_CHAPTER_SCHEMA_ESCAPED = _escape_for_template(
    json.dumps(ChapterConceptsResult.model_json_schema(), indent=2)
)
_SKILLS_SCHEMA_ESCAPED = _escape_for_template(
    json.dumps(ChapterSkillsResult.model_json_schema(), indent=2)
)
_FEEDBACK_SCHEMA_ESCAPED = _escape_for_template(
    json.dumps(ExtractionFeedback.model_json_schema(), indent=2)
)


# ── CHAPTER EXTRACTION PROMPT ─────────────────────────────────

CHAPTER_EXTRACTION_SYSTEM = (
    """You are an expert educational content analyst specializing in textbook analysis.
Your task is to extract ALL CONCEPTS from a complete book chapter in a SINGLE pass.

DEFINITIONS:
- CONCEPT: A knowledge point — something a student needs to KNOW.

RULES:
1. Extract ALL concepts from the ENTIRE chapter content below.
2. Each concept MUST have:
   - name: concise, specific identifier
   - description: 1-2 sentence explanation grounded in the chapter text
   - relevance: core (main topic), supplementary (supports main topic), tangential (briefly mentioned)
   - text_evidence: a short quote or close paraphrase from the chapter text
   - source_section: the section title this concept primarily belongs to (from the section list provided)
3. Be EXHAUSTIVE — extract ALL concepts from every section.
4. Be PRECISE — use specific names, not vague terms like "databases" or "data".
5. chapter_title in your response MUST exactly match the provided chapter title.
6. For source_section, use the EXACT section title from the provided list. If a concept spans multiple sections or comes from the chapter intro, use the most relevant section title.

Respond with valid JSON matching this schema:
"""
    + _CHAPTER_SCHEMA_ESCAPED
)

CHAPTER_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CHAPTER_EXTRACTION_SYSTEM),
        (
            "human",
            """Extract ALL concepts from this entire chapter.
Return ONLY a valid JSON object matching the schema above.

**Book:** {book_name}
**Chapter:** {chapter_title}

**Sections in this chapter:**
{section_list}

--- FULL CHAPTER CONTENT ---
{chapter_content}
--- END CHAPTER CONTENT ---""",
        ),
    ]
)


# ── CHAPTER EVALUATION PROMPT ─────────────────────────────────

CHAPTER_EVALUATION_SYSTEM = (
    """You are a strict quality reviewer for educational concept extraction.
Evaluate whether concepts extracted from a COMPLETE BOOK CHAPTER are complete and accurate.

CRITERIA:
1. COMPLETENESS: All important concepts from EVERY section captured? Nothing skipped?
2. GRANULARITY: Not too broad ("databases") and not too narrow ("line 42 of code")?
3. ACCURACY: Descriptions match what the chapter actually says?
4. TEXT EVIDENCE: Valid grounding from the chapter for each concept?
5. RELEVANCE TAGS: core/supplementary/tangential labels accurate?
6. CONCEPT NAMES: Specific and informative, not too generic or sentence-like?
7. SECTION ATTRIBUTION: source_section correctly identifies which section the concept belongs to?
8. COVERAGE: Concepts distributed across sections, not just from the first section?

Be STRICT but FAIR. Only give NEEDS_REVISION for substantive problems.

Respond with valid JSON matching this schema:
"""
    + _FEEDBACK_SCHEMA_ESCAPED
)

CHAPTER_EVALUATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CHAPTER_EVALUATION_SYSTEM),
        (
            "human",
            """Evaluate this chapter-level concept extraction.

**Book:** {book_name}
**Chapter:** {chapter_title}

**Sections in this chapter:**
{section_list}

--- CHAPTER CONTENT (first 5000 chars) ---
{chapter_content_preview}
--- END PREVIEW ---

--- EXTRACTION ({num_concepts} concepts) ---
{concepts_detail}
--- END EXTRACTION ---

Evaluate thoroughly — pay special attention to COMPLETENESS across all sections.""",
        ),
    ]
)


# ── CHAPTER REVISION PROMPT ───────────────────────────────────

CHAPTER_REVISION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CHAPTER_EXTRACTION_SYSTEM),
        (
            "human",
            """You previously extracted concepts from this chapter, but the quality review found issues.
Revise your extraction to fix them.
Return ONLY a valid JSON object matching the schema above.

**Book:** {book_name}
**Chapter:** {chapter_title}

**Sections in this chapter:**
{section_list}

--- FULL CHAPTER CONTENT ---
{chapter_content}
--- END CHAPTER CONTENT ---

--- YOUR PREVIOUS EXTRACTION ({num_prev_concepts} concepts) ---
{prev_extraction_summary}

--- ISSUES FOUND ---
{reflection_issues}

Now produce a REVISED extraction that fixes all the issues above.
Keep what was good, fix what was wrong, add what was missing.""",
        ),
    ]
)


# ── SKILLS PROMPT ─────────────────────────────────────────────

SKILLS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert educational content analyst.
Given a chapter's extracted concepts (organized by section), identify practical SKILLS and provide a brief chapter summary.

DEFINITIONS:
- SKILL: A practical, hands-on ability — something a student can DO after studying this chapter.
- Skills use action verbs (design, implement, analyze, compare, configure...).
- concept_names must exactly match concept names from the extraction.

RULES:
1. Not every chapter has skills. Purely theoretical chapters may have none.
2. Each skill should reference specific concepts it depends on.
3. Be selective — only include genuine practical abilities, not reworded concepts.
4. chapter_summary: 2-3 sentences about the chapter's main topics.

Respond with valid JSON matching this schema:
"""
            + _SKILLS_SCHEMA_ESCAPED,
        ),
        (
            "human",
            """Based on the extracted concepts below, identify practical skills for this chapter
and provide a brief chapter summary.
Return ONLY a valid JSON object matching the schema above.

**Book:** {book_name}
**Chapter:** {chapter_title}

--- EXTRACTED CONCEPTS BY SECTION ---
{all_sections_summary}
--- END ---""",
        ),
    ]
)


def truncate_content(content: str, max_chars: int = 30_000) -> str:
    """Truncate long chapter content, keeping head and tail."""
    if len(content) <= max_chars:
        return content
    half = max_chars // 2
    return (
        content[:half]
        + "\n\n[... middle section truncated for length ...]\n\n"
        + content[-half:]
    )
