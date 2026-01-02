from __future__ import annotations

from datetime import datetime
from typing import LiteralString

from neo4j import ManagedTransaction
from neo4j import Session as Neo4jSession

from .graph_schemas import (
    ClassNodeData,
    ConceptNodeData,
    CourseGraphResponse,
    DocumentNodeData,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    MentionsEdgeData,
)

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

GET_COURSE_GRAPH_SNAPSHOT: LiteralString = """
MATCH (cls:CLASS {id: $course_id})
OPTIONAL MATCH (cls)-[:HAS_DOCUMENT]->(d:TEACHER_UPLOADED_DOCUMENT)
WITH cls, d
ORDER BY d.extracted_at DESC
WITH cls, collect(DISTINCT d)[0..$max_documents] AS docs
UNWIND docs AS d
OPTIONAL MATCH (d)-[m:MENTIONS]->(c:CONCEPT)
RETURN
  cls.id AS course_id,
  cls.title AS course_title,
  d.id AS document_id,
  d.source_filename AS source_filename,
  d.topic AS topic,
  d.extracted_at AS extracted_at,
  c.name AS concept_name,
  m.definition AS definition,
  m.text_evidence AS text_evidence,
  m.source_document AS source_document
"""

EXPAND_DOCUMENT_NEIGHBORS: LiteralString = """
MATCH (cls:CLASS {id: $course_id})-[:HAS_DOCUMENT]->(d:TEACHER_UPLOADED_DOCUMENT {id: $document_id})
OPTIONAL MATCH (d)-[m:MENTIONS]->(c:CONCEPT)
RETURN
  cls.id AS course_id,
  cls.title AS course_title,
  d.id AS document_id,
  d.source_filename AS source_filename,
  d.topic AS topic,
  d.extracted_at AS extracted_at,
  c.name AS concept_name,
  m.definition AS definition,
  m.text_evidence AS text_evidence,
  m.source_document AS source_document
LIMIT $limit
"""

EXPAND_CONCEPT_NEIGHBORS: LiteralString = """
MATCH (c:CONCEPT {name: toLower($concept_name)})
OPTIONAL MATCH (d:TEACHER_UPLOADED_DOCUMENT {course_id: $course_id})-[m:MENTIONS]->(c)
RETURN
  $course_id AS course_id,
  NULL AS course_title,
  d.id AS document_id,
  d.source_filename AS source_filename,
  d.topic AS topic,
  d.extracted_at AS extracted_at,
  c.name AS concept_name,
  m.definition AS definition,
  m.text_evidence AS text_evidence,
  m.source_document AS source_document
LIMIT $limit
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

    def get_course_graph_snapshot(
        self,
        *,
        course_id: int,
        max_documents: int,
        max_concepts: int,
    ) -> CourseGraphResponse:
        params = {
            "course_id": course_id,
            "max_documents": max_documents,
        }

        def _tx(tx: ManagedTransaction) -> list[dict[str, object]]:
            return list(tx.run(GET_COURSE_GRAPH_SNAPSHOT, params).data())

        rows = list(self._session.execute_read(_tx))
        return _rows_to_course_graph_response(
            rows=rows,
            course_id=course_id,
            max_concepts=max_concepts,
        )

    def expand_course_graph_node(
        self,
        *,
        course_id: int,
        node_kind: GraphNodeKind,
        node_key: str,
        limit: int,
        max_concepts: int,
    ) -> CourseGraphResponse:
        if node_kind == GraphNodeKind.DOCUMENT:
            cypher = EXPAND_DOCUMENT_NEIGHBORS
            params = {"course_id": course_id, "document_id": node_key, "limit": limit}
        elif node_kind == GraphNodeKind.CONCEPT:
            cypher = EXPAND_CONCEPT_NEIGHBORS
            params = {"course_id": course_id, "concept_name": node_key, "limit": limit}
        else:
            # For CLASS, fall back to a bounded snapshot.
            return self.get_course_graph_snapshot(
                course_id=course_id,
                max_documents=min(limit, 250),
                max_concepts=max_concepts,
            )

        def _tx(tx: ManagedTransaction) -> list[dict[str, object]]:
            return list(tx.run(cypher, params).data())

        rows = list(self._session.execute_read(_tx))
        return _rows_to_course_graph_response(
            rows=rows,
            course_id=course_id,
            max_concepts=max_concepts,
        )


def _rows_to_course_graph_response(
    *,
    rows: list[dict[str, object]],
    course_id: int,
    max_concepts: int,
) -> CourseGraphResponse:
    nodes_by_id: dict[str, GraphNode] = {}
    edges_by_id: dict[str, GraphEdge] = {}

    # Always include the course/class node (even if Neo4j row set is empty).
    class_node_id = f"class_{course_id}"
    nodes_by_id[class_node_id] = GraphNode(
        id=class_node_id,
        kind=GraphNodeKind.CLASS,
        label=f"Course {course_id}",
        data=ClassNodeData(course_id=course_id, title=None),
    )

    concept_count = 0

    for r in rows:
        raw_course_title = r.get("course_title")
        if isinstance(raw_course_title, str) and raw_course_title.strip():
            nodes_by_id[class_node_id] = GraphNode(
                id=class_node_id,
                kind=GraphNodeKind.CLASS,
                label=raw_course_title,
                data=ClassNodeData(course_id=course_id, title=raw_course_title),
            )

        document_id = r.get("document_id")
        if isinstance(document_id, str) and document_id:
            doc_node_id = f"document_{document_id}"
            if doc_node_id not in nodes_by_id:
                source_filename = (
                    str(r.get("source_filename"))
                    if isinstance(r.get("source_filename"), str)
                    else None
                )
                topic = str(r.get("topic")) if isinstance(r.get("topic"), str) else None
                extracted_at = (
                    str(r.get("extracted_at"))
                    if isinstance(r.get("extracted_at"), str)
                    else None
                )
                nodes_by_id[doc_node_id] = GraphNode(
                    id=doc_node_id,
                    kind=GraphNodeKind.DOCUMENT,
                    label=source_filename or document_id,
                    data=DocumentNodeData(
                        document_id=document_id,
                        course_id=course_id,
                        source_filename=source_filename,
                        topic=topic,
                        extracted_at=extracted_at,
                    ),
                )

            has_doc_edge_id = f"has_document_{course_id}_{document_id}"
            if has_doc_edge_id not in edges_by_id:
                edges_by_id[has_doc_edge_id] = GraphEdge(
                    id=has_doc_edge_id,
                    kind=GraphEdgeKind.HAS_DOCUMENT,
                    source=class_node_id,
                    target=doc_node_id,
                    data=None,
                )

            concept_name = r.get("concept_name")
            if isinstance(concept_name, str) and concept_name:
                concept_node_id = f"concept_{concept_name}"
                if concept_node_id not in nodes_by_id:
                    if concept_count >= max_concepts:
                        continue
                    concept_count += 1
                    nodes_by_id[concept_node_id] = GraphNode(
                        id=concept_node_id,
                        kind=GraphNodeKind.CONCEPT,
                        label=concept_name,
                        data=ConceptNodeData(name=concept_name),
                    )

                mentions_edge_id = f"mentions_{document_id}_{concept_name}"
                if mentions_edge_id not in edges_by_id:
                    definition = (
                        str(r.get("definition"))
                        if isinstance(r.get("definition"), str)
                        else None
                    )
                    text_evidence = (
                        str(r.get("text_evidence"))
                        if isinstance(r.get("text_evidence"), str)
                        else None
                    )
                    source_document = (
                        str(r.get("source_document"))
                        if isinstance(r.get("source_document"), str)
                        else None
                    )
                    edges_by_id[mentions_edge_id] = GraphEdge(
                        id=mentions_edge_id,
                        kind=GraphEdgeKind.MENTIONS,
                        source=doc_node_id,
                        target=concept_node_id,
                        data=MentionsEdgeData(
                            definition=definition,
                            text_evidence=text_evidence,
                            source_document=source_document,
                        ),
                    )

    return CourseGraphResponse(
        nodes=list(nodes_by_id.values()),
        edges=list(edges_by_id.values()),
    )
