from __future__ import annotations

from datetime import datetime
from typing import LiteralString

from neo4j import ManagedTransaction
from neo4j import Session as Neo4jSession

DEFAULT_MIN_SELECTED_SKILLS = 20
DEFAULT_MAX_SELECTED_SKILLS = 35

UPSERT_CLASS: LiteralString = """
MERGE (c:CLASS {id: $id})
SET
    c.title = $title,
    c.description = $description,
    c.created_at = $created_at,
    c.extraction_status = $extraction_status
"""

LINK_TEACHER_TEACHES_CLASS: LiteralString = """
MERGE (t:USER {id: $teacher_id})
MERGE (c:CLASS {id: $class_id})
MERGE (t)-[:TEACHES_CLASS]->(c)
"""

LINK_STUDENT_ENROLLED: LiteralString = """
MERGE (s:USER {id: $student_id})
MERGE (c:CLASS {id: $class_id})
MERGE (s)-[:ENROLLED_IN_CLASS]->(c)
"""

UNLINK_STUDENT_ENROLLED: LiteralString = """
MATCH (s:USER {id: $student_id})-[r:ENROLLED_IN_CLASS]->(c:CLASS {id: $class_id})
DELETE r
"""

DELETE_CLASS: LiteralString = """
MATCH (c:CLASS {id: $class_id})
OPTIONAL MATCH (c)-[:CANDIDATE_BOOK]->(b:BOOK)
OPTIONAL MATCH (b)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)
OPTIONAL MATCH (ch)-[:HAS_SECTION]->(sec:BOOK_SECTION)
OPTIONAL MATCH (ch)-[:HAS_CHUNK]->(chunk1:BOOK_CHUNK)
OPTIONAL MATCH (sec)-[:HAS_CHUNK]->(chunk2:BOOK_CHUNK)
OPTIONAL MATCH (ch)-[:HAS_SKILL]->(skill:BOOK_SKILL)
DETACH DELETE c, b, ch, sec, chunk1, chunk2, skill
"""

SET_SKILL_SELECTION_RANGE: LiteralString = """
MATCH (c:CLASS {id: $class_id})
SET
    c.selection_min_skills = $min_skills,
    c.selection_max_skills = $max_skills
"""

GET_SKILL_SELECTION_RANGE: LiteralString = """
MATCH (c:CLASS {id: $class_id})
RETURN
    c.selection_min_skills AS min_skills,
    c.selection_max_skills AS max_skills
"""


class CourseGraphRepository:
    _session: Neo4jSession

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    def upsert_course(
        self,
        *,
        course_id: int,
        title: str,
        description: str | None,
        created_at: datetime | None,
        extraction_status: str | None,
    ) -> None:
        params = {
            "id": course_id,
            "title": title,
            "description": description,
            "created_at": created_at.isoformat() if created_at else None,
            "extraction_status": extraction_status,
        }

        def _tx(tx: ManagedTransaction) -> None:
            tx.run(UPSERT_CLASS, params).consume()

        self._session.execute_write(_tx)

    def link_teacher_teaches_class(self, *, teacher_id: int, course_id: int) -> None:
        params = {"teacher_id": teacher_id, "class_id": course_id}

        def _tx(tx: ManagedTransaction) -> None:
            tx.run(LINK_TEACHER_TEACHES_CLASS, params).consume()

        self._session.execute_write(_tx)

    def link_student_enrolled(self, *, student_id: int, course_id: int) -> None:
        params = {"student_id": student_id, "class_id": course_id}

        def _tx(tx: ManagedTransaction) -> None:
            tx.run(LINK_STUDENT_ENROLLED, params).consume()

        self._session.execute_write(_tx)

    def unlink_student_enrolled(self, *, student_id: int, course_id: int) -> None:
        params = {"student_id": student_id, "class_id": course_id}

        def _tx(tx: ManagedTransaction) -> None:
            tx.run(UNLINK_STUDENT_ENROLLED, params).consume()

        self._session.execute_write(_tx)

    def delete_course(self, *, course_id: int) -> None:
        params = {"class_id": course_id}

        def _tx(tx: ManagedTransaction) -> None:
            tx.run(DELETE_CLASS, params).consume()

        self._session.execute_write(_tx)

    def set_skill_selection_range(
        self,
        *,
        course_id: int,
        min_skills: int,
        max_skills: int,
    ) -> None:
        params = {
            "class_id": course_id,
            "min_skills": min_skills,
            "max_skills": max_skills,
        }

        def _tx(tx: ManagedTransaction) -> None:
            tx.run(SET_SKILL_SELECTION_RANGE, params).consume()

        self._session.execute_write(_tx)

    def get_skill_selection_range(self, *, course_id: int) -> dict[str, int | bool]:
        params = {"class_id": course_id}

        def _tx(tx: ManagedTransaction) -> dict[str, int | bool]:
            record = tx.run(GET_SKILL_SELECTION_RANGE, params).single()
            stored_min = (
                int(record["min_skills"])
                if record and record["min_skills"] is not None
                else None
            )
            stored_max = (
                int(record["max_skills"])
                if record and record["max_skills"] is not None
                else None
            )
            is_default = stored_min is None or stored_max is None
            return {
                "min_skills": stored_min or DEFAULT_MIN_SELECTED_SKILLS,
                "max_skills": stored_max or DEFAULT_MAX_SELECTED_SKILLS,
                "is_default": is_default,
            }

        return self._session.execute_read(_tx)
