from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import LiteralString

from fastapi import HTTPException, Request, status
from neo4j import Driver, GraphDatabase
from neo4j import Session as Neo4jSession
from neo4j.exceptions import Neo4jError

from app.core.settings import settings

logger = logging.getLogger(__name__)


def create_neo4j_driver() -> Driver | None:
    """Create a Neo4j driver if configured.

    This keeps the app runnable without Neo4j in local/test environments.
    """

    if not (settings.neo4j_uri and settings.neo4j_username and settings.neo4j_password):
        return None

    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
        max_connection_lifetime=200,
        keep_alive=True,
    )


def verify_neo4j_connectivity(driver: Driver) -> None:
    driver.verify_connectivity()


def initialize_neo4j_constraints(driver: Driver) -> None:
    """Best-effort constraints/indexes initializer.

    Uses IF NOT EXISTS so it is safe and idempotent.
    """

    statements: list[LiteralString] = [
        # Canonical identity constraints
        "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:USER) REQUIRE u.id IS UNIQUE",
        "CREATE CONSTRAINT class_id_unique IF NOT EXISTS FOR (c:CLASS) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:CONCEPT) REQUIRE c.name IS UNIQUE",
        "CREATE CONSTRAINT teacher_uploaded_document_id_unique IF NOT EXISTS FOR (d:TEACHER_UPLOADED_DOCUMENT) REQUIRE d.id IS UNIQUE",
        # Prefer stable dedupe by content hash per course (best-effort; may fail on older Neo4j versions).
        "CREATE CONSTRAINT teacher_uploaded_document_course_hash_key IF NOT EXISTS "
        "FOR (d:TEACHER_UPLOADED_DOCUMENT) REQUIRE (d.course_id, d.content_hash) IS NODE KEY",
        # Curriculum graph constraints
        "CREATE CONSTRAINT book_chapter_id_unique IF NOT EXISTS FOR (ch:BOOK_CHAPTER) REQUIRE ch.id IS UNIQUE",
        "CREATE CONSTRAINT book_section_id_unique IF NOT EXISTS FOR (s:BOOK_SECTION) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT book_skill_id_unique IF NOT EXISTS FOR (sk:BOOK_SKILL) REQUIRE sk.id IS UNIQUE",
        "CREATE CONSTRAINT course_chapter_id_unique IF NOT EXISTS FOR (ch:COURSE_CHAPTER) REQUIRE ch.id IS UNIQUE",
        "CREATE INDEX course_chapter_course_id_idx IF NOT EXISTS FOR (ch:COURSE_CHAPTER) ON (ch.course_id)",
        "CREATE CONSTRAINT book_id_unique IF NOT EXISTS FOR (b:BOOK) REQUIRE b.id IS UNIQUE",
        "CREATE CONSTRAINT market_skill_name_unique IF NOT EXISTS FOR (ms:MARKET_SKILL) REQUIRE ms.name IS UNIQUE",
        "CREATE CONSTRAINT question_id_unique IF NOT EXISTS FOR (q:QUESTION) REQUIRE q.id IS UNIQUE",
        "CREATE CONSTRAINT reading_resource_id_unique IF NOT EXISTS FOR (r:READING_RESOURCE) REQUIRE r.id IS UNIQUE",
        "CREATE CONSTRAINT reading_resource_url_unique IF NOT EXISTS FOR (r:READING_RESOURCE) REQUIRE r.url IS UNIQUE",
        "CREATE CONSTRAINT video_resource_id_unique IF NOT EXISTS FOR (v:VIDEO_RESOURCE) REQUIRE v.id IS UNIQUE",
        "CREATE CONSTRAINT video_resource_url_unique IF NOT EXISTS FOR (v:VIDEO_RESOURCE) REQUIRE v.url IS UNIQUE",
        # Helpful indexes
        "CREATE INDEX class_title_idx IF NOT EXISTS FOR (c:CLASS) ON (c.title)",
        "CREATE INDEX teacher_uploaded_document_course_id_idx IF NOT EXISTS FOR (d:TEACHER_UPLOADED_DOCUMENT) ON (d.course_id)",
        "CREATE INDEX skill_name_idx IF NOT EXISTS FOR (s:SKILL) ON (s.name)",
        "CREATE INDEX skill_prerequisite_confidence_idx IF NOT EXISTS FOR ()-[r:PREREQUISITE]-() ON (r.confidence)",
    ]

    embedding_dims = settings.embedding_dims
    vector_statements: list[LiteralString] = []
    relationship_vector_statements: list[LiteralString] = []
    if embedding_dims is not None:
        vector_statements.append(
            "CREATE VECTOR INDEX teacher_uploaded_document_summary_embedding_vector_idx IF NOT EXISTS "
            "FOR (d:TEACHER_UPLOADED_DOCUMENT) ON (d.summary_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: "
            + str(int(embedding_dims))
            + ", `vector.similarity_function`: 'cosine'}}"
        )

        vector_statements.append(
            "CREATE VECTOR INDEX concept_embedding_idx IF NOT EXISTS "
            "FOR (c:CONCEPT) ON (c.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: "
            + str(int(embedding_dims))
            + ", `vector.similarity_function`: 'cosine'}}"
        )

        vector_statements.append(
            "CREATE VECTOR INDEX book_chapter_summary_vector_idx IF NOT EXISTS "
            "FOR (ch:BOOK_CHAPTER) ON (ch.summary_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: "
            + str(int(embedding_dims))
            + ", `vector.similarity_function`: 'cosine'}}"
        )

        vector_statements.append(
            "CREATE VECTOR INDEX skill_name_embedding_idx IF NOT EXISTS "
            "FOR (s:SKILL) ON (s.name_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: "
            + str(int(embedding_dims))
            + ", `vector.similarity_function`: 'cosine'}}"
        )

        vector_statements.append(
            "CREATE VECTOR INDEX skill_description_embedding_idx IF NOT EXISTS "
            "FOR (s:SKILL) ON (s.description_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: "
            + str(int(embedding_dims))
            + ", `vector.similarity_function`: 'cosine'}}"
        )

        # Relationship vector indexes are not supported on all Neo4j versions.
        relationship_vector_statements.append(
            "CREATE VECTOR INDEX mentions_definition_embedding_vector_idx IF NOT EXISTS "
            "FOR ()-[m:MENTIONS]-() ON (m.definition_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: "
            + str(int(embedding_dims))
            + ", `vector.similarity_function`: 'cosine'}}"
        )
        relationship_vector_statements.append(
            "CREATE VECTOR INDEX mentions_text_evidence_embedding_vector_idx IF NOT EXISTS "
            "FOR ()-[m:MENTIONS]-() ON (m.text_evidence_embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: "
            + str(int(embedding_dims))
            + ", `vector.similarity_function`: 'cosine'}}"
        )

    try:
        with driver.session(database=settings.neo4j_database) as session:
            for stmt in statements:
                try:
                    session.run(stmt).consume()
                except Neo4jError:
                    logger.exception("Neo4j schema statement failed (continuing)")

            for stmt in vector_statements:
                try:
                    session.run(stmt).consume()
                except Neo4jError:
                    logger.exception("Neo4j vector index creation failed (continuing)")

            for stmt in relationship_vector_statements:
                try:
                    session.run(stmt).consume()
                except Neo4jError as e:
                    logger.warning(
                        "Neo4j relationship vector index not supported or failed (continuing): %s",
                        str(e),
                    )
    except Neo4jError:
        # Some environments restrict schema ops; don't block app startup.
        logger.exception("Neo4j schema initialization failed (continuing)")


def get_neo4j_driver(request: Request) -> Driver | None:
    return getattr(request.app.state, "neo4j_driver", None)


def get_neo4j_session(request: Request) -> Iterator[Neo4jSession | None]:
    """FastAPI dependency: yields a Neo4j session when configured, else yields None."""

    driver = get_neo4j_driver(request)
    if driver is None:
        yield None
        return

    with driver.session(database=settings.neo4j_database) as session:
        yield session


def require_neo4j_session(request: Request) -> Iterator[Neo4jSession]:
    """FastAPI dependency: yields a Neo4j session or raises 503 if disabled."""

    driver = get_neo4j_driver(request)
    if driver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j is not configured",
        )

    with driver.session(database=settings.neo4j_database) as session:
        yield session


@contextmanager
def neo4j_session_from_request(request: Request) -> Iterator[Neo4jSession | None]:
    """Convenience context manager for places that aren't DI-friendly (e.g., auth hooks)."""

    driver = get_neo4j_driver(request)
    if driver is None:
        yield None
        return

    with driver.session(database=settings.neo4j_database) as session:
        yield session
