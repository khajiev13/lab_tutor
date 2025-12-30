from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import LiteralString, cast

from neo4j import ManagedTransaction
from neo4j import Session as Neo4jSession
from pydantic import BaseModel


class MentionInput(BaseModel):
    name: str
    original_name: str
    definition: str
    text_evidence: str
    source_document: str


UPSERT_COURSE_DOCUMENT: LiteralString = """
MERGE (d:TEACHER_UPLOADED_DOCUMENT {id: $document_id})
SET
    d.course_id = $course_id,
    d.teacher_id = $teacher_id,
    d.source_filename = $source_filename,
    d.topic = $topic,
    d.summary = $summary,
    d.keywords = $keywords,
    d.original_text = $original_text,
    d.content_hash = $content_hash,
    d.extracted_at = $extracted_at
WITH d
MERGE (t:USER {id: $teacher_id})
MERGE (c:CLASS {id: $course_id})
MERGE (t)-[:UPLOADED_DOCUMENT]->(d)
MERGE (c)-[:HAS_DOCUMENT]->(d)
RETURN d
"""


UPSERT_MENTIONS: LiteralString = """
MATCH (d:TEACHER_UPLOADED_DOCUMENT {id: $document_id})
UNWIND $mentions AS mention
MERGE (c:CONCEPT {name: toLower(mention.name)})
MERGE (d)-[m:MENTIONS]->(c)
SET
    m.original_name = mention.original_name,
    m.definition = mention.definition,
    m.text_evidence = mention.text_evidence,
    m.source_document = mention.source_document,
    m.updated_at = $updated_at
RETURN count(m) AS mentions_upserted
"""


DELETE_DOCUMENT_AND_ORPHAN_CONCEPTS: LiteralString = """
MATCH (d:TEACHER_UPLOADED_DOCUMENT {id: $document_id})
OPTIONAL MATCH (d)-[:MENTIONS]->(c:CONCEPT)
WITH d, collect(DISTINCT c) AS concepts
DETACH DELETE d
WITH concepts
UNWIND concepts AS c
OPTIONAL MATCH (c)-[r]-()
WITH c, count(r) AS rels
WHERE rels = 0
DELETE c
RETURN count(c) AS concepts_deleted
"""


DELETE_DOCUMENTS_BY_COURSE_AND_FILENAME_AND_ORPHAN_CONCEPTS: LiteralString = """
MATCH (d:TEACHER_UPLOADED_DOCUMENT)
WHERE d.course_id = $course_id AND d.source_filename = $source_filename
OPTIONAL MATCH (d)-[:MENTIONS]->(c:CONCEPT)
WITH collect(DISTINCT d) AS docs, collect(DISTINCT c) AS concepts
WITH docs, concepts, size(docs) AS documents_deleted
UNWIND docs AS d
DETACH DELETE d
WITH concepts, documents_deleted
UNWIND concepts AS c
OPTIONAL MATCH (c)-[r]-()
WITH c, count(r) AS rels, documents_deleted
WHERE rels = 0
DELETE c
RETURN documents_deleted, count(c) AS concepts_deleted
"""


DELETE_DOCUMENTS_BY_COURSE_AND_ORPHAN_CONCEPTS: LiteralString = """
MATCH (d:TEACHER_UPLOADED_DOCUMENT)
WHERE d.course_id = $course_id
OPTIONAL MATCH (d)-[:MENTIONS]->(c:CONCEPT)
WITH collect(DISTINCT d) AS docs, collect(DISTINCT c) AS concepts
WITH docs, concepts, size(docs) AS documents_deleted
UNWIND docs AS d
DETACH DELETE d
WITH concepts, documents_deleted
UNWIND concepts AS c
OPTIONAL MATCH (c)-[r]-()
WITH c, count(r) AS rels, documents_deleted
WHERE rels = 0
DELETE c
RETURN documents_deleted, count(c) AS concepts_deleted
"""


class DocumentExtractionGraphRepository:
    """Neo4j repository for extraction-created nodes and relationships."""

    _session: Neo4jSession

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    def upsert_course_document(
        self,
        *,
        course_id: int,
        teacher_id: int,
        document_id: str,
        source_filename: str,
        topic: str | None,
        summary: str | None,
        keywords: list[str] | None,
        original_text: str | None,
        content_hash: str | None,
        extracted_at: datetime | None,
    ) -> None:
        params = {
            "course_id": course_id,
            "teacher_id": teacher_id,
            "document_id": document_id,
            "source_filename": source_filename,
            "topic": topic,
            "summary": summary,
            "keywords": keywords or [],
            "original_text": original_text,
            "content_hash": content_hash,
            "extracted_at": extracted_at.isoformat() if extracted_at else None,
        }

        def _tx(tx: ManagedTransaction) -> None:
            tx.run(UPSERT_COURSE_DOCUMENT, params).consume()

        self._session.execute_write(_tx)

    def upsert_mentions(
        self,
        *,
        document_id: str,
        mentions: Sequence[MentionInput],
        updated_at: datetime | None = None,
    ) -> int:
        mentions_payload = [m.model_dump() for m in mentions]
        params = {
            "document_id": document_id,
            "mentions": mentions_payload,
            "updated_at": (updated_at or datetime.utcnow()).isoformat(),
        }

        def _tx(tx: ManagedTransaction) -> int:
            record = tx.run(UPSERT_MENTIONS, params).single()
            return int(record["mentions_upserted"]) if record else 0

        return int(self._session.execute_write(_tx))

    def delete_document_and_orphan_concepts(self, *, document_id: str) -> int:
        """Delete the uploaded document and delete any concepts that become orphaned.

        A concept is considered safe to delete if it has zero relationships after the
        document (and its :MENTIONS relationships) are removed.
        """
        params = {"document_id": document_id}

        def _tx(tx: ManagedTransaction) -> int:
            record = tx.run(DELETE_DOCUMENT_AND_ORPHAN_CONCEPTS, params).single()
            return int(record["concepts_deleted"]) if record else 0

        return int(self._session.execute_write(_tx))

    def delete_documents_by_course_and_filename_and_orphan_concepts(
        self, *, course_id: int, source_filename: str
    ) -> tuple[int, int]:
        """Delete all uploaded documents for a course matching a filename.

        Returns (documents_deleted, concepts_deleted).
        """
        params = {"course_id": course_id, "source_filename": source_filename}

        def _tx(tx: ManagedTransaction) -> tuple[int, int]:
            record = tx.run(
                DELETE_DOCUMENTS_BY_COURSE_AND_FILENAME_AND_ORPHAN_CONCEPTS, params
            ).single()
            if not record:
                return (0, 0)
            return (int(record["documents_deleted"]), int(record["concepts_deleted"]))

        return cast(tuple[int, int], self._session.execute_write(_tx))

    def delete_documents_by_course_and_orphan_concepts(
        self, *, course_id: int
    ) -> tuple[int, int]:
        """Delete all uploaded documents for a course.

        Returns (documents_deleted, concepts_deleted).
        """
        params = {"course_id": course_id}

        def _tx(tx: ManagedTransaction) -> tuple[int, int]:
            record = tx.run(
                DELETE_DOCUMENTS_BY_COURSE_AND_ORPHAN_CONCEPTS, params
            ).single()
            if not record:
                return (0, 0)
            return (int(record["documents_deleted"]), int(record["concepts_deleted"]))

        return cast(tuple[int, int], self._session.execute_write(_tx))
