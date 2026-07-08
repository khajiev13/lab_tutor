from __future__ import annotations

from sqlalchemy.orm import Session

from .models import IndividualProfile


class IndividualLearningRepository:
    def __init__(self, db: Session | None) -> None:
        self._db = db

    def get_profile(self, user_id: int) -> IndividualProfile | None:
        if self._db is None:
            return None
        return (
            self._db.query(IndividualProfile)
            .filter(IndividualProfile.user_id == user_id)
            .one_or_none()
        )
