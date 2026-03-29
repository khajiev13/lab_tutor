"""Neo4j repository for question nodes."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from neo4j import Session as Neo4jSession

from .schemas import GeneratedQuestion

logger = logging.getLogger(__name__)


def write_questions(
    session: Neo4jSession,
    skill_name: str,
    questions: list[GeneratedQuestion],
) -> int:
    """Write QUESTION nodes and link via HAS_QUESTION. Idempotent via MERGE on id."""
    now = datetime.now(UTC).isoformat()

    question_dicts = [
        {
            "id": str(uuid.uuid4()),
            "text": q.text,
            "difficulty": q.difficulty,
            "answer": q.answer,
            "skill_name": skill_name,
            "created_at": now,
        }
        for q in questions
    ]

    result = session.run(
        """
        UNWIND $questions AS q
        MATCH (sk:SKILL {name: $skill_name})
        MERGE (qn:QUESTION {text: q.text, skill_name: q.skill_name, difficulty: q.difficulty})
        ON CREATE SET
            qn.id = q.id,
            qn.answer = q.answer,
            qn.created_at = datetime(q.created_at)
        ON MATCH SET
            qn.answer = q.answer
        MERGE (sk)-[:HAS_QUESTION]->(qn)
        RETURN count(qn) AS written
        """,
        skill_name=skill_name,
        questions=question_dicts,
    )
    record = result.single()
    count = record["written"] if record else 0
    logger.info("Wrote %d questions for skill %s", count, skill_name)
    return count


def has_questions(session: Neo4jSession, skill_name: str) -> bool:
    """Check if questions already exist for a skill."""
    result = session.run(
        "RETURN EXISTS { (:SKILL {name: $skill_name})-[:HAS_QUESTION]->(:QUESTION) } AS has_questions",
        skill_name=skill_name,
    )
    record = result.single()
    return bool(record and record["has_questions"])


def get_questions_for_skill(session: Neo4jSession, skill_name: str) -> list[dict]:
    """Read existing questions for a skill."""
    result = session.run(
        """
        MATCH (:SKILL {name: $skill_name})-[:HAS_QUESTION]->(q:QUESTION)
        RETURN q {
            .id, .text, .difficulty, .answer, .skill_name,
            created_at: toString(q.created_at)
        } AS question
        ORDER BY
            CASE q.difficulty
                WHEN 'easy' THEN 0
                WHEN 'medium' THEN 1
                WHEN 'hard' THEN 2
            END
        """,
        skill_name=skill_name,
    )
    return [r["question"] for r in result]
