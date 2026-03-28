"""One-time backfill: copy chapter titles from PostgreSQL → Neo4j.

Usage:
    cd backend && uv run python -m scripts.backfill_chapter_titles
"""

from __future__ import annotations

import logging

from app.core.database import SessionLocal
from app.core.neo4j import create_neo4j_driver
from app.core.settings import settings
from app.modules.curricularalignmentarchitect.models import BookChapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    db = SessionLocal()
    driver = create_neo4j_driver()
    if driver is None:
        logger.error("Neo4j not configured — aborting")
        return

    try:
        chapters = db.query(BookChapter).all()
        logger.info("Found %d BookChapter rows in PostgreSQL", len(chapters))

        # Build mapping: neo4j_id → title
        updates: list[dict] = []
        for ch in chapters:
            neo4j_id = f"book_{ch.selected_book_id}_ch_{ch.chapter_index}"
            updates.append(
                {
                    "id": neo4j_id,
                    "title": ch.chapter_title,
                    "chapter_index": ch.chapter_index,
                }
            )

        if not updates:
            logger.info("No chapters to update")
            return

        with driver.session(database=settings.neo4j_database) as session:
            result = session.run(
                """
                UNWIND $updates AS u
                MATCH (ch:BOOK_CHAPTER {id: u.id})
                SET ch.title = u.title,
                    ch.chapter_index = u.chapter_index
                RETURN count(*) AS updated
                """,
                updates=updates,
            )
            record = result.single()
            logger.info("Updated %d BOOK_CHAPTER nodes in Neo4j", record["updated"])

    finally:
        db.close()
        driver.close()


if __name__ == "__main__":
    main()
