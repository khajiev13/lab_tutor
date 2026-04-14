"""Utility helpers for chunking analysis phase."""

from __future__ import annotations

import logging

import numpy as np
from neo4j import GraphDatabase

from app.core.settings import settings

from .state import CHUNK_OVERLAP, CHUNK_SIZE, SEPARATORS

logger = logging.getLogger(__name__)


def chunk_paragraphs_text(text: str) -> list[str]:
    """Paragraph-level chunking with RecursiveCharacterTextSplitter."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=SEPARATORS,
    )
    return splitter.split_text(text)


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return matrix / norms


def build_sim_distribution(max_sims: np.ndarray) -> list[dict]:
    if max_sims.size == 0:
        return []

    buckets: list[dict] = []
    for idx in range(20):
        start = idx * 0.05
        end = start + 0.05
        if idx == 19:
            count = int(np.sum((max_sims >= start) & (max_sims <= end)))
        else:
            count = int(np.sum((max_sims >= start) & (max_sims < end)))
        buckets.append(
            {
                "bucket_start": round(start, 2),
                "bucket_end": round(end, 2),
                "count": count,
            }
        )
    return buckets


def load_course_concepts(course_id: int) -> list[dict]:
    uri = settings.neo4j_uri
    username = settings.neo4j_username
    password = settings.neo4j_password
    if not (uri and username and password):
        raise ValueError("Neo4j is not configured; cannot score concept coverage")

    query = """
    MATCH (d:TEACHER_UPLOADED_DOCUMENT {course_id: $course_id})-[m:MENTIONS]->(c:CONCEPT)
    RETURN
      c.name AS concept_name,
      d.topic AS doc_topic,
      coalesce(m.text_evidence, m.definition, '') AS text_evidence,
      c.embedding AS name_embedding,
      coalesce(m.text_evidence_embedding, m.definition_embedding) AS evidence_embedding
    ORDER BY concept_name ASC
    """

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=settings.neo4j_database) as session:
            rows = session.run(query, {"course_id": course_id}).data()
    finally:
        driver.close()

    by_name: dict[str, dict] = {}
    for row in rows:
        raw_name = row.get("concept_name") or ""
        if isinstance(raw_name, list):
            raw_name = raw_name[0] if raw_name else ""
        concept_name = str(raw_name).strip()
        name_embedding = row.get("name_embedding")
        if not concept_name or not name_embedding:
            continue

        existing = by_name.get(concept_name)
        candidate = {
            "concept_name": concept_name,
            "doc_topic": row.get("doc_topic"),
            "text_evidence": row.get("text_evidence") or None,
            "name_embedding": [float(v) for v in name_embedding],
            "evidence_embedding": (
                [float(v) for v in row["evidence_embedding"]]
                if row.get("evidence_embedding")
                else None
            ),
        }
        if existing is None:
            by_name[concept_name] = candidate
            continue

        if not existing.get("text_evidence") and candidate.get("text_evidence"):
            by_name[concept_name] = candidate

    concepts = list(by_name.values())
    if not concepts:
        raise ValueError(f"No embedded course concepts found for course {course_id}")

    # All embeddings must be the expected dimension (default 2048).
    # Re-embed any concepts with wrong dimensions and update Neo4j.
    expected_dim = settings.embedding_dims or 2048
    bad = [c for c in concepts if len(c["name_embedding"]) != expected_dim]
    if bad:
        logger.warning(
            "Re-embedding %d concepts with wrong dim (expected %d)",
            len(bad),
            expected_dim,
        )
        from app.modules.embeddings.embedding_service import EmbeddingService

        embedder = EmbeddingService()
        bad_names = [c["concept_name"] for c in bad]
        new_vecs = embedder.embed_documents(bad_names)

        reembed_driver = GraphDatabase.driver(uri, auth=(username, password))
        try:
            with reembed_driver.session(database=settings.neo4j_database) as neo_sess:
                for concept, vec in zip(bad, new_vecs, strict=True):
                    concept["name_embedding"] = vec
                    neo_sess.run(
                        "MATCH (c:CONCEPT {name: toLower($name)}) "
                        "SET c.embedding = $vec",
                        {"name": concept["concept_name"], "vec": vec},
                    )
        finally:
            reembed_driver.close()
        logger.info("Re-embedded and updated %d concepts in Neo4j", len(bad))

    return concepts


__all__ = [
    "chunk_paragraphs_text",
    "l2_normalize",
    "build_sim_distribution",
    "load_course_concepts",
]
