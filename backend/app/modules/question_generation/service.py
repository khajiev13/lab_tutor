"""Question generation: 3 difficulty-graded questions per skill via LLM."""

from __future__ import annotations

import logging

from openai import OpenAI

from app.core.settings import settings

from .schemas import GeneratedQuestion, QuestionSet

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=120,
        )
    return _client


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return s


SYSTEM_PROMPT = """You are an expert question generator for university courses.

Given a skill profile (name, description, concepts, course level), generate exactly 3 multiple-choice questions
at different difficulty levels.

DIFFICULTY DEFINITIONS:
- **easy**: Tests basic recall of a concept definition or simple fact. A student who read
  the material once should be able to answer.
- **medium**: Tests application of the skill across 2+ concepts. Requires understanding
  how concepts relate to each other.
- **hard**: Tests synthesis/analysis requiring deep understanding. May ask the student
  to compare approaches, identify trade-offs, or solve a novel problem.

CONSTRAINTS:
- Generate questions based ONLY on the skill metadata (name, description, concepts).
- Do NOT reference any specific reading material, video, or textbook.
- Each question should be self-contained — a student should understand the question without external context.
- Each question must have exactly 4 answer options in A/B/C/D order.
- Exactly one option must be correct.
- Return a single valid JSON object and no explanatory text before or after it.
- The top-level object must have exactly one key named "questions".
- Use these exact literal field names in every question object:
  "text", "difficulty", "options", "correct_option", "answer".
- The "questions" array must contain exactly 3 objects:
  one "easy", one "medium", and one "hard".
- Distractors should be plausible and clearly distinct from the correct answer.
- Keep the correct option balanced across the 3 questions. Do not always use the same letter.
- Answers should briefly explain why the correct option is right (1-3 sentences).
- Tailor complexity to the course level (bachelor = fundamentals, master = deeper analysis, phd = research-level).

Return ONLY valid JSON matching this schema:
{
  "questions": [
    {
      "text": "...",
      "difficulty": "easy",
      "options": ["...", "...", "...", "..."],
      "correct_option": "A",
      "answer": "..."
    },
    {
      "text": "...",
      "difficulty": "medium",
      "options": ["...", "...", "...", "..."],
      "correct_option": "B",
      "answer": "..."
    },
    {
      "text": "...",
      "difficulty": "hard",
      "options": ["...", "...", "...", "..."],
      "correct_option": "C",
      "answer": "..."
    }
  ]
}"""


def _build_user_message(
    skill_name: str,
    skill_description: str,
    concepts: list[dict],
    course_level: str,
) -> str:
    parts = [
        f"Skill: {skill_name}",
        f"Description: {skill_description}" if skill_description else "",
        f"Course Level: {course_level}",
    ]
    if concepts:
        concept_lines = [
            f"  - {c.get('name', '')}: {c.get('definition', c.get('description', ''))}"
            for c in concepts[:10]
        ]
        parts.append("Concepts:\n" + "\n".join(concept_lines))
    return "\n".join(p for p in parts if p)


def generate_questions_for_skill(
    skill_name: str,
    skill_description: str,
    concepts: list[dict],
    course_level: str,
) -> list[GeneratedQuestion]:
    """Generate 3 questions (easy, medium, hard) from skill metadata.

    Context is SKILL metadata only (name, description, concepts).
    Does NOT use reading/video content.
    """
    user_msg = _build_user_message(
        skill_name, skill_description, concepts, course_level
    )

    resp = _get_client().chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_completion_tokens=4096,
    )

    raw = resp.choices[0].message.content or ""
    parsed = QuestionSet.model_validate_json(_strip_json_fence(raw))

    logger.info(
        "Generated %d questions for skill %s",
        len(parsed.questions),
        skill_name,
    )
    return parsed.questions
