from __future__ import annotations

from datetime import datetime
from typing import LiteralString

UPSERT_USER: LiteralString = """
MERGE (u:USER {id: $id})
SET
    u.first_name = $first_name,
    u.last_name = $last_name,
    u.email = $email,
    u.created_at = $created_at
WITH u
REMOVE u.role
REMOVE u:STUDENT:TEACHER
FOREACH (_ IN CASE WHEN $role = 'student' THEN [1] ELSE [] END | SET u:STUDENT)
FOREACH (_ IN CASE WHEN $role = 'teacher' THEN [1] ELSE [] END | SET u:TEACHER)
RETURN u
"""


class UserGraphRepository:
    def __init__(self, session):
        self._session = session

    def upsert_user(
        self,
        *,
        user_id: int,
        role: str,
        first_name: str | None,
        last_name: str | None,
        email: str,
        created_at: datetime | None,
    ) -> None:
        params = {
            "id": user_id,
            "role": role,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "created_at": created_at.isoformat() if created_at else None,
        }

        def _tx(tx):
            tx.run(UPSERT_USER, params).consume()

        self._session.execute_write(_tx)
