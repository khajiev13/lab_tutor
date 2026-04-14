from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class BookSkillMappingState(TypedDict):
    course_id: int
    mappings: Annotated[list[dict], operator.add]
    errors: Annotated[list[dict], operator.add]


class ChapterMapperInput(TypedDict):
    course_id: int
    book_chapter_id: str
    book_chapter_title: str
    skills: list[dict]
    course_chapters: list[dict]
    mappings: Annotated[list[dict], operator.add]
    errors: Annotated[list[dict], operator.add]
