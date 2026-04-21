"""synthgen.cleanup — remove all synthetic data for a given run_id.

Usage:
    cd knowledge_graph_builder
    uv run python -m synthgen.cleanup --run-id <run_id>

Or call directly:
    from synthgen.cleanup import cleanup_run
    cleanup_run(run_id, cfg)
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def cleanup_run(run_id: str, cfg) -> None:
    """Delete all synthetic data for run_id from both databases."""
    _cleanup_neo4j(run_id, cfg)
    _cleanup_postgres(run_id, cfg)
    logger.info("Cleanup complete for run_id=%s", run_id)


def _cleanup_neo4j(run_id: str, cfg) -> None:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password)
    )
    with driver.session(database=cfg.neo4j_database) as session:
        # Remove ANSWERED edges from synthetic run
        res = session.run(
            "MATCH ()-[r:ANSWERED {run_id: $rid}]->() DELETE r RETURN count(r) AS n",
            rid=run_id,
        ).single()
        logger.info("Neo4j: deleted %d ANSWERED edges", res["n"] if res else 0)

        # Remove MASTERED edges from synthetic run
        res = session.run(
            "MATCH ()-[r:MASTERED {run_id: $rid}]->() DELETE r RETURN count(r) AS n",
            rid=run_id,
        ).single()
        logger.info("Neo4j: deleted %d MASTERED edges", res["n"] if res else 0)

        # Remove ENROLLED_IN_CLASS edges for synthetic students
        res = session.run(
            """
            MATCH (u:SYNTHETIC {run_id: $rid})-[r:ENROLLED_IN_CLASS]->()
            DELETE r RETURN count(r) AS n
            """,
            rid=run_id,
        ).single()
        logger.info("Neo4j: deleted %d ENROLLED_IN_CLASS edges", res["n"] if res else 0)

        # Remove synthetic QUESTION nodes and their HAS_QUESTION edges
        res = session.run(
            """
            MATCH (q:QUESTION {run_id: $rid})
            DETACH DELETE q RETURN count(q) AS n
            """,
            rid=run_id,
        ).single()
        logger.info("Neo4j: deleted %d QUESTION nodes", res["n"] if res else 0)

        # Remove synthetic USER nodes
        res = session.run(
            """
            MATCH (u:USER:SYNTHETIC {run_id: $rid})
            DETACH DELETE u RETURN count(u) AS n
            """,
            rid=run_id,
        ).single()
        logger.info("Neo4j: deleted %d USER nodes", res["n"] if res else 0)

    driver.close()


def _cleanup_postgres(run_id: str, cfg) -> None:
    pg_url = cfg.postgres_url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
        "postgres://", "postgresql+psycopg://", 1
    )
    engine = create_engine(pg_url)
    with engine.begin() as conn:
        res = conn.execute(
            text(
                "DELETE FROM users WHERE email LIKE :pat RETURNING id"
            ),
            {"pat": f"%_{run_id}@labtutor.local"},
        )
        deleted = res.rowcount
    logger.info("Postgres: deleted %d synthetic users", deleted)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from synthgen.config import default_config

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    cfg = default_config()
    cleanup_run(args.run_id, cfg)
