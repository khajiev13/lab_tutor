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
        concepts: [(bsk)-[:REQUIRES_CONCEPT]->(bc:CONCEPT) | bc { .name, .description }],
        readings: [(bsk)-[:HAS_READING]->(rr:READING_RESOURCE) | rr {
            .title, .url,
            domain: coalesce(rr.domain, ''),
            snippet: coalesce(rr.snippet, ''),
            search_content: coalesce(rr.search_content, ''),
            search_result_url: coalesce(rr.search_result_url, ''),
            search_result_domain: coalesce(rr.search_result_domain, ''),
            source_engine: coalesce(rr.source_engine, ''),
            source_engines: coalesce(rr.source_engines, []),
            search_metadata_json: coalesce(rr.search_metadata_json, '[]'),
            .final_score, .resource_type,
            concepts_covered: coalesce(rr.concepts_covered, [])
        }],
        videos: [(bsk)-[:HAS_VIDEO]->(vr:VIDEO_RESOURCE) | vr {
            .title, .url,
            video_id: coalesce(vr.video_id, ''),
            domain: coalesce(vr.domain, ''),
            snippet: coalesce(vr.snippet, ''),
            search_content: coalesce(vr.search_content, ''),
            search_result_url: coalesce(vr.search_result_url, ''),
            search_result_domain: coalesce(vr.search_result_domain, ''),
            source_engine: coalesce(vr.source_engine, ''),
            source_engines: coalesce(vr.source_engines, []),
            search_metadata_json: coalesce(vr.search_metadata_json, '[]'),
            .final_score, .resource_type,
            concepts_covered: coalesce(vr.concepts_covered, [])
        }]
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
        job_postings: [(msk)-[:SOURCED_FROM]->(jp:JOB_POSTING) | jp { .url, .title, .company, .site }],
        readings: [(msk)-[:HAS_READING]->(rr:READING_RESOURCE) | rr {
            .title, .url,
            domain: coalesce(rr.domain, ''),
            snippet: coalesce(rr.snippet, ''),
            search_content: coalesce(rr.search_content, ''),
            search_result_url: coalesce(rr.search_result_url, ''),
            search_result_domain: coalesce(rr.search_result_domain, ''),
            source_engine: coalesce(rr.source_engine, ''),
            source_engines: coalesce(rr.source_engines, []),
            search_metadata_json: coalesce(rr.search_metadata_json, '[]'),
            .final_score, .resource_type,
            concepts_covered: coalesce(rr.concepts_covered, [])
        }],
        videos: [(msk)-[:HAS_VIDEO]->(vr:VIDEO_RESOURCE) | vr {
            .title, .url,
            video_id: coalesce(vr.video_id, ''),
            domain: coalesce(vr.domain, ''),
            snippet: coalesce(vr.snippet, ''),
            search_content: coalesce(vr.search_content, ''),
            search_result_url: coalesce(vr.search_result_url, ''),
            search_result_domain: coalesce(vr.search_result_domain, ''),
            source_engine: coalesce(vr.source_engine, ''),
            source_engines: coalesce(vr.source_engines, []),
            search_metadata_json: coalesce(vr.search_metadata_json, '[]'),
            .final_score, .resource_type,
            concepts_covered: coalesce(vr.concepts_covered, [])
        }]
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

# ── Teacher transcripts (course chapters with included documents) ──
_TEACHER_TRANSCRIPTS_QUERY = """
MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(cc:COURSE_CHAPTER)
WITH cc ORDER BY cc.chapter_index
RETURN cc {
    .title,
    .chapter_index,
    .description,
    .learning_objectives,
    documents: [(cc)-[:INCLUDES_DOCUMENT]->(doc:TEACHER_UPLOADED_DOCUMENT) | doc {
        .topic,
        .source_filename
    }]
} AS chapter
ORDER BY cc.chapter_index
"""

# ── Book skill bank (books → chapters → skills) ──
_BOOK_SKILL_BANK_QUERY = """
MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(b:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)
WITH b, ch ORDER BY ch.chapter_index
WITH b,
     COLLECT(ch {
         .chapter_index,
         chapter_id: ch.id,
         skills: [(ch)-[:HAS_SKILL]->(sk:BOOK_SKILL) | sk { .name, .description }]
     }) AS chapters
RETURN b {
    book_id: b.id,
    .title,
    .authors,
    chapters: chapters
} AS book
ORDER BY b.title
"""

# ── Market skill bank (job postings → skills) ──
_MARKET_SKILL_BANK_QUERY = """
MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp:JOB_POSTING)
WITH jp, COLLECT(DISTINCT ms { .name, .category, .status, .priority, .demand_pct }) AS skills
RETURN jp {
    .title,
    .company,
    .site,
    .url,
    .search_term,
    skills: skills
} AS job_posting
ORDER BY jp.title
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

    def get_teacher_transcripts(self, course_id: int) -> list[dict]:
        """Return course chapters with their included teacher documents."""
        result = self._session.run(_TEACHER_TRANSCRIPTS_QUERY, course_id=course_id)
        return [r.data().get("chapter", {}) for r in result]

    def get_book_skill_bank(self, course_id: int) -> list[dict]:
        """Return books with their chapters and skills."""
        result = self._session.run(_BOOK_SKILL_BANK_QUERY, course_id=course_id)
        return [r.data().get("book", {}) for r in result]

    def get_market_skill_bank(self, course_id: int) -> list[dict]:
        """Return job postings with their associated market skills."""
        result = self._session.run(_MARKET_SKILL_BANK_QUERY, course_id=course_id)
        return [r.data().get("job_posting", {}) for r in result]
