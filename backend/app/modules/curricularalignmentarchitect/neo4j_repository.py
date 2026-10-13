from __future__ import annotations

from neo4j import Driver

from app.core.settings import settings


def load_extracted_course_books(driver: Driver, course_id: int) -> list[dict]:
    """Return course books that already have extracted graph content in Neo4j."""
    with driver.session(database=settings.neo4j_database) as session:
        result = session.run(
            """
            MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(b:BOOK)
            CALL {
                WITH b
                MATCH (b)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)
                RETURN count(DISTINCT ch) AS chapter_count
            }
            CALL {
                WITH b
                MATCH (b)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(sk:BOOK_SKILL)
                RETURN count(DISTINCT sk) AS skill_count
            }
            WHERE chapter_count > 0 OR skill_count > 0
            RETURN
                b.id AS id,
                b.title AS title,
                b.authors AS authors,
                b.publisher AS publisher,
                b.year AS year,
                b.blob_url AS blob_url,
                chapter_count,
                skill_count
            ORDER BY b.title
            """,
            course_id=course_id,
        )
        rows = [record.data() for record in result]

    return [
        row
        for row in rows
        if row.get("title")
        and (
            int(row.get("chapter_count") or 0) > 0
            or int(row.get("skill_count") or 0) > 0
        )
    ]
