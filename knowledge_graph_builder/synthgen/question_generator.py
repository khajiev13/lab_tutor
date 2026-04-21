"""synthgen.question_generator — IRT 2PL question bank builder.

Creates QUESTION nodes with difficulty (b) and discrimination (a) drawn from
realistic distributions, and writes them to Neo4j as synthetic nodes.
"""
from __future__ import annotations

import logging

import numpy as np
from scipy.special import expit as sigmoid  # type: ignore

from .config import SynthGenConfig

logger = logging.getLogger(__name__)


def build_question_bank(
    skills: list[dict],
    cfg: SynthGenConfig,
) -> list[dict]:
    """Generate a synthetic question bank (IRT 2PL parameters).

    Returns list of question dicts:
        question_id    : str
        skill_ids      : list[str]  (skill names, since IDs = names here)
        difficulty     : float  b  ~ N(0, 1.2) ∈ [-3, 3]
        discrimination : float  a  ~ LogNormal(0, 0.5) ∈ [0.5, 3.0]
        text           : str    placeholder text
        synthetic      : True
    """
    rng = np.random.default_rng(cfg.random_seed + 1)

    questions = []
    for skill in skills:
        sid = skill["name"]   # we use skill name as ID for compatibility
        n = cfg.questions_per_skill

        # b ~ N(0, 1.2) clipped to [-3, 3]
        difficulties = np.clip(rng.normal(0.0, 1.2, size=n), -3.0, 3.0)
        # a ~ LogNormal(0, 0.5) clipped to [0.5, 3.0]
        discriminations = np.clip(
            rng.lognormal(0.0, 0.5, size=n), 0.5, 3.0
        )

        for j in range(n):
            qid = f"synq_{sid[:20]}_{j:02d}_{cfg.run_id}"
            questions.append(
                {
                    "question_id": qid,
                    "skill_ids": [sid],
                    "difficulty": round(float(difficulties[j]), 4),
                    "discrimination": round(float(discriminations[j]), 4),
                    "text": f"[SYNTHETIC] Question {j+1} for skill: {sid}",
                    "synthetic": True,
                    "run_id": cfg.run_id,
                }
            )

    logger.info(
        "Built question bank: %d questions for %d skills",
        len(questions),
        len(skills),
    )
    return questions


def write_questions_to_neo4j(
    questions: list[dict],
    neo4j_session,
    cfg: SynthGenConfig,
) -> None:
    """Write QUESTION nodes and HAS_QUESTION edges to Neo4j in batches.

    Each question is tagged with :SYNTHETIC label and {synthetic:true}.
    """
    batch_size = cfg.batch_size

    def _write_batch(tx, batch):
        tx.run(
            """
            UNWIND $rows AS q
            MERGE (n:QUESTION:SYNTHETIC_RUN {id: q.question_id})
            SET n:QUESTION,
                n:SYNTHETIC,
                n.text           = q.text,
                n.difficulty     = q.difficulty,
                n.discrimination = q.discrimination,
                n.synthetic      = true,
                n.run_id         = q.run_id
            WITH n, q
            UNWIND q.skill_ids AS sname
            MATCH (s {name: sname})
            WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
            MERGE (s)-[:HAS_QUESTION]->(n)
            """,
            rows=batch,
        )

    total = len(questions)
    for start in range(0, total, batch_size):
        batch = questions[start : start + batch_size]
        neo4j_session.execute_write(_write_batch, batch)
        logger.info(
            "Wrote questions %d/%d", min(start + batch_size, total), total
        )

    logger.info("All %d questions written to Neo4j", total)
