from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.marketdemandanalyst.repository import RevisionConflict
from app.modules.marketdemandanalyst.schemas import SkillReview

from .importer import release_url
from .models import OnetRelease
from .repository import OccupationReferenceRepository
from .schemas import (
    OccupationChoice,
    OccupationSearch,
    OccupationSelection,
    OccupationSkills,
    OnetEvidence,
    ReleaseInfo,
    ReleaseList,
)


class OccupationReferenceService:
    def __init__(self, repository: OccupationReferenceRepository):
        self._repo = repository

    def require_teacher(self, course_id: int, teacher_id: int) -> None:
        if not self._repo.owns_course(course_id, teacher_id):
            raise HTTPException(404, "Course not found")

    def _ready_release(self, release: str | None) -> OnetRelease:
        ready = (
            self._repo.get_release(release) if release else self._repo.active_release()
        )
        if ready is None:
            raise HTTPException(503, "O*NET catalog is unavailable for this release")
        return ready

    def list_releases(self, course_id: int, teacher_id: int) -> ReleaseList:
        self.require_teacher(course_id, teacher_id)
        return ReleaseList(
            items=[
                ReleaseInfo.model_validate(row) for row in self._repo.list_releases()
            ]
        )

    def pin_release(self, course_id: int, teacher_id: int, release: str | None) -> str:
        self.require_teacher(course_id, teacher_id)
        return self._ready_release(release).version

    def search_occupations(
        self,
        course_id: int,
        teacher_id: int,
        release: str | None,
        q: str,
        offset: int = 0,
        limit: int = 20,
    ) -> OccupationSearch:
        self.require_teacher(course_id, teacher_id)
        q = q.strip()
        if not 2 <= len(q) <= 120 or offset < 0 or not 1 <= limit <= 50:
            raise HTTPException(422, "Invalid occupation search bounds")
        ready = self._ready_release(release)
        items, total = self._repo.search_occupations(ready.version, q, offset, limit)
        return OccupationSearch(
            release=ready.version,
            total=total,
            items=[OccupationChoice.model_validate(row) for row in items],
        )

    def get_occupation_choices(
        self, course_id: int, teacher_id: int, release: str, soc_codes: list[str]
    ) -> list[OccupationChoice]:
        self.require_teacher(course_id, teacher_id)
        if not 1 <= len(soc_codes) <= 5 or len(set(soc_codes)) != len(soc_codes):
            raise HTTPException(422, "Choose one to five distinct occupations")
        ready = self._ready_release(release)
        rows = {
            row.soc_code: row
            for row in self._repo.get_occupations(ready.version, soc_codes)
        }
        if set(rows) != set(soc_codes):
            raise HTTPException(422, "Occupation not found in this release")
        return [OccupationChoice.model_validate(rows[code]) for code in soc_codes]

    def get_skill_evidence(
        self, course_id: int, teacher_id: int, release: str | None, soc_codes: list[str]
    ) -> list[OnetEvidence]:
        self.require_teacher(course_id, teacher_id)
        ready = self._ready_release(release)
        occupations = self.get_occupation_choices(
            course_id, teacher_id, ready.version, soc_codes
        )
        titles = {row.soc_code: row.title for row in occupations}
        return [
            OnetEvidence(
                id=row.id,
                release=row.release,
                soc_code=row.soc_code,
                occupation_title=titles[row.soc_code],
                family=row.family,
                element_id=row.element_id,
                label=row.label,
                definition=row.definition,
                workplace_example=row.workplace_example,
                ratings=row.ratings,
                flags=row.flags,
                source_url=release_url(row.release, f"{row.family}_skills.csv"),
                attribution=ready.attribution,
            )
            for row in self._repo.load_occupation_evidence(ready.version, soc_codes)
        ]

    def get_occupation_skills(
        self, course_id: int, teacher_id: int, release: str | None, soc_code: str
    ) -> OccupationSkills:
        self.require_teacher(course_id, teacher_id)
        ready = self._ready_release(release)
        return OccupationSkills(
            release=ready.version,
            soc_code=soc_code,
            items=self.get_skill_evidence(
                course_id, teacher_id, ready.version, [soc_code]
            ),
        )

    def confirm_occupations(
        self, course_id: int, teacher_id: int, selection: OccupationSelection
    ) -> tuple[SkillReview, dict]:
        self.require_teacher(course_id, teacher_id)
        run = self._repo.get_run(selection.run_id, course_id, teacher_id)
        if run is None:
            raise HTTPException(404, "Analysis run not found")
        if run.candidate_revision != selection.expected_candidate_revision:
            raise HTTPException(
                409, "Analysis review has changed; reload before saving"
            )
        if "onet" not in run.config.get("evidence_sources", ["jobs"]):
            raise HTTPException(422, "O*NET was not selected for this analysis")
        if run.config.get("onet_release") != selection.release:
            raise HTTPException(
                422, "Occupation release must match the pinned analysis release"
            )
        if (
            run.lifecycle != "draft"
            or run.candidate_manifest.get("candidates")
            or any(
                outcome.get("received_count", 0) > 0
                or outcome.get("status") in {"loading", "success", "partial", "empty"}
                for outcome in run.source_outcomes.values()
            )
        ):
            raise HTTPException(
                409, "Occupation changes require a new analysis after collection starts"
            )
        occupations = self.get_occupation_choices(
            course_id, teacher_id, selection.release, selection.soc_codes
        )
        confirmation = {
            "onet_release": selection.release,
            "selected_onet_occupations": [item.model_dump() for item in occupations],
            "onet_selection_confirmed": True,
        }
        try:
            run = self._repo.save_occupation_confirmation(
                selection, course_id, teacher_id, confirmation
            )
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        manifest = run.candidate_manifest
        return SkillReview(
            run_id=run.id,
            candidate_revision=run.candidate_revision,
            selection_revision=run.selection_revision,
            categories=manifest.get("categories", []),
            candidates=manifest.get("candidates", []),
            selected_candidate_ids=run.selected_candidate_ids,
            excluded_candidate_ids=run.excluded_candidate_ids,
            recommendations=run.recommendations,
            source_outcomes=run.source_outcomes,
            extraction_coverage=run.extraction_coverage,
            integration_review=run.integration_review,
            publication_revision=run.publication_revision,
            approved_references=run.approved_references,
        ), confirmation

    def save_confirmation_snapshot(
        self, thread_id: str, run_id: UUID, snapshot: dict
    ) -> None:
        try:
            self._repo.save_confirmation_snapshot(thread_id, run_id, snapshot)
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    def commit(self) -> None:
        self._repo.commit()

    def rollback(self) -> None:
        self._repo.rollback()


def get_occupation_reference_service(
    db: Session = Depends(get_db),
) -> OccupationReferenceService:
    return OccupationReferenceService(OccupationReferenceRepository(db))
