from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

from sqlalchemy import text

import main as main_module
from app.modules.auth.models import User, UserRole
from app.modules.individual_learning.models import (
    IndividualJobMatchRun,
    IndividualRunStatus,
)
from app.modules.individual_learning.repository import IndividualLearningRepository
from main import _ensure_sql_schema_upgrades


def test_schema_upgrade_preserves_duplicate_legacy_matches_and_adds_workflow_identity(
    db_session,
) -> None:
    user = User(
        email="legacy-match-upgrade@example.com",
        hashed_password="hashed",
        first_name="Indy",
        last_name="Learner",
        role=UserRole.INDIVIDUAL,
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    repository = IndividualLearningRepository(db_session)
    search_run = repository.create_job_search_run(
        user_id=user.id,
        target_titles=["Backend Engineer"],
        country="USA",
        location="New York",
    )
    user_id = user.id
    search_run_id = search_run.id
    bind = db_session.get_bind()
    with bind.begin() as connection:
        connection.execute(
            text("DROP INDEX IF EXISTS ux_individual_job_match_runs_job_search_run_id")
        )
        connection.execute(
            text("DROP INDEX IF EXISTS ix_individual_job_match_runs_job_search_run_id")
        )

    db_session.add_all(
        [
            IndividualJobMatchRun(
                user_id=user.id,
                job_search_run_id=search_run.id,
                status=IndividualRunStatus.FAILED.value,
            ),
            IndividualJobMatchRun(
                user_id=user.id,
                job_search_run_id=search_run.id,
                status=IndividualRunStatus.COMPLETED.value,
            ),
        ]
    )
    db_session.commit()
    db_session.close()
    with bind.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE individual_job_match_runs "
                "DROP COLUMN IF EXISTS workflow_thread_id"
            )
        )

    _ensure_sql_schema_upgrades()
    _ensure_sql_schema_upgrades()

    with bind.connect() as connection:
        duplicate_count = connection.scalar(
            text(
                "SELECT count(*) FROM individual_job_match_runs "
                "WHERE job_search_run_id = :job_search_run_id"
            ),
            {"job_search_run_id": search_run_id},
        )
        column_exists = connection.scalar(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'individual_job_match_runs' "
                "AND column_name = 'workflow_thread_id'"
            )
        )
        index_rows = connection.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'individual_job_match_runs'"
            )
        ).mappings()
        indexes = {row["indexname"]: row["indexdef"] for row in index_rows}

    assert duplicate_count == 2
    assert column_exists == 1
    assert "ux_individual_job_match_runs_job_search_run_id" not in indexes
    assert (
        "UNIQUE"
        not in indexes["ix_individual_job_match_runs_job_search_run_id"].upper()
    )
    workflow_index = indexes["ux_individual_job_match_runs_workflow_thread_id"].upper()
    assert "UNIQUE" in workflow_index
    assert "WORKFLOW_THREAD_ID IS NOT NULL" in workflow_index

    workflow_thread_id = f"individual-{user_id}-cv-8-extraction-13-match"
    new_match = repository.get_or_create_job_match_run(
        user_id=user_id,
        job_search_run_id=search_run_id,
        workflow_thread_id=workflow_thread_id,
    )
    retried_match = repository.get_or_create_job_match_run(
        user_id=user_id,
        job_search_run_id=search_run_id,
        workflow_thread_id=workflow_thread_id,
    )
    assert new_match.id == retried_match.id


def test_individual_schema_upgrade_serializes_concurrent_callers(
    db_session,
    monkeypatch,
) -> None:
    bind = db_session.get_bind()
    legacy_index_name = "ix_individual_job_match_runs_job_search_run_id"
    with bind.begin() as connection:
        connection.execute(text(f"DROP INDEX IF EXISTS {legacy_index_name}"))
        connection.execute(
            text(
                f"CREATE UNIQUE INDEX {legacy_index_name} "
                "ON individual_job_match_runs (job_search_run_id)"
            )
        )

    connection_start_barrier = Barrier(2)
    observation_lock = Lock()
    observations = {"advisory_calls": 0, "unsafe_drop": False}
    real_engine = main_module.engine

    class CoordinatedConnection:
        def __init__(self, connection) -> None:
            self._connection = connection

        def __enter__(self):
            self._connection.__enter__()
            connection_start_barrier.wait(timeout=10)
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self._connection.__exit__(exc_type, exc_value, traceback)

        def execute(self, statement, *args, **kwargs):
            sql = str(statement)
            if "pg_advisory_xact_lock" in sql:
                with observation_lock:
                    observations["advisory_calls"] += 1
            if f"DROP INDEX {legacy_index_name}" in sql and "IF EXISTS" not in sql:
                with observation_lock:
                    observations["unsafe_drop"] = True

            return self._connection.execute(statement, *args, **kwargs)

        def __getattr__(self, name: str):
            return getattr(self._connection, name)

    class CoordinatedEngine:
        url = real_engine.url

        @staticmethod
        def connect():
            return CoordinatedConnection(real_engine.connect())

    monkeypatch.setattr(main_module, "engine", CoordinatedEngine())

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_ensure_sql_schema_upgrades) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]

    assert results == [None, None]
    assert observations == {"advisory_calls": 2, "unsafe_drop": False}

    with bind.connect() as connection:
        index_rows = connection.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'individual_job_match_runs'"
            )
        ).mappings()
        indexes = {row["indexname"]: row["indexdef"] for row in index_rows}

    assert "UNIQUE" not in indexes[legacy_index_name].upper()
    workflow_index = indexes["ux_individual_job_match_runs_workflow_thread_id"].upper()
    assert "UNIQUE" in workflow_index
    assert "WORKFLOW_THREAD_ID IS NOT NULL" in workflow_index
