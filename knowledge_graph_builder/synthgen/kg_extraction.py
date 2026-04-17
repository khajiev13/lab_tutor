"""synthgen.kg_extraction — pull concept/skill graph from Neo4j."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def fetch_skills(neo4j_session) -> list[dict]:
    """Fetch all SKILL/BOOK_SKILL/MARKET_SKILL nodes with prerequisites."""
    result = neo4j_session.run(
        """
        MATCH (s)
        WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
        OPTIONAL MATCH (s)-[:REQUIRES_CONCEPT]->(c:CONCEPT)
        WITH s, collect(c.name) AS concept_names
        RETURN s.name AS name,
               coalesce(s.id, s.name) AS id,
               concept_names
        ORDER BY s.name
        """
    )
    skills = [dict(r) for r in result]
    logger.info("Fetched %d skills", len(skills))
    return skills


def fetch_prerequisite_edges(neo4j_session) -> list[dict]:
    """Fetch PREREQUISITE edges between skills."""
    result = neo4j_session.run(
        """
        MATCH (a)-[r:PREREQUISITE]->(b)
        WHERE (a:SKILL OR a:BOOK_SKILL OR a:MARKET_SKILL)
          AND (b:SKILL OR b:BOOK_SKILL OR b:MARKET_SKILL)
        RETURN a.name AS from_skill, b.name AS to_skill,
               CASE r.confidence
                   WHEN 'high'   THEN 1.0
                   WHEN 'medium' THEN 0.6
                   WHEN 'low'    THEN 0.3
                   ELSE               0.6
               END AS strength
        """
    )
    edges = [dict(r) for r in result]
    logger.info("Fetched %d prerequisite edges", len(edges))
    return edges


def fetch_skill_video_edges(neo4j_session) -> list[dict]:
    """Fetch HAS_VIDEO edges between skills and VIDEO_RESOURCE nodes.

    Returns a list of dicts with keys:
      skill_name  – name of the skill node
      video_id    – id of the VIDEO_RESOURCE node
      video_title – title of the video (for debugging / vocab)
    """
    result = neo4j_session.run(
        """
        MATCH (s)-[:HAS_VIDEO]->(v:VIDEO_RESOURCE)
        WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
        RETURN s.name AS skill_name,
               coalesce(v.id, v.url) AS video_id,
               v.title AS video_title
        """
    )
    edges = [dict(r) for r in result]
    logger.info("Fetched %d skill-video edges", len(edges))
    return edges


def fetch_skill_reading_edges(neo4j_session) -> list[dict]:
    """Fetch HAS_READING edges between skills and READING_RESOURCE nodes.

    Returns a list of dicts with keys:
      skill_name    – name of the skill node
      reading_id    – id of the READING_RESOURCE node
      reading_title – title of the reading (for debugging / vocab)
    """
    result = neo4j_session.run(
        """
        MATCH (s)-[:HAS_READING]->(r:READING_RESOURCE)
        WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
        RETURN s.name AS skill_name,
               coalesce(r.id, r.url) AS reading_id,
               r.title AS reading_title
        """
    )
    edges = [dict(r) for r in result]
    logger.info("Fetched %d skill-reading edges", len(edges))
    return edges


def fetch_existing_questions(neo4j_session) -> list[dict]:
    """Fetch any QUESTION nodes already in the graph.

    Maps categorical difficulty/discrimination to numeric IRT values so the
    interaction simulator can use them directly in the 2PL formula.
    """
    result = neo4j_session.run(
        """
        MATCH (q:QUESTION)
        OPTIONAL MATCH (s)-[:HAS_QUESTION]->(q)
        WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
        WITH q,
             CASE
               WHEN q.difficulty = 'easy'   THEN -1.0
               WHEN q.difficulty = 'medium' THEN  0.0
               WHEN q.difficulty = 'hard'   THEN  1.0
               WHEN q.difficulty IS NULL    THEN  0.0
               ELSE toFloat(q.difficulty)
             END AS difficulty_num,
             CASE
               WHEN q.discrimination = 'high'   THEN 1.5
               WHEN q.discrimination = 'medium' THEN 1.0
               WHEN q.discrimination = 'low'    THEN 0.5
               WHEN q.discrimination IS NULL    THEN 1.0
               ELSE toFloat(q.discrimination)
             END AS discrimination_num,
             collect(s.name) AS skill_names
        RETURN q.id AS id,
               difficulty_num     AS difficulty,
               discrimination_num AS discrimination,
               skill_names
        """
    )
    questions = [dict(r) for r in result]
    logger.info("Found %d existing questions in graph", len(questions))
    return questions
