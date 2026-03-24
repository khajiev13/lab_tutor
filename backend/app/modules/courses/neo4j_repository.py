from __future__ import annotations

from datetime import datetime
from typing import LiteralString

from neo4j import ManagedTransaction
from neo4j import Session as Neo4jSession

UPSERT_CLASS: LiteralString = """
MERGE (c:CLASS {id: $id})
SET
    c.title = $title,
    c.description = $description,
    c.created_at = $created_at,
    c.extraction_status = $extraction_status
RETURN c
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
DETACH DELETE c
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
