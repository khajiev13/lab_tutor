from __future__ import annotations

import logging

from neo4j import Session as Neo4jSession

logger = logging.getLogger(__name__)

# ── Full curriculum tree ───────────────────────────────────────
_CURRICULUM_TREE_QUERY = """
MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(b:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)
WITH b, ch ORDER BY ch.chapter_index

RETURN
    b.title AS book_title,
    b.authors AS book_authors,
    ch.chapter_index AS chapter_index,
    ch.title AS chapter_title,
    ch.summary AS chapter_summary,
    COLLECT {
        MATCH (ch)-[:HAS_SECTION]->(s:BOOK_SECTION)
        RETURN s {
            section_index: s.section_index,
            title: s.title,
            concepts: [(s)-[sm:MENTIONS]->(sc:CONCEPT) | {
                name: sc.name,
                description: sc.description,
                definition: sm.definition
            }]
        } AS section
        ORDER BY s.section_index
    } AS sections,
    [(ch)-[:HAS_SKILL]->(bsk:BOOK_SKILL) | bsk {
        .name,
        .description,
        source: 'book',
        concepts: [(bsk)-[:REQUIRES_CONCEPT]->(bc:CONCEPT) | bc { .name, .description }]
    }] AS book_skills,
    [(ch)-[:HAS_SKILL]->(msk:MARKET_SKILL) | msk {
        .name,
        source: 'market_demand',
        .category,
        .frequency,
        .demand_pct,
        .priority,
        .status,
        .reasoning,
        .rationale,
        created_at: toString(msk.created_at),
        concepts: [(msk)-[:REQUIRES_CONCEPT]->(mc:CONCEPT) | mc { .name, .description }],
        job_postings: [(msk)-[:SOURCED_FROM]->(jp:JOB_POSTING) | jp { .url, .title, .company, .site }]
    }] AS market_skills

ORDER BY ch.chapter_index
"""

# ── Changelog: market-skill insertions ordered by time ──────────
_CHANGELOG_QUERY = """
MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(b:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(ms:MARKET_SKILL)
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
