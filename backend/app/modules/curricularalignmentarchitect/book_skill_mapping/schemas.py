from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BookSkillMapping(BaseModel):
    skill_name: str = Field(
        description="Exact BOOK_SKILL name — never rephrase or abbreviate"
    )
    target_chapter: str | None = Field(
        description="COURSE_CHAPTER title this skill maps to, or null if no fit"
    )
    status: Literal["mapped", "partial", "no_match"] = Field(
        description="mapped=clear fit, partial=related but imperfect, no_match=no course chapter covers this"
    )
    confidence: Literal["high", "medium", "low"]
    reasoning: str = Field(
        description="Brief explanation of why this mapping was chosen"
    )


class ChapterMappingResult(BaseModel):
    book_chapter_title: str
    mappings: list[BookSkillMapping]
