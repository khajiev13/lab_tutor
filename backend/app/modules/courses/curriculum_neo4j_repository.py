from __future__ import annotations

import logging

from neo4j import Session as Neo4jSession

logger = logging.getLogger(__name__)

# ── Full curriculum tree ───────────────────────────────────────
_CURRICULUM_TREE_QUERY = """
MATCH (cl:CLASS {id: $course_id})-[:USES_BOOK]->(b:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)
WITH b, ch ORDER BY ch.chapter_index

// Sections + their concepts
OPTIONAL MATCH (ch)-[:HAS_SECTION]->(s:BOOK_SECTION)
WITH b, ch, s ORDER BY s.section_index
OPTIONAL MATCH (s)-[sm:MENTIONS]->(sc:CONCEPT)
WITH b, ch, s,
     collect(DISTINCT {name: sc.name, description: sc.description, definition: sm.definition}) AS sec_concepts
WITH b, ch,
     collect(DISTINCT {
         section_index: s.section_index,
         title: s.title,
         concepts: sec_concepts
     }) AS sections

// Book skills
OPTIONAL MATCH (ch)-[:HAS_SKILL]->(bsk:BOOK_SKILL)
OPTIONAL MATCH (bsk)-[:REQUIRES_CONCEPT]->(bc:CONCEPT)
WITH b, ch, sections, bsk,
     collect(DISTINCT {name: bc.name, description: bc.description}) AS bsk_concepts
WITH b, ch, sections,
     collect(DISTINCT CASE WHEN bsk IS NOT NULL THEN {
         name: bsk.name,
         description: bsk.description,
         source: 'book',
         concepts: bsk_concepts
     } END) AS book_skills

// Market skills
OPTIONAL MATCH (ch)-[:HAS_SKILL]->(msk:MARKET_SKILL)
OPTIONAL MATCH (msk)-[:REQUIRES_CONCEPT]->(mc:CONCEPT)
WITH b, ch, sections, book_skills, msk,
     collect(DISTINCT {name: mc.name, description: mc.description}) AS msk_concepts
OPTIONAL MATCH (msk)-[:SOURCED_FROM]->(jp:JOB_POSTING)
WITH b, ch, sections, book_skills, msk, msk_concepts,
     collect(DISTINCT {url: jp.url, title: jp.title, company: jp.company, site: jp.site}) AS job_postings
WITH b, ch, sections, book_skills,
     collect(DISTINCT CASE WHEN msk IS NOT NULL THEN {
         name: msk.name,
         source: 'market_demand',
         category: msk.category,
         frequency: msk.frequency,
         demand_pct: msk.demand_pct,
         priority: msk.priority,
         status: msk.status,
         reasoning: msk.reasoning,
         rationale: msk.rationale,
         created_at: toString(msk.created_at),
         concepts: msk_concepts,
         job_postings: job_postings
     } END) AS market_skills

RETURN
    b.title AS book_title,
    b.authors AS book_authors,
    ch.chapter_index AS chapter_index,
    ch.title AS chapter_title,
    ch.summary AS chapter_summary,
    sections,
    book_skills,
    market_skills
ORDER BY ch.chapter_index
"""

# ── Changelog: market-skill insertions ordered by time ──────────
_CHANGELOG_QUERY = """
MATCH (cl:CLASS {id: $course_id})-[:USES_BOOK]->(b:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(ms:MARKET_SKILL)
WHERE ms.created_at IS NOT NULL
RETURN
    toString(ms.created_at) AS timestamp,
    ms.source AS agent,
    ms.name AS skill_name,
    ms.status AS skill_status,
    ms.category AS category,
    ch.title AS chapter
ORDER BY ms.created_at DESC
"""


class CurriculumNeo4jRepository:
    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    def get_curriculum_tree(self, course_id: int) -> dict | None:
        """Return raw records for the full curriculum tree, or None if no book linked."""
        result = self._session.run(_CURRICULUM_TREE_QUERY, course_id=course_id)
        records = [r.data() for r in result]
        if not records:
            return None

        first = records[0]
        return {
            "book_title": first.get("book_title"),
            "book_authors": first.get("book_authors"),
            "chapters": records,
        }

    def get_changelog(self, course_id: int) -> list[dict]:
        """Return market-skill changelog entries ordered by time desc."""
        result = self._session.run(_CHANGELOG_QUERY, course_id=course_id)
        return [r.data() for r in result]
