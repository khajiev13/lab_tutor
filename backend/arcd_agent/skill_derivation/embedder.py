"""Concept extraction and SentenceTransformer embedding."""

from __future__ import annotations

import numpy as np


def extract_concepts(
    driver,
    course_id: str | None = None,
) -> list[dict[str, str]]:
    """Query CONCEPT nodes from Neo4j, optionally filtered by course."""
    with driver.session() as session:
        if course_id:
            result = session.run(
                "MATCH (c:CONCEPT) WHERE c.area = $cid OR c.course_id = $cid "
                "RETURN c.concept_id AS cid, c.name AS name, "
                "coalesce(c.description, '') AS desc ORDER BY c.name",
                cid=course_id,
            )
        else:
            result = session.run(
                "MATCH (c:CONCEPT) RETURN c.concept_id AS cid, c.name AS name, "
                "coalesce(c.description, '') AS desc ORDER BY c.name"
            )
        concepts = []
        for r in result:
            cid = r["cid"] or r["name"]
            name = r["name"] or ""
            desc = r["desc"] or ""
            if name:
                concepts.append({"concept_id": cid, "name": name, "description": desc})
        return concepts


def embed_concepts(
    concepts: list[dict[str, str]],
    model_name: str = "all-MiniLM-L6-v2",
) -> tuple[list[str], np.ndarray]:
    """Embed concepts using SentenceTransformer.

    Returns:
        (concept_ids, embeddings) where embeddings has shape [N, D].
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    texts = [
        f"{c['name']} : {c['description']}" if c["description"] else c["name"]
        for c in concepts
    ]
    ids = [c["concept_id"] for c in concepts]
    embeddings = model.encode(
        texts, batch_size=64, show_progress_bar=True, convert_to_numpy=True
    )
    return ids, embeddings.astype(np.float32)
