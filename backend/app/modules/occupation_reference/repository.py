from collections.abc import Iterable
from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import case, exists, func, insert, or_, select, text, update
from sqlalchemy.orm import Session

from app.modules.courses.models import Course

from .importer import ParsedRelease, attribution, manifest_identity
from .models import OnetEvidence, OnetOccupation, OnetRelease
from .schemas import OccupationChoice

IMPORT_LOCK = 78239834401501535
BATCH_SIZE = 1000


class ReleaseConflictError(ValueError):
    """A release version already exists with different source content."""


class OccupationReferenceRepository:
    def __init__(self, session: Session):
        self._db = session

    def _insert_batches(self, model, rows: Iterable[dict[str, Any]]) -> None:
        batch = []
        for row in rows:
            batch.append(row)
            if len(batch) == BATCH_SIZE:
                self._db.execute(insert(model), batch)
                self._db.flush()
                batch = []
        if batch:
            self._db.execute(insert(model), batch)
            self._db.flush()

    def import_release(
        self, parsed: ParsedRelease, *, activate: bool = False
    ) -> OnetRelease:
        """Commit a complete immutable release, including activation, atomically.

        The import command owns its session. A transaction advisory lock serializes
        activation across processes, and the partial index protects other writers.
        """
        try:
            self._db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK}
            )
            row = self._db.get(OnetRelease, parsed.version)
            if row is not None:
                if manifest_identity(row.manifest) != manifest_identity(
                    parsed.manifest
                ):
                    raise ReleaseConflictError(
                        f"O*NET release {parsed.version} has different source content"
                    )
            else:
                row = OnetRelease(
                    version=parsed.version,
                    manifest=parsed.manifest,
                    attribution=attribution(parsed.version),
                    active=False,
                )
                self._db.add(row)
                self._db.flush()
                self._insert_batches(
                    OnetOccupation,
                    (
                        {"release": parsed.version, **asdict(o)}
                        for o in parsed.occupations
                    ),
                )
                self._insert_batches(
                    OnetEvidence,
                    ({**asdict(e), "id": UUID(e.id)} for e in parsed.evidence),
                )
            if activate:
                self._db.execute(
                    update(OnetRelease)
                    .where(OnetRelease.active.is_(True))
                    .values(active=False)
                )
                self._db.flush()
                row.active = True
            self._db.commit()
            return row
        except Exception:
            self._db.rollback()
            raise

    def active_release(self) -> OnetRelease | None:
        return self._db.scalar(
            select(OnetRelease).where(
                OnetRelease.active.is_(True), OnetRelease.status == "ready"
            )
        )

    def get_release(self, version: str, *, fresh: bool = False) -> OnetRelease | None:
        return self._db.scalar(
            select(OnetRelease)
            .where(OnetRelease.version == version, OnetRelease.status == "ready")
            .execution_options(populate_existing=fresh)
        )

    def list_releases(self) -> list[OnetRelease]:
        return list(
            self._db.scalars(
                select(OnetRelease)
                .where(OnetRelease.status == "ready")
                .order_by(OnetRelease.imported_at.desc(), OnetRelease.version)
            )
        )

    def count_evidence(self, version: str) -> int:
        return (
            self._db.scalar(
                select(func.count())
                .select_from(OnetEvidence)
                .where(OnetEvidence.release == version)
            )
            or 0
        )

    def owns_course(self, course_id: int, teacher_id: int) -> bool:
        return bool(
            self._db.scalar(
                select(
                    exists().where(
                        Course.id == course_id, Course.teacher_id == teacher_id
                    )
                )
            )
        )

    def search_occupations(
        self, version: str, q: str, offset: int, limit: int
    ) -> tuple[list[OnetOccupation], int]:
        escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped}%"
        aliases = func.jsonb_array_elements_text(
            OnetOccupation.alternate_titles
        ).table_valued("value")
        alias_match = exists(
            select(1)
            .select_from(aliases)
            .where(aliases.c.value.ilike(pattern, escape="\\"))
        )
        title_match = OnetOccupation.title.ilike(pattern, escape="\\")
        condition = (
            OnetOccupation.release == version,
            or_(OnetOccupation.soc_code == q, title_match, alias_match),
        )
        total = (
            self._db.scalar(
                select(func.count()).select_from(OnetOccupation).where(*condition)
            )
            or 0
        )
        rank = case(
            (OnetOccupation.soc_code == q, 0),
            (func.lower(OnetOccupation.title) == q.lower(), 1),
            (title_match, 2),
            else_=3,
        )
        rows = self._db.scalars(
            select(OnetOccupation)
            .where(*condition)
            .order_by(rank, func.lower(OnetOccupation.title), OnetOccupation.soc_code)
            .offset(offset)
            .limit(limit)
        )
        return list(rows), total

    def list_priority_occupations(self, version: str) -> list[OccupationChoice]:
        """The complete ordered catalog; priority must never search a title subset."""
        return [
            OccupationChoice.model_validate(row)
            for row in self._db.scalars(
                select(OnetOccupation)
                .where(OnetOccupation.release == version)
                .order_by(OnetOccupation.soc_code)
            )
        ]

    def get_occupations(
        self, version: str, soc_codes: list[str], *, fresh: bool = False
    ) -> list[OnetOccupation]:
        return list(
            self._db.scalars(
                select(OnetOccupation)
                .where(
                    OnetOccupation.release == version,
                    OnetOccupation.soc_code.in_(soc_codes),
                )
                .order_by(OnetOccupation.soc_code)
                .execution_options(populate_existing=fresh)
            )
        )

    def get_evidence(
        self, version: str, soc_codes: list[str], *, fresh: bool = False
    ) -> list[OnetEvidence]:
        return list(
            self._db.scalars(
                select(OnetEvidence)
                .where(
                    OnetEvidence.release == version,
                    OnetEvidence.soc_code.in_(soc_codes),
                )
                .order_by(
                    OnetEvidence.soc_code,
                    OnetEvidence.family,
                    OnetEvidence.element_id,
                    OnetEvidence.workplace_example,
                    OnetEvidence.id,
                )
                .execution_options(populate_existing=fresh)
            )
        )

    def load_occupation_evidence(
        self, version: str, soc_codes: list[str]
    ) -> list[OnetEvidence]:
        return self.get_evidence(version, soc_codes)

    def get_run(self, run_id: UUID, course_id: int, teacher_id: int):
        from app.modules.marketdemandanalyst.repository import MarketReviewRepository

        return MarketReviewRepository(self._db).get_run(
            run_id, course_id, teacher_id, for_update=True
        )

    def save_occupation_confirmation(
        self, selection, course_id: int, teacher_id: int, confirmation: dict
    ):
        from copy import deepcopy

        from app.modules.marketdemandanalyst.repository import RevisionConflict

        run = self.get_run(selection.run_id, course_id, teacher_id)
        if (
            run is None
            or run.candidate_revision != selection.expected_candidate_revision
        ):
            raise RevisionConflict("Analysis review has changed; reload before saving")
        run.config = {**deepcopy(run.config), **deepcopy(confirmation)}
        run.candidate_revision += 1
        run.selection_confirmation = None
        run.integration_review = None
        self._db.flush()
        return run

    def save_confirmation_snapshot(
        self, thread_id: str, run_id: UUID, snapshot: dict
    ) -> None:
        """Write the existing active thread in the same transaction as its run.

        The caller holds the conversation lease. Do not recreate cleared threads
        or change a newer run pointer, even if an unguarded writer changed it.
        """
        from copy import deepcopy

        from app.modules.marketdemandanalyst.models import MDAThreadState
        from app.modules.marketdemandanalyst.repository import RevisionConflict

        result = self._db.execute(
            update(MDAThreadState)
            .where(
                MDAThreadState.thread_id == thread_id,
                MDAThreadState.state_json["run_id"].astext == str(run_id),
            )
            .values(state_json=deepcopy(snapshot), updated_at=func.now())
        )
        if result.rowcount != 1:
            raise RevisionConflict(
                "Occupation selection must belong to the active analysis"
            )

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
