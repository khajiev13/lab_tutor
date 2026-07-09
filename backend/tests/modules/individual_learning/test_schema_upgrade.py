from __future__ import annotations

from sqlalchemy import text

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
