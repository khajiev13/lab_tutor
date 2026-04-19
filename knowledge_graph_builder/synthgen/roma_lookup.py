"""synthgen.roma_lookup — resolve or create the teacher in Postgres + Neo4j."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def _psycopg3_url(url: str) -> str:
    if "+psycopg" in url:
        return url
    return url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1
    )


def lookup_or_create_teacher(
    postgres_url: str,
    neo4j_session,
    username: str,
) -> dict[str, Any]:
    """Return {id, email, first_name, last_name} for the teacher.

    Tries to find an existing teacher in Postgres whose first/last name or
    email contains the username token.  If not found, creates the teacher in
    both Postgres and Neo4j so that IDs are consistent.
    """
    engine = create_engine(_psycopg3_url(postgres_url))
    token = username.lower()

    with engine.connect() as conn:
        # Postgres stores enum as uppercase text: TEACHER
        row = conn.execute(
            text(
                """
                SELECT id, email, first_name, last_name FROM users
                WHERE (
                       lower(email) LIKE :pat
                    OR lower(first_name) LIKE :pat
                    OR lower(last_name) LIKE :pat
                )
                AND role::text = 'TEACHER'
                LIMIT 1
                """
            ),
            {"pat": f"%{token}%"},
        ).fetchone()

    if row is not None:
        teacher = {
            "id": row[0],
            "email": row[1],
            "first_name": row[2],
            "last_name": row[3],
        }
        logger.info(
            "Found teacher in Postgres: id=%s name=%s %s",
            teacher["id"],
            teacher["first_name"],
            teacher["last_name"],
        )
        return teacher

    # ── Teacher not found → create Roma in both databases ─────────────────
    logger.info(
        "Teacher '%s' not found — creating in Postgres + Neo4j …", username
    )
    email = f"{token.lower()}@labtutor.local"
    first_name = username.capitalize()
    last_name = "Teacher"
    now = datetime.now(UTC)

    engine2 = create_engine(_psycopg3_url(postgres_url))
    with engine2.begin() as conn:
        # Check if email already exists (different role)
        existing = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        ).fetchone()
        if existing:
            pg_id = existing[0]
        else:
            row2 = conn.execute(
                    text(
                        """
                        INSERT INTO users
                            (email, first_name, last_name, role,
                             hashed_password, is_active, is_superuser, is_verified, created_at)
                        VALUES
                            (:email, :first_name, :last_name, 'TEACHER'::user_role,
                             'SYNTHETIC_NO_PASSWORD', true, false, false, :now)
                        RETURNING id
                        """
                    ),
                {
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "now": now,
                },
            ).fetchone()
            pg_id = row2[0]

    # Create teacher node in Neo4j
    neo4j_session.run(
        """
        MERGE (t:USER:TEACHER {id: $tid})
        SET t.email      = $email,
            t.first_name = $first_name,
            t.last_name  = $last_name
        """,
        tid=pg_id,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )

    # Link teacher to ALL existing classes
    neo4j_session.run(
        """
        MATCH (t:USER:TEACHER {id: $tid}), (c:CLASS)
        MERGE (t)-[:TEACHES_CLASS]->(c)
        """,
        tid=pg_id,
    )

    teacher = {
        "id": pg_id,
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
    }
    logger.info(
        "Created teacher: id=%s email=%s", teacher["id"], teacher["email"]
    )
    return teacher


# Keep backward-compatible alias used in __main__.py
def lookup_teacher(postgres_url: str, username: str) -> dict[str, Any]:
    """Legacy shim — call lookup_or_create_teacher from __main__ instead."""
    raise RuntimeError(
        "Call lookup_or_create_teacher(postgres_url, neo4j_session, username) instead."
    )


def lookup_teacher_classes(neo4j_session, teacher_id: int) -> list[dict]:
    """Return all CLASS nodes taught by teacher_id."""
    result = neo4j_session.run(
        """
        MATCH (t:USER {id: $tid})-[:TEACHES_CLASS]->(c:CLASS)
        RETURN c.id AS id, c.title AS title
        """,
        tid=teacher_id,
    )
    classes = [dict(r) for r in result]
    logger.info("Teacher %s teaches %d classes", teacher_id, len(classes))
    return classes


def lookup_skills_for_class(neo4j_session, class_id: int) -> list[dict]:
    """Return all SKILL / BOOK_SKILL / MARKET_SKILL nodes for a class."""
    result = neo4j_session.run(
        """
        MATCH (cl:CLASS {id: $cid})-[:CANDIDATE_BOOK]->(:BOOK)
              -[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(s)
        WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
        RETURN s.name AS name, s.id AS id,
               coalesce(ch.chapter_index, 9999) AS chapter_order
        ORDER BY chapter_order, s.name
        """,
        cid=class_id,
    )
    skills = [dict(r) for r in result]

    if not skills:
        result = neo4j_session.run(
            """
            MATCH (cl:CLASS {id: $cid})-[:HAS_COURSE_CHAPTER]->(cc:COURSE_CHAPTER)
                  <-[:MAPPED_TO]-(s)
            WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
            RETURN s.name AS name, s.id AS id,
                   coalesce(cc.chapter_index, 9999) AS chapter_order
            ORDER BY chapter_order, s.name
            """,
            cid=class_id,
        )
        skills = [dict(r) for r in result]

    logger.info("Class %s → %d skills", class_id, len(skills))
    return skills
