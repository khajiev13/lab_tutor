"""Cognitive Diagnosis — Neo4j repository.

All graph writes for ARCD-derived data:
  (USER:STUDENT) -[:MASTERED]->       (SKILL)
  (USER:STUDENT) -[:ANSWERED]->       (QUESTION)
  (USER:STUDENT) -[:OPENED_READING]-> (READING_RESOURCE)
  (USER:STUDENT) -[:OPENED_VIDEO]->   (VIDEO_RESOURCE)

Reads:
  - Student mastery snapshots
  - Skill prerequisite matrix
  - Skill names and concept counts
"""

from __future__ import annotations

import time
import uuid
from typing import LiteralString

from neo4j import Session as Neo4jSession

# ── Write: MASTERED ──────────────────────────────────────────────────────

UPSERT_MASTERED: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})
MATCH (s {name: $skill_name})
WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
MERGE (u)-[r:MASTERED]->(s)
SET r.mastery          = $mastery,
    r.decay            = $decay,
    r.status           = $status,
    r.attempt_count    = $attempt_count,
    r.correct_count    = $correct_count,
    r.updated_at_ts    = $updated_at_ts,
    r.model_version    = $model_version,
    r.last_practice_ts = $last_practice_ts
"""

UPSERT_MASTERY_BATCH: LiteralString = """
UNWIND $rows AS row
MATCH (u:USER:STUDENT {id: row.user_id})
MATCH (s {name: row.skill_name})
WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
MERGE (u)-[r:MASTERED]->(s)
SET r.mastery          = row.mastery,
    r.decay            = row.decay,
    r.status           = row.status,
    r.attempt_count    = row.attempt_count,
    r.correct_count    = row.correct_count,
    r.updated_at_ts    = row.updated_at_ts,
    r.model_version    = row.model_version,
    r.last_practice_ts = row.last_practice_ts
"""


# ── Write: ANSWERED ───────────────────────────────────────────────────────

CREATE_ANSWERED: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})
MATCH (q:QUESTION {id: $question_id})
CREATE (u)-[r:ANSWERED]->(q)
SET r.answered_right   = $answered_right,
    r.answered_at      = datetime($answered_at),
    r.selected_option  = $selected_option
"""


# ── Write: OPENED_READING / OPENED_VIDEO ─────────────────────────────────

UPSERT_OPENED_READING: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})
MATCH (res:READING_RESOURCE {id: $resource_id})
MERGE (u)-[e:OPENED_READING]->(res)
ON CREATE SET e.first_opened_at = datetime($opened_at),
              e.last_opened_at  = datetime($opened_at),
              e.open_count      = 1,
              e.opened_at       = [$opened_at]
ON MATCH  SET e.last_opened_at  = datetime($opened_at),
              e.open_count      = e.open_count + 1,
              e.opened_at       = e.opened_at + [$opened_at]
"""

UPSERT_OPENED_VIDEO: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})
MATCH (v:VIDEO_RESOURCE {id: $resource_id})
MERGE (u)-[e:OPENED_VIDEO]->(v)
ON CREATE SET e.first_opened_at = datetime($opened_at),
              e.last_opened_at  = datetime($opened_at),
              e.open_count      = 1,
              e.opened_at       = [$opened_at]
ON MATCH  SET e.last_opened_at  = datetime($opened_at),
              e.open_count      = e.open_count + 1,
              e.opened_at       = e.opened_at + [$opened_at]
"""


# ── Read: mastery snapshot ─────────────────────────────────────────────────

GET_STUDENT_MASTERY: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[r:MASTERED]->(s)
WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
RETURN s.name AS skill_name,
       r.mastery          AS mastery,
       r.decay            AS decay,
       r.status           AS status,
       r.attempt_count    AS attempt_count,
       r.correct_count    AS correct_count,
       r.last_practice_ts AS last_practice_ts,
       r.model_version    AS model_version
ORDER BY s.name
"""

GET_STUDENT_MASTERY_FOR_COURSE: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[r:MASTERED]->(s)
WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
  AND (
    EXISTS {
      MATCH (:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)
            -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(s)
    }
    OR EXISTS {
      MATCH (:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
            <-[:MAPPED_TO]-(s)
    }
  )
RETURN s.name AS skill_name,
       r.mastery          AS mastery,
       r.decay            AS decay,
       r.status           AS status,
       r.attempt_count    AS attempt_count,
       r.correct_count    AS correct_count,
       r.last_practice_ts AS last_practice_ts,
       r.model_version    AS model_version
ORDER BY s.name
"""


# ── Read: KG structure for PathGen/RevFell ─────────────────────────────────

GET_ALL_SKILLS_WITH_CONCEPTS: LiteralString = """
MATCH (s)
WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
WITH s,
     head(COLLECT { MATCH (s)<-[:HAS_SKILL]-(bch:BOOK_CHAPTER) RETURN bch ORDER BY bch.chapter_index ASC }) AS ch,
     [(s)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name] AS concept_names
WITH s, ch, concept_names,
     CASE
         WHEN ch IS NOT NULL AND ch.title IS NOT NULL AND trim(ch.title) <> ''
             THEN trim(ch.title)
         WHEN ch IS NOT NULL AND ch.chapter_index IS NOT NULL
             THEN 'Chapter ' + toString(ch.chapter_index)
         ELSE null
     END AS chapter_name,
     coalesce(ch.chapter_index, 9999) AS chapter_order
RETURN s.name AS skill_name,
       concept_names,
       coalesce(chapter_name, 'Untitled Chapter') AS chapter_name,
       chapter_order
ORDER BY chapter_order, chapter_name, s.name
"""

GET_SKILLS_FOR_COURSE: LiteralString = """
MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)
      -[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(s)
WITH s, ch
ORDER BY ch.chapter_index, s.name
WITH s,
     head(collect(
         coalesce(
             ch.title,
             CASE WHEN ch.chapter_index IS NOT NULL
                  THEN 'Chapter ' + toString(ch.chapter_index)
                  ELSE 'Untitled Chapter' END
         )
     )) AS chapter_name,
     head(collect(ch.chapter_index)) AS chapter_idx
WITH s, chapter_name, chapter_idx,
     [(s)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name] AS concept_names
RETURN s.name AS skill_name,
       concept_names,
       coalesce(chapter_name, '') AS chapter_name,
       coalesce(chapter_idx, 9999) AS chapter_order
ORDER BY chapter_order, skill_name
"""

GET_STUDENT_SELECTED_SKILLS: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[:SELECTED_SKILL]->(s)
WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
WITH s,
     head(COLLECT { MATCH (s)<-[:HAS_SKILL]-(bch:BOOK_CHAPTER) RETURN bch ORDER BY bch.chapter_index ASC }) AS ch,
     [(s)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name] AS concept_names
WITH s, ch, concept_names,
     CASE
         WHEN ch IS NOT NULL AND ch.title IS NOT NULL AND trim(ch.title) <> ''
             THEN trim(ch.title)
         WHEN ch IS NOT NULL AND ch.chapter_index IS NOT NULL
             THEN 'Chapter ' + toString(ch.chapter_index)
         ELSE null
     END AS chapter_name,
     coalesce(ch.chapter_index, 9999) AS chapter_order
RETURN s.name AS skill_name,
       concept_names,
       coalesce(chapter_name, 'Untitled Chapter') AS chapter_name,
       chapter_order
ORDER BY chapter_order, chapter_name, skill_name
"""

GET_STUDENT_SELECTED_SKILLS_FOR_COURSE: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[:SELECTED_SKILL]->(s)
WHERE (s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL)
  AND (
    EXISTS {
      MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)
            -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(s)
    }
    OR EXISTS {
      MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
            <-[:MAPPED_TO]-(s)
    }
  )
WITH s,
     head(COLLECT { MATCH (:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(bch:BOOK_CHAPTER)-[:HAS_SKILL]->(s) RETURN bch ORDER BY bch.chapter_index ASC }) AS bch,
     head(COLLECT { MATCH (:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(cch:COURSE_CHAPTER)<-[:MAPPED_TO]-(s) RETURN cch ORDER BY cch.chapter_index ASC }) AS cch,
     [(s)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name] AS concept_names
WITH s, bch, cch, concept_names,
     CASE
         WHEN bch IS NOT NULL AND bch.title IS NOT NULL AND trim(bch.title) <> ''
             THEN trim(bch.title)
         WHEN bch IS NOT NULL AND bch.chapter_index IS NOT NULL
             THEN 'Chapter ' + toString(bch.chapter_index)
         WHEN cch IS NOT NULL AND cch.title IS NOT NULL AND trim(cch.title) <> ''
             THEN trim(cch.title)
         WHEN cch IS NOT NULL AND cch.chapter_index IS NOT NULL
             THEN 'Chapter ' + toString(cch.chapter_index)
         ELSE null
     END AS chapter_name,
     coalesce(bch.chapter_index, cch.chapter_index, 9999) AS chapter_order
RETURN s.name AS skill_name,
       concept_names,
       coalesce(chapter_name, 'Untitled Chapter') AS chapter_name,
       chapter_order
ORDER BY chapter_order, chapter_name, skill_name
"""

GET_PREREQUISITE_MATRIX: LiteralString = """
MATCH (a)-[r:PREREQUISITE]->(b)
WHERE (a:SKILL OR a:BOOK_SKILL OR a:MARKET_SKILL)
  AND (b:SKILL OR b:BOOK_SKILL OR b:MARKET_SKILL)
RETURN a.name AS from_skill, b.name AS to_skill,
       CASE r.confidence
           WHEN 'high'   THEN 1.0
           WHEN 'medium' THEN 0.6
           WHEN 'low'    THEN 0.3
           ELSE               0.6
       END AS strength
"""

GET_STUDENT_INTERACTION_TIMELINE: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[a:ANSWERED]->(q:QUESTION)
MATCH (s)-[:HAS_QUESTION]->(q)
WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
RETURN s.name AS skill_name, a.answered_right AS response, a.answered_at.epochSeconds AS ts
ORDER BY a.answered_at
"""

GET_STUDENT_INTERACTION_TIMELINE_FOR_COURSE: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[a:ANSWERED]->(q:QUESTION)
MATCH (s)-[:HAS_QUESTION]->(q)
WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
  AND (
    EXISTS {
      MATCH (:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)
            -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(s)
    }
    OR EXISTS {
      MATCH (:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
            <-[:MAPPED_TO]-(s)
    }
  )
RETURN s.name AS skill_name, a.answered_right AS response, a.answered_at.epochSeconds AS ts
ORDER BY a.answered_at
"""

GET_QUESTIONS_FOR_SKILL: LiteralString = """
MATCH (s {name: $skill_name})-[:HAS_QUESTION]->(q:QUESTION)
WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
RETURN q.id AS question_id, q.text AS text, q.difficulty AS difficulty,
       q.options AS options, q.correct_option AS correct_option, q.answer AS answer
LIMIT $limit
"""

CREATE_STUDENT_EVENT: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})
CREATE (e:STUDENT_EVENT {
  id: $event_id,
  date: $date,
  title: $title,
  event_type: $event_type,
  duration_minutes: $duration_minutes,
  notes: $notes,
  created_at_ts: $created_at_ts
})
MERGE (u)-[:HAS_EVENT]->(e)
RETURN e.id AS id,
       u.id AS user_id,
       e.date AS date,
       e.title AS title,
       e.event_type AS event_type,
       e.duration_minutes AS duration_minutes,
       e.notes AS notes,
       toString(e.created_at_ts) AS created_at
"""

GET_STUDENT_EVENTS: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[:HAS_EVENT]->(e:STUDENT_EVENT)
WHERE ($from_date IS NULL OR e.date >= $from_date)
  AND ($to_date IS NULL OR e.date <= $to_date)
RETURN e.id AS id,
       u.id AS user_id,
       e.date AS date,
       e.title AS title,
       e.event_type AS event_type,
       e.duration_minutes AS duration_minutes,
       coalesce(e.notes, '') AS notes,
       toString(e.created_at_ts) AS created_at
ORDER BY e.date ASC, e.created_at_ts ASC
"""

DELETE_STUDENT_EVENT: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[:HAS_EVENT]->(e:STUDENT_EVENT {id: $event_id})
DETACH DELETE e
RETURN count(*) AS deleted_count
"""


# ── Repository class ───────────────────────────────────────────────────────


class CognitiveDiagnosisRepository:
    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    # ── Writes ──────────────────────────────────────────────────

    def upsert_mastery_batch(
        self,
        user_id: int,
        mastery_items: list[dict],
        model_version: str = "arcd_v2",
    ) -> None:
        """Write/update MASTERED edges for all skills at once."""
        now_ts = int(time.time())
        rows = [
            {
                "user_id": user_id,
                "skill_name": item["skill_name"],
                "mastery": float(item.get("mastery", 0.0)),
                "decay": float(item.get("decay", 1.0)),
                "status": item.get("status", "not_started"),
                "attempt_count": int(item.get("attempt_count", 0)),
                "correct_count": int(item.get("correct_count", 0)),
                "updated_at_ts": now_ts,
                "model_version": model_version,
                "last_practice_ts": item.get("last_practice_ts"),
            }
            for item in mastery_items
        ]
        self._session.run(UPSERT_MASTERY_BATCH, rows=rows).consume()

    def create_answered(
        self,
        user_id: int,
        question_id: str,
        answered_right: bool,
        answered_at: str | None = None,
        selected_option: str | None = None,
    ) -> None:
        """Create an ANSWERED relationship."""
        from datetime import datetime, timezone

        at_iso = answered_at or datetime.now(timezone.utc).isoformat()
        self._session.run(
            CREATE_ANSWERED,
            user_id=user_id,
            question_id=question_id,
            answered_right=answered_right,
            answered_at=at_iso,
            selected_option=selected_option,
        ).consume()

    def upsert_opened_resource(
        self,
        user_id: int,
        resource_id: str,
        resource_type: str,
        opened_at: str | None = None,
    ) -> None:
        """Create/update OPENED_READING or OPENED_VIDEO relationship."""
        from datetime import datetime, timezone

        at_iso = opened_at or datetime.now(timezone.utc).isoformat()
        query = (
            UPSERT_OPENED_VIDEO
            if resource_type == "video"
            else UPSERT_OPENED_READING
        )
        self._session.run(
            query,
            user_id=user_id,
            resource_id=resource_id,
            opened_at=at_iso,
        ).consume()

    # ── Reads ────────────────────────────────────────────────────

    def get_student_mastery(
        self, user_id: int, course_id: int | None = None
    ) -> list[dict]:
        if course_id is not None:
            result = self._session.run(
                GET_STUDENT_MASTERY_FOR_COURSE, user_id=user_id, course_id=course_id
            )
        else:
            result = self._session.run(GET_STUDENT_MASTERY, user_id=user_id)
        return [dict(r) for r in result]

    def get_all_skills_with_concepts(self, course_id: int | None = None) -> list[dict]:
        if course_id is not None:
            result = self._session.run(GET_SKILLS_FOR_COURSE, course_id=course_id)
        else:
            result = self._session.run(GET_ALL_SKILLS_WITH_CONCEPTS)
        return [dict(r) for r in result]

    def get_student_selected_skills(
        self, user_id: int, course_id: int | None = None
    ) -> list[dict]:
        """Return only the skills this student has explicitly selected.

        Falls back to get_all_skills_with_concepts when no selected skills found,
        so the system still works before skill selection is completed.
        """
        if course_id is not None:
            result = self._session.run(
                GET_STUDENT_SELECTED_SKILLS_FOR_COURSE,
                user_id=user_id,
                course_id=course_id,
            )
        else:
            result = self._session.run(GET_STUDENT_SELECTED_SKILLS, user_id=user_id)
        rows = [dict(r) for r in result]
        # Fall back to all course skills if student hasn't selected any yet
        if not rows:
            return self.get_all_skills_with_concepts(course_id)
        return rows

    def get_prerequisite_edges(self) -> list[dict]:
        result = self._session.run(GET_PREREQUISITE_MATRIX)
        return [dict(r) for r in result]

    def get_student_timeline(
        self, user_id: int, course_id: int | None = None
    ) -> list[dict]:
        if course_id is not None:
            result = self._session.run(
                GET_STUDENT_INTERACTION_TIMELINE_FOR_COURSE,
                user_id=user_id,
                course_id=course_id,
            )
        else:
            result = self._session.run(
                GET_STUDENT_INTERACTION_TIMELINE, user_id=user_id
            )
        return [dict(r) for r in result]

    def get_questions_for_skill(self, skill_name: str, limit: int = 10) -> list[dict]:
        result = self._session.run(
            GET_QUESTIONS_FOR_SKILL, skill_name=skill_name, limit=limit
        )
        return [dict(r) for r in result]

    def create_student_event(self, user_id: int, event: dict) -> dict:
        created_at_ts = int(time.time())
        event_id = str(event.get("id") or f"evt_{uuid.uuid4().hex[:16]}")
        payload = {
            "event_id": event_id,
            "user_id": user_id,
            "date": event["date"],
            "title": event["title"],
            "event_type": event["event_type"],
            "duration_minutes": event.get("duration_minutes"),
            "notes": event.get("notes", ""),
            "created_at_ts": created_at_ts,
        }
        rec = self._session.run(CREATE_STUDENT_EVENT, **payload).single()
        return dict(rec) if rec else {}

    def get_student_events(
        self,
        user_id: int,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        result = self._session.run(
            GET_STUDENT_EVENTS,
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
        )
        return [dict(r) for r in result]

    def delete_student_event(self, user_id: int, event_id: str) -> bool:
        rec = self._session.run(
            DELETE_STUDENT_EVENT,
            user_id=user_id,
            event_id=event_id,
        ).single()
        deleted_count = int((rec or {}).get("deleted_count", 0))
        return deleted_count > 0
