"""Neo4j repository for question nodes."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from neo4j import Session as Neo4jSession

from .schemas import GeneratedQuestion

logger = logging.getLogger(__name__)

QUESTION_OPTIONS_KEY = "options"
QUESTION_CORRECT_OPTION_KEY = "correct_option"


def write_questions(
    session: Neo4jSession,
    skill_name: str,
    questions: list[GeneratedQuestion],
) -> int:
    """Replace QUESTION nodes for a skill and link via HAS_QUESTION."""
    now = datetime.now(UTC).isoformat()

    question_dicts = [
        {
            "id": str(uuid.uuid4()),
            "text": q.text,
            "difficulty": q.difficulty,
            "options": q.options,
            "correct_option": q.correct_option,
            "answer": q.answer,
            "skill_name": skill_name,
            "created_at": now,
        }
        for q in questions
    ]

    result = session.run(
        """
        MATCH (sk:SKILL {name: $skill_name})
        OPTIONAL MATCH (sk)-[:HAS_QUESTION]->(existing:QUESTION)
        WHERE NOT EXISTS { (existing)<-[:ANSWERED]-(:USER:STUDENT) }
        WITH sk, collect(existing) AS deletable_questions
        FOREACH (node IN deletable_questions | DETACH DELETE node)
        WITH sk
        UNWIND $questions AS q
        CREATE (qn:QUESTION {
            id: q.id,
            text: q.text,
            difficulty: q.difficulty,
            options: q.options,
            correct_option: q.correct_option,
            answer: q.answer,
            skill_name: q.skill_name,
            created_at: datetime(q.created_at)
        })
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
    """Check if a skill already has a complete multiple-choice question set."""
    result = session.run(
        """
        MATCH (sk:SKILL {name: $skill_name})
        OPTIONAL MATCH (sk)-[:HAS_QUESTION]->(q:QUESTION)
        WITH count(q) AS total_questions,
             count(CASE
                 WHEN size(coalesce(q[$options_key], [])) = 4
                  AND q[$correct_option_key] IN ['A', 'B', 'C', 'D']
                 THEN 1
             END) AS mcq_questions
        RETURN total_questions = 3 AND mcq_questions = 3 AS has_questions
        """,
        skill_name=skill_name,
        options_key=QUESTION_OPTIONS_KEY,
        correct_option_key=QUESTION_CORRECT_OPTION_KEY,
    )
    record = result.single()
    return bool(record and record["has_questions"])


def get_questions_for_skill(session: Neo4jSession, skill_name: str) -> list[dict]:
    """Read existing questions for a skill."""
    result = session.run(
        """
        MATCH (:SKILL {name: $skill_name})-[:HAS_QUESTION]->(q:QUESTION)
        RETURN q {
            .id,
            .text,
            .difficulty,
            .answer,
            .skill_name,
            correct_option: q[$correct_option_key],
            options: coalesce(q[$options_key], []),
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
        options_key=QUESTION_OPTIONS_KEY,
        correct_option_key=QUESTION_CORRECT_OPTION_KEY,
    )
    return [r["question"] for r in result]
