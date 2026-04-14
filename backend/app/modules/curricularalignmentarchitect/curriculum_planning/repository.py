from __future__ import annotations

import uuid

from neo4j import Session as Neo4jSession

from .schemas import ChapterPlan, ChapterPlanResponse, DocumentInfo


class ChapterPlanRepository:
    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    def list_documents(self, course_id: int) -> list[DocumentInfo]:
        result = self._session.run(
            """
            MATCH (c:CLASS {id: $course_id})-[:HAS_DOCUMENT]->(d:TEACHER_UPLOADED_DOCUMENT)
            RETURN d
            ORDER BY d.source_filename
            """,
            course_id=course_id,
        )
        docs = []
        for record in result:
            d = record["d"]
            docs.append(
                DocumentInfo(
                    id=d["id"],
                    source_filename=d.get("source_filename", ""),
                    topic=d.get("topic"),
                    summary=d.get("summary"),
                )
            )
        return docs

    def save_plan(self, course_id: int, chapters: list[ChapterPlan]) -> None:
        # Delete existing COURSE_CHAPTER nodes for this course
        self._session.run(
            """
            MATCH (c:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)
            DETACH DELETE ch
            """,
            course_id=course_id,
        ).consume()

        for chapter in chapters:
            chapter_id = str(uuid.uuid4())
            doc_ids = chapter.assigned_documents
            self._session.run(
                """
                MERGE (ch:COURSE_CHAPTER {id: $id})
                SET ch.course_id          = $course_id,
                    ch.title              = $title,
                    ch.description        = $description,
                    ch.learning_objectives = $learning_objectives,
                    ch.prerequisites      = $prerequisites,
                    ch.chapter_index      = $chapter_index,
                    ch.number             = $number
                WITH ch
                MATCH (c:CLASS {id: $course_id})
                MERGE (c)-[:HAS_COURSE_CHAPTER]->(ch)
                WITH ch
                UNWIND CASE WHEN $doc_ids = [] THEN [null] ELSE $doc_ids END AS doc_id
                WITH ch, doc_id WHERE doc_id IS NOT NULL
                MATCH (d:TEACHER_UPLOADED_DOCUMENT {id: doc_id})
                MERGE (ch)-[:INCLUDES_DOCUMENT]->(d)
                """,
                id=chapter_id,
                course_id=course_id,
                title=chapter.title,
                description=chapter.description,
                learning_objectives=chapter.learning_objectives,
                prerequisites=chapter.prerequisites,
                chapter_index=chapter.number,
                number=chapter.number,
                doc_ids=doc_ids,
            ).consume()

    def get_plan(self, course_id: int) -> ChapterPlanResponse:
        result = self._session.run(
            """
            MATCH (c:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)
            OPTIONAL MATCH (ch)-[:INCLUDES_DOCUMENT]->(d:TEACHER_UPLOADED_DOCUMENT)
            RETURN ch, collect(d.id) AS doc_ids
            ORDER BY ch.chapter_index
            """,
            course_id=course_id,
        )

        chapters: list[ChapterPlan] = []
        assigned_ids: set[str] = set()

        for record in result:
            ch = record["ch"]
            doc_ids: list[str] = [d for d in record["doc_ids"] if d is not None]
            assigned_ids.update(doc_ids)
            chapters.append(
                ChapterPlan(
                    number=ch.get("number", ch.get("chapter_index", 0)),
                    title=ch["title"],
                    description=ch.get("description", ""),
                    learning_objectives=list(ch.get("learning_objectives") or []),
                    prerequisites=list(ch.get("prerequisites") or []),
                    assigned_documents=doc_ids,
                )
            )

        all_documents = self.list_documents(course_id)
        unassigned = [d for d in all_documents if d.id not in assigned_ids]

        return ChapterPlanResponse(
            course_id=course_id,
            chapters=chapters,
            unassigned_documents=unassigned,
            all_documents=all_documents,
        )

    def has_plan(self, course_id: int) -> bool:
        result = self._session.run(
            """
            MATCH (c:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)
            RETURN count(ch) AS cnt
            """,
            course_id=course_id,
        ).single()
        return result is not None and result["cnt"] > 0
