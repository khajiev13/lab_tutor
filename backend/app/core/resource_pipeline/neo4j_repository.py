"""Neo4j repository: load skills, write/read resource nodes."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from neo4j import Session as Neo4jSession

from .schemas import CandidateResource, ResourceScore, SkillProfile

logger = logging.getLogger(__name__)


def load_skills_from_neo4j(session: Neo4jSession, course_id: int) -> list[SkillProfile]:
    """Load all BOOK_SKILL and MARKET_SKILL nodes for a course."""
    skills: list[SkillProfile] = []

    # Course level
    course_row = session.run(
        "MATCH (cl:CLASS {id: $course_id}) RETURN cl.title AS title, cl.description AS desc",
        course_id=course_id,
    ).single()
    course_level = "bachelor"
    if course_row and course_row["desc"]:
        desc_lower = (course_row["desc"] or "").lower()
        if "master" in desc_lower or "graduate" in desc_lower:
            course_level = "master"
        elif "phd" in desc_lower or "doctoral" in desc_lower:
            course_level = "phd"

    # BOOK_SKILL nodes
    book_result = session.run(
        "MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(sk:BOOK_SKILL) "
        "RETURN sk {"
        "  .name, .description, "
        "  ch_title: ch.title, ch_summary: ch.summary, ch_idx: ch.chapter_index, "
        "  concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | {"
        "    name: CASE WHEN valueType(c.name) STARTS WITH 'STRING' THEN c.name ELSE head(c.name) END, "
        "    definition: CASE WHEN c.description IS NOT NULL THEN c.description ELSE '' END, "
        "    embedding: c.embedding"
        "  }]"
        "} AS skill "
        "ORDER BY skill.ch_idx",
        course_id=course_id,
    )
    for r in book_result:
        skill = r["skill"]
        concepts = [c for c in skill["concepts"] if c.get("name")]
        skills.append(
            SkillProfile(
                name=skill["name"],
                skill_type="book",
                description=skill["description"] or "",
                chapter_title=skill["ch_title"] or "",
                chapter_summary=skill["ch_summary"] or "",
                chapter_index=skill["ch_idx"] or 0,
                concepts=concepts,
                course_level=course_level,
            )
        )

    # MARKET_SKILL nodes
    market_result = session.run(
        "MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(ms:MARKET_SKILL) "
        "RETURN ms {"
        "  .name, .category, .demand_pct, .priority, .status, "
        "  ch_title: ch.title, ch_summary: ch.summary, ch_idx: ch.chapter_index, "
        "  concepts: [(ms)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | {"
        "    name: CASE WHEN valueType(c.name) STARTS WITH 'STRING' THEN c.name ELSE head(c.name) END, "
        "    definition: CASE WHEN c.description IS NOT NULL THEN c.description ELSE '' END, "
        "    embedding: c.embedding"
        "  }], "
        "  job_descs: [(ms)-[:SOURCED_FROM]->(jp:JOB_POSTING) | jp.description][0..3]"
        "} AS skill "
        "ORDER BY skill.ch_idx",
        course_id=course_id,
    )
    for r in market_result:
        skill = r["skill"]
        concepts = [c for c in skill["concepts"] if c.get("name")]
        job_evidence = [d[:500] for d in (skill["job_descs"] or []) if d]
        skills.append(
            SkillProfile(
                name=skill["name"],
                skill_type="market",
                category=skill["category"] or "",
                demand_pct=skill["demand_pct"] or 0.0,
                priority=skill["priority"] or "",
                status=skill["status"] or "",
                chapter_title=skill["ch_title"] or "",
                chapter_summary=skill["ch_summary"] or "",
                chapter_index=skill["ch_idx"] or 0,
                concepts=concepts,
                job_evidence=job_evidence,
                course_level=course_level,
            )
        )

    return skills


def write_resources(
    session: Neo4jSession,
    skill_name: str,
    skill_type: str,
    resources: list[tuple[CandidateResource, ResourceScore, float]],
    resource_label: str,
    relationship: str,
) -> int:
    """Write resource nodes and link them to the skill. Returns count written."""
    skill_label = "BOOK_SKILL" if skill_type == "book" else "MARKET_SKILL"
    now = datetime.now(UTC).isoformat()

    for candidate, score, final_score in resources:
        resource_id = str(uuid.uuid4())
        # Use raw Cypher with MERGE on URL to be idempotent
        session.run(
            f"MATCH (sk:{skill_label} {{name: $skill_name}}) "
            f"MERGE (r:{resource_label} {{url: $url}}) "
            f"ON CREATE SET r.id = $id, r.title = $title, r.domain = $domain, "
            f"  r.snippet = $snippet, r.search_content = $search_content, "
            f"  r.video_id = $video_id, r.search_result_url = $search_result_url, "
            f"  r.search_result_domain = $search_result_domain, "
            f"  r.source_engine = $source_engine, r.source_engines = $source_engines, "
            f"  r.search_metadata_json = $search_metadata_json, "
            f"  r.resource_type = $resource_type, r.estimated_year = $estimated_year, "
            f"  r.final_score = $final_score, r.concepts_covered = $concepts_covered, "
            f"  r.created_at = datetime($created_at) "
            f"ON MATCH SET r.title = $title, r.domain = $domain, r.snippet = $snippet, "
            f"  r.search_content = $search_content, r.video_id = $video_id, "
            f"  r.search_result_url = $search_result_url, "
            f"  r.search_result_domain = $search_result_domain, "
            f"  r.source_engine = $source_engine, r.source_engines = $source_engines, "
            f"  r.search_metadata_json = $search_metadata_json, "
            f"  r.resource_type = $resource_type, r.estimated_year = $estimated_year, "
            f"  r.final_score = $final_score, r.concepts_covered = $concepts_covered "
            f"MERGE (sk)-[:{relationship}]->(r)",
            skill_name=skill_name,
            id=resource_id,
            url=candidate.url,
            title=candidate.title,
            domain=candidate.domain,
            snippet=candidate.snippet[:500],
            search_content=candidate.search_content[:4000],
            video_id=candidate.video_id,
            search_result_url=candidate.search_result_url,
            search_result_domain=candidate.search_result_domain,
            source_engine=candidate.source_engine,
            source_engines=candidate.source_engines,
            search_metadata_json=candidate.metadata_json(),
            resource_type=score.resource_type,
            estimated_year=score.estimated_year,
            final_score=final_score,
            concepts_covered=score.concepts_covered,
            created_at=now,
        )
    return len(resources)


def get_resources_for_course(
    session: Neo4jSession,
    course_id: int,
    resource_label: str,
    relationship: str,
) -> list[dict]:
    """Read all resources grouped by skill for a course."""
    result = session.run(
        f"MATCH (cl:CLASS {{id: $course_id}})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->"
        f"(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(sk)-[:{relationship}]->(r:{resource_label}) "
        f"WITH sk, ch, r ORDER BY r.final_score DESC "
        f"WITH sk, ch, collect(r {{"
        f"  .title, .url, "
        f"  domain: coalesce(r.domain, ''), "
        f"  snippet: coalesce(r.snippet, ''), "
        f"  search_content: coalesce(r.search_content, ''), "
        f"  video_id: coalesce(r.video_id, ''), "
        f"  search_result_url: coalesce(r.search_result_url, ''), "
        f"  search_result_domain: coalesce(r.search_result_domain, ''), "
        f"  source_engine: coalesce(r.source_engine, ''), "
        f"  source_engines: coalesce(r.source_engines, []), "
        f"  search_metadata_json: coalesce(r.search_metadata_json, '[]'), "
        f"  .resource_type, .estimated_year, .final_score, "
        f"  concepts_covered: coalesce(r.concepts_covered, [])"
        f"}}) AS resources "
        f"RETURN sk.name AS skill_name, "
        f"  CASE WHEN sk:BOOK_SKILL THEN 'book' ELSE 'market' END AS skill_type, "
        f"  ch.title AS chapter_title, resources "
        f"ORDER BY ch.chapter_index",
        course_id=course_id,
    )
    return [r.data() for r in result]
