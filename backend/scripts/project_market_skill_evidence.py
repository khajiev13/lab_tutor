"""Retry one committed course/run approval; never infer targets from CLI input."""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-id", type=int, required=True)
    parser.add_argument("--run-id", type=UUID)
    parser.add_argument("--revision", type=int)
    parser.add_argument(
        "--redact-only",
        action="store_true",
        help="Retry pending provider content cleanup for the course",
    )
    parser.add_argument(
        "--test-graph",
        action="store_true",
        help="Require the explicit isolated disposable graph configuration",
    )
    args = parser.parse_args(argv)
    if not args.redact_only and (args.run_id is None or args.revision is None):
        parser.error("--run-id and --revision are required for approval projection")
    driver = None
    try:
        import main as application  # noqa: F401
        from app.core.database import SessionLocal
        from app.core.neo4j import create_neo4j_driver
        from app.modules.marketdemandanalyst.neo4j_repository import (
            MarketSkillGraphRepository,
        )
        from app.modules.marketdemandanalyst.projection_service import (
            SkillEvidenceProjector,
        )
        from app.modules.marketdemandanalyst.repository import MarketReviewRepository

        database = None
        if args.test_graph:
            from neo4j import GraphDatabase

            uri = os.environ["MARKET_SKILL_TEST_NEO4J_URI"]
            if urlsplit(uri).hostname != "lab_tutor_market_projection_test":
                raise ValueError("Disposable graph configuration required")
            database = os.environ["MARKET_SKILL_TEST_NEO4J_DATABASE"]
            if database != "neo4j":
                raise ValueError("Unexpected disposable database")
            driver = GraphDatabase.driver(
                uri,
                auth=(
                    os.environ["MARKET_SKILL_TEST_NEO4J_USERNAME"],
                    os.environ["MARKET_SKILL_TEST_NEO4J_PASSWORD"],
                ),
                connection_timeout=3,
                max_transaction_retry_time=1,
            )
        else:
            driver = create_neo4j_driver()
        with SessionLocal() as db:
            graph = (
                MarketSkillGraphRepository(driver, database=database)
                if driver
                else None
            )
            projector = SkillEvidenceProjector(MarketReviewRepository(db), graph)
            status = (
                projector.redact(args.course_id)
                if args.redact_only
                else projector.project(
                    args.course_id, args.revision, run_id=args.run_id
                )
            )
        print(
            json.dumps(
                {
                    "course_id": args.course_id,
                    "run_id": str(args.run_id) if args.run_id is not None else None,
                    "approved_revision": args.revision,
                    "projection_status": status,
                }
            )
        )
        return 0 if status == "projected" else 1
    except Exception as exc:
        # Driver/SQL exceptions may include connection strings. Report type only.
        print(f"Evidence projection failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    finally:
        if driver is not None:
            driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
