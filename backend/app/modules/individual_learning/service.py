from __future__ import annotations

from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from .repository import IndividualLearningRepository
from .schemas import IndividualProfileRead


class IndividualLearningService:
    def __init__(self, db: Session | None, neo4j_driver: Neo4jDriver | None) -> None:
        self._repo = IndividualLearningRepository(db)
        self._neo4j_driver = neo4j_driver

    def get_profile(self, user_id: int) -> IndividualProfileRead:
        profile = self._repo.get_profile(user_id)
        if profile is None:
            return IndividualProfileRead(user_id=user_id, onboarding_status="needs_cv")

        return IndividualProfileRead(
            user_id=user_id,
            onboarding_status=profile.onboarding_status,
            target_titles=list(profile.target_titles_json or []),
            preferred_country=profile.preferred_country,
            preferred_location=profile.preferred_location,
            reviewed_at=profile.reviewed_at,
        )
