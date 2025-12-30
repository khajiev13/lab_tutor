from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import LiteralString

from neo4j import ManagedTransaction
from neo4j import Session as Neo4jSession

logger = logging.getLogger(__name__)

GET_ALL_CONCEPTS: LiteralString = """
MATCH (c:CONCEPT)
RETURN c.name AS name
ORDER BY c.name ASC
"""


GET_COURSE_CONCEPTS: LiteralString = """
MATCH (d:TEACHER_UPLOADED_DOCUMENT {course_id: $course_id})-[:MENTIONS]->(c:CONCEPT)
RETURN DISTINCT c.name AS name
ORDER BY c.name ASC
"""


GET_CONCEPT_DEFINITIONS: LiteralString = """
UNWIND $names AS name
MATCH (c:CONCEPT {name: toLower(name)})
OPTIONAL MATCH (d:TEACHER_UPLOADED_DOCUMENT)-[m:MENTIONS]->(c)
WITH name, collect(DISTINCT m.definition) AS defs
RETURN name AS name, [d IN defs WHERE d IS NOT NULL AND trim(d) <> ""] AS definitions
"""


GET_COURSE_CONCEPT_DEFINITIONS: LiteralString = """
UNWIND $names AS name
MATCH (c:CONCEPT {name: toLower(name)})
OPTIONAL MATCH (d:TEACHER_UPLOADED_DOCUMENT {course_id: $course_id})-[m:MENTIONS]->(c)
WITH name, collect(DISTINCT m.definition) AS defs
RETURN name AS name, [d IN defs WHERE d IS NOT NULL AND trim(d) <> ""] AS definitions
"""

APOC_MERGE_CONCEPTS: LiteralString = """
MERGE (canonical:CONCEPT {name: toLower($canonical)})
WITH canonical
UNWIND $variants AS variant_name
MATCH (variant:CONCEPT)
WHERE toLower(variant.name) = variant_name AND id(variant) <> id(canonical)
WITH canonical, collect(DISTINCT variant) AS variant_nodes
CALL {
  WITH canonical, variant_nodes
  WITH canonical, variant_nodes WHERE size(variant_nodes) > 0
  CALL apoc.refactor.mergeNodes(
    [canonical] + variant_nodes,
    {
      properties: {
        name: "discard",
        aliases: "combine",
        `.*`: "overwrite"
      },
      mergeRels: true
    }
  )
  YIELD node
  RETURN node AS node, true AS merged
  UNION
  WITH canonical, variant_nodes
  WITH canonical, variant_nodes WHERE size(variant_nodes) = 0
  RETURN canonical AS node, false AS merged
}
SET node.aliases = apoc.coll.toSet(
  coalesce(node.aliases, []) + [v IN $variants WHERE toLower(v) <> toLower($canonical)]
)
RETURN node.name AS canonical_name, merged AS merged
"""


class ConceptNormalizationRepository:
    """Neo4j queries for concept normalization (concept bank + definitions + apply-merge).

    IMPORTANT: Review/proposal state is NOT stored in Neo4j.
    Neo4j should contain only the knowledge graph (e.g., :CONCEPT nodes).
    """

    _session: Neo4jSession

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    def list_concepts(self) -> list[dict[str, str]]:
        def _tx(tx: ManagedTransaction) -> list[dict[str, str]]:
            rows = tx.run(GET_ALL_CONCEPTS).data()
            return [{"name": str(r["name"])} for r in rows if r.get("name")]

        return list(self._session.execute_read(_tx))

    def list_concepts_for_course(self, *, course_id: int) -> list[dict[str, str]]:
        params = {"course_id": course_id}

        def _tx(tx: ManagedTransaction) -> list[dict[str, str]]:
            rows = tx.run(GET_COURSE_CONCEPTS, params).data()
            return [{"name": str(r["name"])} for r in rows if r.get("name")]

        return list(self._session.execute_read(_tx))

    def get_concept_definitions(self, names: Sequence[str]) -> dict[str, list[str]]:
        if not names:
            return {}

        params = {"names": [n for n in names if n]}

        def _tx(tx: ManagedTransaction) -> dict[str, list[str]]:
            rows = tx.run(GET_CONCEPT_DEFINITIONS, params).data()
            out: dict[str, list[str]] = {}
            for r in rows:
                name = str(r.get("name") or "")
                defs = r.get("definitions") or []
                out[name] = [str(d) for d in defs if d]
            return out

        return dict(self._session.execute_read(_tx))

    def get_concept_definitions_for_course(
        self, *, names: Sequence[str], course_id: int
    ) -> dict[str, list[str]]:
        if not names:
            return {}

        params = {"names": [n for n in names if n], "course_id": course_id}

        def _tx(tx: ManagedTransaction) -> dict[str, list[str]]:
            rows = tx.run(GET_COURSE_CONCEPT_DEFINITIONS, params).data()
            out: dict[str, list[str]] = {}
            for r in rows:
                name = str(r.get("name") or "")
                defs = r.get("definitions") or []
                out[name] = [str(d) for d in defs if d]
            return out

        return dict(self._session.execute_read(_tx))

    def merge_concepts(self, *, canonical: str, variants: list[str]) -> bool:
        """Merge variant :CONCEPT nodes into a canonical :CONCEPT node.

        Returns True if apoc.refactor.mergeNodes performed an actual merge,
        False if the operation was a no-op (e.g., no distinct variant nodes found).
        """
        canonical_lower = str(canonical or "").casefold()
        variants_list = [str(v).casefold() for v in variants if isinstance(v, str) and v]
        if canonical_lower and canonical_lower not in variants_list:
            variants_list.append(canonical_lower)
        variants_list = sorted(set([v for v in variants_list if v]))
        if not canonical_lower:
            raise ValueError("canonical must be non-empty")

        def _tx(tx: ManagedTransaction) -> bool:
            rows = tx.run(
                APOC_MERGE_CONCEPTS,
                {"canonical": canonical_lower, "variants": variants_list},
            ).data()
            return bool(rows and rows[0].get("merged"))

        return bool(self._session.execute_write(_tx))
