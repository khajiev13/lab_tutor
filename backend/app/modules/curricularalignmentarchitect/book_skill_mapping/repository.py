from __future__ import annotations

import logging

from neo4j import Driver as Neo4jDriver

logger = logging.getLogger(__name__)


def load_course_chapters(driver: Neo4jDriver, course_id: int) -> list[dict]:
    """Load all COURSE_CHAPTERs for a course from Neo4j."""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(cc:COURSE_CHAPTER)
            RETURN cc {
                .title,
                .description,
                .learning_objectives,
                .chapter_index
            } AS chapter
            ORDER BY cc.chapter_index
            """,
            course_id=course_id,
        )
        return [r["chapter"] for r in result]


def load_book_chapters_with_skills(driver: Neo4jDriver, course_id: int) -> list[dict]:
    """Load BOOK_CHAPTERs with their BOOK_SKILLs grouped, for a course."""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(b:BOOK)
                  -[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(sk:BOOK_SKILL)
            RETURN
                ch.id AS chapter_id,
                ch.title AS chapter_title,
                ch.chapter_index AS chapter_index,
                collect(sk {
                    .name,
                    .description,
                    concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name]
                }) AS skills
            ORDER BY ch.chapter_index
            """,
            course_id=course_id,
        )
        return [dict(r) for r in result]


def clear_book_skill_mappings(driver: Neo4jDriver, course_id: int) -> int:
    """Delete all existing BOOK_SKILL MAPPED_TO COURSE_CHAPTER relationships for this course."""
    with driver.session() as session:
        result = session.run(
            """
            MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(b:BOOK)
                  -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(sk:BOOK_SKILL)
                  -[r:MAPPED_TO]->(cc:COURSE_CHAPTER)
            DELETE r
            RETURN count(r) AS deleted
            """,
            course_id=course_id,
        )
        record = result.single()
        return record["deleted"] if record else 0


def write_skill_mappings(
    driver: Neo4jDriver,
    course_id: int,
    mappings: list[dict],
) -> int:
    """Batch-write (BOOK_SKILL)-[:MAPPED_TO]->(COURSE_CHAPTER) relationships."""
    writable = [m for m in mappings if m.get("target_chapter")]
    if not writable:
        return 0
    with driver.session() as session:
        result = session.run(
            """
            UNWIND $mappings AS m
            MATCH (sk:BOOK_SKILL {name: m.skill_name})
            MATCH (cc:COURSE_CHAPTER {title: m.target_chapter})
            WHERE cc.course_id = $course_id
            MERGE (sk)-[r:MAPPED_TO]->(cc)
            SET r.status     = m.status,
                r.confidence = m.confidence,
                r.reasoning  = m.reasoning,
                r.mapped_at  = datetime()
            RETURN count(r) AS written
            """,
            mappings=writable,
            course_id=course_id,
        )
        record = result.single()
        return record["written"] if record else 0
