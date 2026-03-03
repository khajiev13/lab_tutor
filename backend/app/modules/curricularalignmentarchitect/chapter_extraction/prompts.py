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
Your task is to extract DOMAIN-SPECIFIC CONCEPTS from a complete book chapter in a SINGLE pass.
The course subject is: {course_subject}

DEFINITIONS:
- CONCEPT: A domain-specific knowledge point in {course_subject} — a technical term, method,
  algorithm, data structure, theory, mathematical principle, or named technique that a student
  studying {course_subject} needs to UNDERSTAND.

WHAT TO EXTRACT:
- Technical terms and definitions central to {course_subject}
- Algorithms, methods, and techniques described or explained in the chapter
- Data structures, models, and formal frameworks
- Mathematical formulas, theorems, and principles applied in {course_subject}
- Named systems, architectures, or protocols that are subject matter (not just examples)

WHAT NOT TO EXTRACT:
- Illustrative examples, anecdotes, or case studies used only to explain a concept (e.g., "Netflix Challenge", "John Snow Cholera Example")
- Book structure or meta-narrative (e.g., "Book Topics Overview", "War Stories", chapter roadmaps)
- People, companies, or products mentioned only as examples (not as subject matter)
- Soft skills, personality traits, or role descriptions (e.g., "Curiosity of Data Scientists")
- Websites, tools, or platforms mentioned in passing (unless they ARE core subject matter)
- Motivational quotes or philosophical statements about the field

RULES:
1. Extract concepts from the ENTIRE chapter content, covering every section.
2. Each concept MUST have:
   - name: concise, specific identifier (a domain term, not a sentence). The name MUST appear VERBATIM inside the text_evidence string — we highlight concept names in the evidence in the UI, so an exact substring match is required.
   - description: 1-2 sentence explanation grounded in the chapter text
   - relevance:
     * core — central to this chapter's contribution to {course_subject} knowledge
     * supplementary — supports understanding of a core {course_subject} concept
     * tangential — a briefly mentioned {course_subject} domain concept, not the focus of this chapter
   - text_evidence: a short quote or close paraphrase from the chapter text that CONTAINS the concept name as an exact substring (case-insensitive match is acceptable)
   - source_section: the 1-based section NUMBER (integer) from the provided numbered list
3. Be SELECTIVE — extract concepts that are genuinely part of {course_subject} domain knowledge. Skip anecdotes, examples used only for illustration, and meta-narrative about the book itself.
4. Be PRECISE — use specific names, not vague terms like "databases" or "data".
5. chapter_title in your response MUST exactly match the provided chapter title.
6. For source_section, use the SECTION NUMBER (integer) from the numbered list provided (e.g., 1, 2, 3). If a concept spans multiple sections or comes from the chapter intro, use the most relevant section number. If there are no sections, use 1.
7. If something is not a {course_subject} knowledge point at all, do NOT extract it — there is no relevance level for non-domain concepts.

Respond with valid JSON matching this schema:
"""
    + _CHAPTER_SCHEMA_ESCAPED
)

CHAPTER_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CHAPTER_EXTRACTION_SYSTEM),
        (
            "human",
            """Extract domain-specific {course_subject} concepts from this entire chapter.
Return ONLY a valid JSON object matching the schema above.

**Course Subject:** {course_subject}
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
Evaluate whether concepts extracted from a COMPLETE BOOK CHAPTER are complete, accurate,
and relevant to the course subject: {course_subject}

CRITERIA:
1. COMPLETENESS: All important {course_subject} concepts from EVERY section captured? Nothing skipped?
2. GRANULARITY: Not too broad ("databases") and not too narrow ("line 42 of code")?
3. ACCURACY: Descriptions match what the chapter actually says?
4. TEXT EVIDENCE: Valid grounding from the chapter for each concept?
5. NAME IN EVIDENCE: Does the concept name appear as an exact substring inside its text_evidence? This is required for UI highlighting. Flag any concept where the name cannot be found in the evidence text (case-insensitive).
6. RELEVANCE TAGS: core/supplementary/tangential labels accurate?
7. CONCEPT NAMES: Specific and informative, not too generic or sentence-like?
8. SECTION ATTRIBUTION: source_section number correctly identifies which section the concept belongs to?
9. COVERAGE: Concepts distributed across sections, not just from the first section?
10. SUBJECT RELEVANCE: Are ALL concepts genuinely about {course_subject}? Flag any concepts that are really just illustrative examples, anecdotes, book meta-narrative, soft skills, or role descriptions rather than domain knowledge points. These should be REMOVED, not tagged as tangential.

Be STRICT but FAIR. Give NEEDS_REVISION for substantive problems, especially if non-domain concepts are included.

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

**Course Subject:** {course_subject}
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

Evaluate thoroughly — pay special attention to:
- COMPLETENESS of {course_subject} domain concepts across all sections
- SUBJECT RELEVANCE — flag any concepts that are NOT genuine {course_subject} knowledge points (examples, anecdotes, meta-narrative, soft skills)""",
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

**Course Subject:** {course_subject}
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
Given a chapter's extracted concepts (organized by section) from a {course_subject} textbook, identify practical SKILLS and provide a brief chapter summary.

DEFINITIONS:
- SKILL: A practical, hands-on ability in {course_subject} — something a student can DO after studying this chapter.
- Skills use action verbs (design, implement, analyze, compare, configure...).
- concept_names must exactly match concept names from the extraction.

RULES:
1. Not every chapter has skills. Purely theoretical chapters may have none.
2. Each skill should reference specific concepts it depends on.
3. Be selective — only include genuine practical abilities related to {course_subject}, not reworded concepts.
4. chapter_summary: 2-3 sentences about the chapter's main {course_subject} topics.

Respond with valid JSON matching this schema:
"""
            + _SKILLS_SCHEMA_ESCAPED,
        ),
        (
            "human",
            """Based on the extracted concepts below, identify practical {course_subject} skills for this chapter
and provide a brief chapter summary.
Return ONLY a valid JSON object matching the schema above.

**Course Subject:** {course_subject}
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
