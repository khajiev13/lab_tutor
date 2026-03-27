"""Prompt templates for chapter-level skills extraction."""

from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate

from .schemas import ChapterSkillsResult, SkillsJudgeFeedback


def _escape(s: str) -> str:
    return s.replace("{", "{{").replace("}", "}}")


_SKILLS_SCHEMA = _escape(json.dumps(ChapterSkillsResult.model_json_schema(), indent=2))
_JUDGE_SCHEMA = _escape(json.dumps(SkillsJudgeFeedback.model_json_schema(), indent=2))


# ── SKILLS EXTRACTION PROMPT ──────────────────────────────────────────────────
# Direct from chapter content — no prior concept extraction needed.

SKILLS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert educational content analyst building a skill bank from textbooks.
Your task: given a chapter from a {course_subject} textbook, extract practical SKILLS
and the CONCEPTS each skill requires.

DEFINITIONS
- SKILL: A practical, hands-on ability a student can DEMONSTRATE after studying this chapter.
  Skills must start with an action verb (design, implement, analyze, compare, configure, apply...).
- CONCEPT: A domain-specific knowledge unit (term, algorithm, method, principle, data structure)
  that a student must UNDERSTAND to perform the skill.

RULES FOR SKILLS
1. Only extract genuine practical abilities — not reworded concept definitions.
2. Each skill must be scoped to something teachable in one chapter, not an entire career.
3. Purely theoretical chapters may have zero skills — that is correct.
4. Avoid vague skills like "Understand X" or "Know about Y" — those are concepts, not skills.

RULES FOR CONCEPTS
1. Each concept must be a real {course_subject} domain term from this chapter.
2. Give a brief, grounded description (1-2 sentences) drawn from the chapter text.
3. A concept list of 2-5 per skill is typical; more if the skill is genuinely complex.
4. Concept names must be concise identifiers, not full sentences.

Respond with valid JSON matching this schema:
"""
            + _SKILLS_SCHEMA,
        ),
        (
            "human",
            """Extract practical {course_subject} skills (with their prerequisite concepts)
from the chapter below.
Return ONLY a valid JSON object matching the schema.

**Course Subject:** {course_subject}
**Book:** {book_name}
**Chapter:** {chapter_title}

--- CHAPTER CONTENT ---
{chapter_content}
--- END ---""",
        ),
    ]
)

SKILLS_REVISION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert educational content analyst building a skill bank from textbooks.
Your task: revise a previous skills extraction that a quality reviewer found lacking.
Apply the reviewer's feedback precisely, then output the corrected result.

Respond with valid JSON matching this schema:
"""
            + _SKILLS_SCHEMA,
        ),
        (
            "human",
            """Revise the skills extraction below based on the reviewer's feedback.
Return ONLY a valid JSON object matching the schema.

**Course Subject:** {course_subject}
**Book:** {book_name}
**Chapter:** {chapter_title}

--- CHAPTER CONTENT ---
{chapter_content}
--- END ---

--- PREVIOUS EXTRACTION ---
{previous_extraction}
--- END ---

--- REVIEWER FEEDBACK ---
{issues}
--- END ---

Produce a revised extraction that fixes all the issues above.""",
        ),
    ]
)


# ── SKILLS JUDGE PROMPT (Karpathy-style LLM-as-judge) ────────────────────────

SKILLS_JUDGE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a strict quality reviewer for educational skill extraction.
Evaluate whether the skills extracted from a {course_subject} chapter meet the bar
for a high-quality skill bank.

WHAT TO CHECK
1. ACTION VERBS — Do all skill names start with a concrete action verb?
2. PRACTICAL — Are these genuine learnable abilities, not disguised concept definitions?
3. SCOPE — Is each skill scoped to something teachable in one chapter?
4. CONCEPTS — Are the listed concepts real {course_subject} domain terms from this chapter?
   Are they actually REQUIRED to perform the skill (not just vaguely related)?
5. COVERAGE — Does the skill set cover the chapter's main practical takeaways?
6. NO DUPLICATES — Are all skills distinct (not minor rewordings of each other)?

Approve if the extraction is solid. Request revision only for substantive problems —
a single minor wording issue is not enough to reject.

Respond with valid JSON matching this schema:
"""
            + _JUDGE_SCHEMA,
        ),
        (
            "human",
            """Evaluate this skills extraction for a {course_subject} chapter.

**Book:** {book_name}
**Chapter:** {chapter_title}

--- EXTRACTED SKILLS ---
{skills_json}
--- END ---

--- CHAPTER SUMMARY ---
{chapter_summary}
--- END ---

Is this extraction ready for a skill bank, or does it need revision?""",
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
