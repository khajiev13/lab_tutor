"""SQL persistence for disposable conversations and durable analysis runs."""

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from .models import MarketAnalysisRun, MarketVacancySnapshot, MDAThreadState
from .schemas import ProviderVacancy, safe_provider_payload


class RevisionConflict(ValueError):
    """The teacher or producer attempted to write an outdated revision."""


class InvalidCandidateIds(ValueError):
    """The selection contains foreign, duplicate, or overlapping candidate IDs."""


class MarketReviewRepository:
    def __init__(self, db: Session):
        self._db = db

    def create_run(
        self, course_id: int, teacher_id: int, config: dict
    ) -> MarketAnalysisRun:
        run = MarketAnalysisRun(
            course_id=course_id,
            teacher_id=teacher_id,
            approval_contract_version=1,
            config=deepcopy(config),
        )
        self._db.add(run)
        self._db.flush()
        return run

    def update_configuration(self, run: MarketAnalysisRun, config: dict) -> None:
        run.config = deepcopy(config)
        self._db.flush()

    def save_configuration_snapshot(self, thread_id: str, snapshot: dict) -> None:
        """Save the active run pointer/state in the configuration transaction."""
        self._db.execute(
            insert(MDAThreadState)
            .values(thread_id=thread_id, state_json=deepcopy(snapshot))
            .on_conflict_do_update(
                index_elements=["thread_id"],
                set_={"state_json": deepcopy(snapshot), "updated_at": func.now()},
            )
        )

    def get_run(
        self, run_id: UUID, course_id: int, teacher_id: int, *, for_update: bool = False
    ) -> MarketAnalysisRun | None:
        query = select(MarketAnalysisRun).where(
            MarketAnalysisRun.id == run_id,
            MarketAnalysisRun.course_id == course_id,
            MarketAnalysisRun.teacher_id == teacher_id,
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        return self._db.scalar(query)

    def lock_vacancy_lifecycle(self) -> None:
        """Serialize short evidence write/purge transactions until commit/rollback.

        Acquire before run row locks when combining snapshot and manifest writes.
        Provider, LLM and embedding work must stay outside this transaction.
        """
        self._db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": "marketdemandanalyst:vacancy_lifecycle"},
        )

    def upsert_vacancy_snapshot(
        self, run_id: UUID, record: ProviderVacancy
    ) -> MarketVacancySnapshot:
        from .job_sources import vacancy_content_hash, vacancy_identity

        # One lifecycle lock remains held across every snapshot in this batch.
        self.lock_vacancy_lifecycle()
        identity = vacancy_identity(record)
        run = self._db.scalar(
            select(MarketAnalysisRun)
            .where(MarketAnalysisRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise LookupError("Analysis run not found")
        if "jobs" not in run.config.get(
            "evidence_sources", ["jobs"]
        ) or record.provider not in run.config.get("sources", ["indeed", "linkedin"]):
            raise ValueError("Vacancy provider was not selected for this analysis")
        digest = vacancy_content_hash(record)
        snapshot = self._db.scalar(
            select(MarketVacancySnapshot)
            .where(
                MarketVacancySnapshot.run_id == run_id,
                MarketVacancySnapshot.provider == record.provider,
                MarketVacancySnapshot.identity == identity,
                MarketVacancySnapshot.content_hash == digest,
            )
            .execution_options(populate_existing=True)
        )
        tombstone = self._db.scalar(
            select(MarketVacancySnapshot)
            .where(
                MarketVacancySnapshot.provider == record.provider,
                MarketVacancySnapshot.identity == identity,
                MarketVacancySnapshot.purged_at.is_not(None),
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if snapshot is not None:
            snapshot.query_membership = list(
                dict.fromkeys([*snapshot.query_membership, *record.query_membership])
            )
            snapshot.source_urls = list(
                dict.fromkeys(
                    [*snapshot.source_urls, *record.source_urls, record.original_url]
                )
            )
            snapshot.last_observed_at = record.retrieved_at
            self._db.flush()
            return snapshot
        snapshot = MarketVacancySnapshot(
            run_id=run_id,
            provider=record.provider,
            native_id=record.native_id,
            identity=identity,
            content_hash=digest,
            original_url=record.original_url,
            source_urls=list(dict.fromkeys([*record.source_urls, record.original_url])),
            title=record.title,
            company=record.company,
            raw_payload={} if tombstone else safe_provider_payload(record.raw_payload),
            original_description=None if tombstone else record.original_description,
            description_text=None if tombstone else record.description_text,
            skill_tags=[] if tombstone else record.skill_tags,
            returned_dates=record.returned_dates,
            status="purged" if tombstone else record.status,
            retrieved_at=record.retrieved_at,
            last_observed_at=record.retrieved_at,
            query_membership=record.query_membership,
            demand_identity=record.demand_identity or f"{record.provider}:{identity}",
            purged_at=tombstone.purged_at if tombstone else None,
            purge_reason=tombstone.purge_reason if tombstone else None,
        )
        self._db.add(snapshot)
        run.integration_review = None
        self._db.flush()
        return snapshot

    def get_vacancy_snapshot(
        self, snapshot_id: UUID, course_id: int, teacher_id: int
    ) -> MarketVacancySnapshot | None:
        return self._db.scalar(
            select(MarketVacancySnapshot)
            .join(MarketAnalysisRun)
            .where(
                MarketVacancySnapshot.id == snapshot_id,
                MarketAnalysisRun.course_id == course_id,
                MarketAnalysisRun.teacher_id == teacher_id,
            )
            .execution_options(populate_existing=True)
        )

    def purge_vacancy_content(self, snapshot_id: UUID, *, reason: str) -> int:
        if not reason.strip():
            raise ValueError("A provider lifecycle removal reason is required")
        self.lock_vacancy_lifecycle()
        snapshot = self._db.get(
            MarketVacancySnapshot, snapshot_id, populate_existing=True
        )
        if snapshot is None:
            raise LookupError("Vacancy snapshot not found")
        copies = list(
            self._db.scalars(
                select(MarketVacancySnapshot)
                .where(
                    MarketVacancySnapshot.provider == snapshot.provider,
                    MarketVacancySnapshot.identity == snapshot.identity,
                )
                .execution_options(populate_existing=True)
            )
        )
        run_ids = sorted({item.run_id for item in copies})
        runs = list(
            self._db.scalars(
                select(MarketAnalysisRun)
                .where(MarketAnalysisRun.id.in_(run_ids))
                .order_by(MarketAnalysisRun.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        for run in runs:
            run.integration_review = None
        now = datetime.now(UTC)
        for item in copies:
            item.raw_payload = {}
            item.original_description = None
            item.description_text = None
            item.skill_tags = []
            item.status = "purged"
            item.purged_at = item.purged_at or now
            item.purge_reason = reason
        self._db.flush()
        return len(copies)

    def update_manifest(
        self,
        run_id: UUID,
        course_id: int,
        teacher_id: int,
        *,
        expected_candidate_revision: int,
        candidates: list[dict],
        categories: list[dict] | None = None,
    ) -> MarketAnalysisRun:
        run = self._locked_run(
            run_id, course_id, teacher_id, expected_candidate_revision
        )
        ids = [str(item["candidate_id"]) for item in candidates]
        if len(set(ids)) != len(ids):
            raise InvalidCandidateIds("Duplicate candidate IDs")
        for candidate_id in ids:
            UUID(candidate_id)
        run.candidate_manifest = deepcopy(
            {"candidates": candidates, "categories": categories or []}
        )
        run.candidate_revision += 1
        run.selection_confirmation = None
        run.integration_review = None
        self._db.flush()
        return run

    def save_draft(
        self,
        run_id: UUID,
        course_id: int,
        teacher_id: int,
        *,
        expected_candidate_revision: int,
        expected_selection_revision: int,
        selected_candidate_ids: list[str],
        excluded_candidate_ids: list[str],
    ) -> MarketAnalysisRun:
        run = self._locked_run(
            run_id,
            course_id,
            teacher_id,
            expected_candidate_revision,
            expected_selection_revision,
        )
        selected = [str(value) for value in selected_candidate_ids]
        excluded = [str(value) for value in excluded_candidate_ids]
        candidates = {
            str(item["candidate_id"])
            for item in run.candidate_manifest.get("candidates", [])
        }
        if (
            len(set(selected)) != len(selected)
            or len(set(excluded)) != len(excluded)
            or set(selected) & set(excluded)
            or (set(selected) | set(excluded)) - candidates
        ):
            raise InvalidCandidateIds(
                "Selection IDs must be current, unique, and disjoint"
            )
        run.selected_candidate_ids = selected
        run.excluded_candidate_ids = excluded
        run.selection_revision += 1
        run.selection_confirmation = None
        run.integration_review = None
        self._db.flush()
        return run

    def _locked_run(
        self,
        run_id: UUID,
        course_id: int,
        teacher_id: int,
        candidate_revision: int,
        selection_revision: int | None = None,
    ) -> MarketAnalysisRun:
        run = self.get_run(run_id, course_id, teacher_id, for_update=True)
        if run is None:
            raise LookupError("Analysis run not found")
        if run.candidate_revision != candidate_revision or (
            selection_revision is not None
            and run.selection_revision != selection_revision
        ):
            raise RevisionConflict("Analysis review has changed; reload before saving")
        return run


class ThreadStateRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def acquire(self, thread_id: str) -> Connection | None:
        with self._session_factory() as session:
            connection = session.get_bind().engine.connect()
        try:
            locked = connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:thread_id, 0))"),
                {"thread_id": thread_id},
            )
            # Session-level locks survive commit. Keep the actual connection open
            # without an idle transaction for the entire execution lifetime.
            connection.commit()
            if not locked:
                connection.close()
                return None
            return connection
        except BaseException:
            connection.invalidate()
            connection.close()
            raise

    def release(self, connection: Connection, thread_id: str) -> None:
        try:
            connection.rollback()
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:thread_id, 0))"),
                {"thread_id": thread_id},
            )
            connection.commit()
        except BaseException:
            # Never return a connection carrying a session advisory lock to the pool.
            connection.invalidate()
            raise
        finally:
            connection.close()

    def load(self, thread_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.get(MDAThreadState, thread_id)
            return deepcopy(row.state_json) if row else None

    def save(self, thread_id: str, state: dict[str, Any]) -> None:
        with self._session_factory() as session:
            session.execute(
                insert(MDAThreadState)
                .values(thread_id=thread_id, state_json=state)
                .on_conflict_do_update(
                    index_elements=["thread_id"],
                    set_={"state_json": state, "updated_at": func.now()},
                )
            )
            session.commit()

    def delete(self, thread_id: str) -> None:
        with self._session_factory() as session:
            session.execute(
                delete(MDAThreadState).where(MDAThreadState.thread_id == thread_id)
            )
            session.commit()


async def load_async_thread_state(session_factory, thread_id: str) -> dict | None:
    async with session_factory() as session:
        row = await session.get(MDAThreadState, thread_id)
        return deepcopy(row.state_json) if row else None
