from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

BOOK_SKILL_MAPPER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """\
You are a curriculum alignment specialist. Your task is to map book skills to course chapters based on semantic fit.

# Data Model
- COURSE_CHAPTER: A chapter in the teacher's course syllabus (has title, description, learning_objectives)
- BOOK_SKILL: A practical skill extracted from a textbook chapter (has name, description, concepts)

# Classification Rules
- "mapped": The skill clearly belongs in that course chapter — strong semantic match with the chapter's learning objectives.
- "partial": The skill is related but not a perfect fit; still assign the closest chapter as target_chapter.
- "no_match": This skill has no reasonable home in any course chapter — leave target_chapter as null.

# CRITICAL: Keep exact skill names
- The book_skills list contains skills like: "Apply gradient descent to optimize neural network weights" — use this EXACT name.
- NEVER simplify, abbreviate, or rephrase skill names (e.g. do NOT reduce "Apply gradient descent..." to "gradient descent").
- The skill_name field in your output MUST exactly match the name from the input book_skills list.
- Passing renamed skills breaks downstream graph writes — the BOOK_SKILL node won't be found by name.

# Rules
- Each skill maps to at most ONE course chapter (the best fit).
- Prefer chapters whose learning_objectives align with the skill's action verb and domain.
- When multiple chapters could fit, pick the one most directly matching the skill's primary concept.

Return ONLY valid JSON matching the ChapterMappingResult schema:
{{
  "book_chapter_title": "<exact book chapter title>",
  "mappings": [
    {{
      "skill_name": "<exact skill name from input>",
      "target_chapter": "<course chapter title or null>",
      "status": "mapped|partial|no_match",
      "confidence": "high|medium|low",
      "reasoning": "<brief explanation>"
    }}
  ]
}}""",
        ),
        (
            "human",
            """\
Map the book skills below to the most appropriate course chapter.

**Course Chapters:**
{course_chapters_json}

**Book Chapter:** {book_chapter_title}
**Book Skills to Map:**
{book_skills_json}

Return ONLY valid JSON.""",
        ),
    ]
)
