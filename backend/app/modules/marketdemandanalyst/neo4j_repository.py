"""Verified course targets and atomic idempotent projection of approved SQL intent."""

import json
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from neo4j import Driver

from app.core.settings import settings

_CHAPTERS = """
MATCH (:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)
RETURN toString(ch.id) AS id, ch.title AS title
"""

_EXISTING = """
MATCH (course:CLASS {id: $course_id})
MATCH (skill)
WHERE (
    (skill:BOOK_SKILL AND (
        EXISTS { MATCH (course)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(skill) }
        OR EXISTS { MATCH (course)-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(skill) }
    )) OR ((skill:MARKET_SKILL OR skill:CAREER_SKILL) AND (
        EXISTS { MATCH (course)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(skill) }
        OR EXISTS { MATCH (course)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:RELEVANT_TO_CHAPTER]-(skill) }
    ))
)
WITH course, skill, CASE WHEN valueType(skill.name) STARTS WITH 'STRING' THEN skill.name ELSE head(skill.name) END AS label
WHERE (($target_id <> '' AND (toString(skill.id) = $target_id OR skill.evidence_target_id = $target_id OR elementId(skill) = $target_id))
    OR ($target_id = '' AND toLower(label) = toLower($target_label)))
    AND ($origin = '' OR ($origin = 'book' AND skill:BOOK_SKILL)
        OR ($origin = 'market_demand' AND NOT skill:BOOK_SKILL)
        OR ($origin = 'onet' AND skill:ONET_SKILL))
FOREACH (ignored IN CASE WHEN skill:MARKET_SKILL AND skill.evidence_target_id IS NULL THEN [1] ELSE [] END |
    SET skill.evidence_target_id = randomUUID())
RETURN CASE WHEN skill:BOOK_SKILL THEN 'book' WHEN skill:CAREER_SKILL THEN 'career' ELSE 'market' END AS kind,
    CASE WHEN skill:MARKET_SKILL THEN skill.evidence_target_id ELSE toString(skill.id) END AS id,
    label,
    CASE WHEN skill:BOOK_SKILL THEN 'book' ELSE coalesce(skill.origin, 'market_demand') END AS origin,
    COLLECT {
        MATCH (course)-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)
        WHERE EXISTS { MATCH (skill)-[:MAPPED_TO|RELEVANT_TO_CHAPTER]->(ch) }
        RETURN toString(ch.id) AS id
    } AS chapter_ids
"""

_NEW_TARGET = """
MATCH (skill:CAREER_SKILL {id: $id})
RETURN skill.course_id AS course_id, skill.name AS label
"""

_PROJECT_REFERENCES = """
UNWIND $records AS row
MATCH (course:CLASS {id: row.course_id})
CALL {
    WITH course, row
    WITH course, row WHERE row.target_kind = 'career'
    MERGE (skill:CAREER_SKILL:SKILL {id: row.graph_target_id})
    ON CREATE SET skill.course_id = row.course_id, skill.name = row.label,
        skill.description = row.description, skill.origin = row.origin, skill.identity_key = row.identity_key
    WITH skill, row WHERE skill.course_id = row.course_id AND skill.name = row.label
    FOREACH (ignored IN CASE WHEN row.origin = 'onet' THEN [1] ELSE [] END | SET skill:ONET_SKILL)
    RETURN skill
    UNION ALL
    WITH course, row
    MATCH (skill:BOOK_SKILL)
    WHERE toString(skill.id) = row.graph_target_id AND row.target_kind = 'book' AND (
        EXISTS { MATCH (course)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(skill) }
        OR EXISTS { MATCH (course)-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(skill) }
    )
    RETURN skill
    UNION ALL
    WITH course, row
    MATCH (skill:MARKET_SKILL {evidence_target_id: row.graph_target_id})
    WHERE row.target_kind = 'market' AND (
        EXISTS { MATCH (course)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(skill) }
        OR EXISTS { MATCH (course)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:RELEVANT_TO_CHAPTER]-(skill) }
    )
    RETURN skill
}
WITH course, row, skill,
    CASE WHEN valueType(skill.name) STARTS WITH 'STRING' THEN skill.name ELSE head(skill.name) END AS actual_label
WHERE actual_label = row.label
MATCH (course)-[:HAS_COURSE_CHAPTER]->(chapter:COURSE_CHAPTER)
WHERE toString(chapter.id) IN row.chapter_ids
WITH course, row, skill, collect(DISTINCT chapter) AS chapters
WHERE size(chapters) = size(row.chapter_ids) AND size(chapters) > 0
FOREACH (chapter IN chapters | MERGE (skill)-[:MAPPED_TO]->(chapter))
MERGE (reference:COURSE_SKILL_REFERENCE {id: row.reference_id})
ON CREATE SET reference.course_id = row.course_id, reference.target_identity = row.target_identity
WITH course, row, skill, reference
WHERE reference.course_id = row.course_id AND reference.target_identity = row.target_identity
SET reference.available_for_new_selection = row.available, reference.approved_revision = row.approved_revision,
    reference.projection_revision = row.approved_revision, reference.source = row.source, reference.origin = row.origin
MERGE (course)-[:HAS_COURSE_SKILL_REFERENCE]->(reference)
MERGE (reference)-[:FOR_SKILL]->(skill)
FOREACH (concept IN row.concepts |
    MERGE (node:CONCEPT {name: concept.name})
    ON CREATE SET node.description = concept.description
    MERGE (skill)-[:REQUIRES_CONCEPT]->(node)
)
RETURN reference.id AS id
"""

_PROJECT_BINDINGS = """
UNWIND $records AS row
MATCH (reference:COURSE_SKILL_REFERENCE {id: row.reference_id, course_id: row.course_id})-[:FOR_SKILL]->(skill)
MATCH (course:CLASS {id: row.course_id})
MERGE (binding:SKILL_EVIDENCE_BINDING {id: row.binding_id})
ON CREATE SET binding.course_id = row.course_id, binding.skill_reference_id = row.reference_id,
    binding.approval_id = row.approval_id, binding.run_id = row.run_id, binding.candidate_id = row.candidate_id,
    binding.review_digest = row.review_digest, binding.evidence_id = row.evidence_id,
    binding.mapping_relation = row.mapping_relation, binding.rationale = row.rationale
WITH course, reference, skill, binding, row
WHERE binding.course_id = row.course_id AND binding.skill_reference_id = row.reference_id
    AND binding.approval_id = row.approval_id AND binding.run_id = row.run_id
    AND binding.candidate_id = row.candidate_id AND binding.evidence_id = row.evidence_id
    AND binding.review_digest = row.review_digest
SET binding.active = true
MERGE (evidence:CAREER_EVIDENCE {id: row.evidence_id})
SET evidence.source = row.source, evidence.public_json = row.evidence_json,
    evidence.source_url = row.source_url
FOREACH (ignored IN CASE WHEN row.source = 'jobs' THEN [1] ELSE [] END | SET evidence:MARKET_VACANCY_EVIDENCE)
FOREACH (ignored IN CASE WHEN row.source = 'onet' THEN [1] ELSE [] END | SET evidence:ONET_EVIDENCE)
MERGE (course)-[:HAS_SKILL_EVIDENCE]->(binding)
MERGE (reference)-[:HAS_SKILL_EVIDENCE]->(binding)
MERGE (binding)-[:FOR_SKILL]->(skill)
MERGE (binding)-[:HAS_EVIDENCE]->(evidence)
FOREACH (url IN row.job_urls |
    MERGE (posting:JOB_POSTING {url: url})
    MERGE (skill)-[:SOURCED_FROM]->(posting)
)
RETURN binding.id AS id
"""


class MarketSkillGraphRepository:
    def __init__(self, driver: Driver, *, database: str | None = None):
        self._driver = driver
        self._database = database or settings.neo4j_database

    def resolve_targets(self, course_id: int, proposals: list[dict]) -> list[dict]:
        with self._driver.session(database=self._database) as session:
            return session.execute_write(self._resolve_targets, course_id, proposals)

    @staticmethod
    def _resolve_targets(tx, course_id: int, proposals: list[dict]) -> list[dict]:
        chapters = {
            row["id"]: row["title"] for row in tx.run(_CHAPTERS, course_id=course_id)
        }
        results = []
        for row in proposals:
            if row["disposition"] == "new":
                target_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        json.dumps(
                            [
                                "lab-tutor",
                                "career-target",
                                course_id,
                                row["identity_key"],
                            ],
                            separators=(",", ":"),
                        ),
                    )
                )
                found = tx.run(_NEW_TARGET, id=target_id).single()
                if found and found["course_id"] != course_id:
                    raise HTTPException(422, "Target is outside this course")
                target = {
                    "identity": f"career:{target_id}",
                    "label": found["label"] if found else row["name"],
                    "source": "market",
                    "origin": row.get("origin", "market_demand"),
                }
                mapped = []
            else:
                target_id = row.get("graph_target_id", "")
                target_hint = row.get("target") or {}
                if not target_id and target_hint.get("identity"):
                    target_id = target_hint["identity"].split(":", 1)[-1]
                found = list(
                    tx.run(
                        _EXISTING,
                        course_id=course_id,
                        target_id=str(target_id),
                        target_label=row.get("target_label")
                        or row.get("overlaps_with")
                        or row["name"],
                        origin=row.get("origin", "")
                        if row.get("origin") == "book"
                        else "",
                    )
                )
                if len(found) != 1:
                    raise HTTPException(
                        422, "Target is not uniquely reachable in this course"
                    )
                match = found[0]
                target = {
                    "identity": f"{match['kind']}:{match['id']}",
                    "label": match["label"],
                    "source": "book" if match["kind"] == "book" else "market",
                    "origin": match["origin"],
                }
                mapped = match["chapter_ids"]
            requested = list(
                dict.fromkeys(str(value) for value in row.get("chapter_ids", []))
            )
            if not requested and row.get("target_chapter"):
                requested = [
                    key
                    for key, title in chapters.items()
                    if title == row["target_chapter"]
                ]
                if len(requested) > 1:
                    raise HTTPException(422, "Chapter title is ambiguous; use its ID")
            requested = requested or mapped
            if not requested or set(requested) - set(chapters):
                raise HTTPException(422, "Choose verified course chapter IDs")
            concepts = []
            for concept in row.get("concepts", []):
                value = {"name": concept} if isinstance(concept, str) else concept
                if (
                    not isinstance(value, dict)
                    or not isinstance(value.get("name"), str)
                    or not value["name"].strip()
                ):
                    raise HTTPException(422, "Concept proposals need concrete names")
                concepts.append(
                    {
                        "name": value["name"].strip(),
                        "description": value.get("description"),
                    }
                )
            results.append(
                {
                    **row,
                    "target": target,
                    "chapters": [
                        {"chapter_id": key, "title": chapters[key]} for key in requested
                    ],
                    "concepts": concepts,
                }
            )
        return results

    def project(self, references: list[dict], bindings: list[dict]) -> None:
        with self._driver.session(database=self._database) as session:
            session.execute_write(self._project, references, bindings)

    def redact(self, records: list[dict]) -> None:
        with self._driver.session(database=self._database) as session:
            session.execute_write(self._redact, records)

    @staticmethod
    def _redact(tx, records: list[dict]) -> None:
        tx.run(
            """
            UNWIND $records AS row
            MATCH (e:CAREER_EVIDENCE {id: row.evidence_id})
            SET e.public_json = row.evidence_json, e.content_removed = true
            """,
            records=records,
        ).consume()
        tx.run(
            """
            UNWIND $records AS row
            UNWIND row.binding_ids AS id
            MATCH (b:SKILL_EVIDENCE_BINDING {id: id, course_id: row.course_id})
            SET b.active = false
            """,
            records=records,
        ).consume()
        tx.run(
            """
            UNWIND $records AS row
            UNWIND row.reference_states AS state
            MATCH (r:COURSE_SKILL_REFERENCE {id: state.reference_id, course_id: row.course_id})
            SET r.available_for_new_selection = state.available
            """,
            records=records,
        ).consume()

    @staticmethod
    def _project(tx, references: list[dict], bindings: list[dict]) -> None:
        ids = [row["reference_id"] for row in references]
        tx.run(
            "UNWIND $ids AS id MATCH (r:COURSE_SKILL_REFERENCE {id: id})-[:HAS_SKILL_EVIDENCE]->(b:SKILL_EVIDENCE_BINDING) SET b.active = false",
            ids=ids,
        ).consume()
        matched = [row["id"] for row in tx.run(_PROJECT_REFERENCES, records=references)]
        if set(matched) != set(ids) or len(matched) != len(ids):
            raise ValueError("Not every reference matched a verified course target")
        expected = {row["binding_id"] for row in bindings}
        matched = [row["id"] for row in tx.run(_PROJECT_BINDINGS, records=bindings)]
        if set(matched) != expected or len(matched) != len(bindings):
            raise ValueError("Not every binding matched its verified course reference")
