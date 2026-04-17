"""Teacher Digital Twin — Neo4j repository.

All read queries for class-level analytics:
  - Skill difficulty aggregated from student mastery
  - Skill popularity from SELECTED_SKILL counts
  - Class mastery overview per student
  - Student group computation input
  - What-if simulation data
"""

from __future__ import annotations

from typing import LiteralString

from neo4j import Session as Neo4jSession

# ── Feature 1: Skill Difficulty ────────────────────────────────────────────

GET_SKILL_DIFFICULTY: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN_CLASS]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
WITH s, u,
     coalesce([(u)-[r:MASTERED]->(s) | r.mastery][0], 0.0) AS mastery_val
WITH s,
     count(DISTINCT u) AS student_count,
     avg(mastery_val) AS avg_mastery
RETURN s.name AS skill_name,
       student_count,
       avg_mastery,
       1.0 - avg_mastery AS perceived_difficulty
ORDER BY perceived_difficulty DESC, s.name
"""


# ── Feature 2: Skill Popularity ───────────────────────────────────────────

GET_SKILL_POPULARITY: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN_CLASS]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
RETURN s.name AS skill_name, count(DISTINCT u) AS selection_count
ORDER BY selection_count DESC
"""

GET_COURSE_STUDENT_COUNT: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN_CLASS]->(cl:CLASS {id: $course_id})
RETURN count(u) AS total_students
"""


# ── Feature 3: Class Mastery ───────────────────────────────────────────────

GET_CLASS_MASTERY: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN_CLASS]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
WITH u, s,
     coalesce([(u)-[r:MASTERED]->(s) | r.mastery][0], 0.0) AS mastery_val
WITH u,
     count(DISTINCT s) AS selected_skill_count,
     avg(mastery_val) AS avg_mastery,
     sum(CASE WHEN mastery_val >= 0.80 THEN 1 ELSE 0 END) AS mastered_count,
     sum(CASE WHEN mastery_val < 0.50 THEN 1 ELSE 0 END) AS struggling_count
RETURN u.id AS user_id,
       coalesce(u.first_name + ' ' + u.last_name, u.email) AS full_name,
       u.email AS email,
       selected_skill_count,
       avg_mastery,
       mastered_count,
       struggling_count
ORDER BY avg_mastery ASC, full_name
"""

GET_STUDENT_PCO_COUNT: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[r:MASTERED]->(s)
WHERE coalesce(r.mastery, 0.0) < 0.40 AND coalesce(r.decay, 1.0) < 0.60
RETURN count(s) AS pco_count
"""


# ── Feature 4: Student Groups ──────────────────────────────────────────────

GET_STUDENT_SKILLS: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN_CLASS]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
WITH u, s,
     coalesce([(u)-[r:MASTERED]->(s) | r.mastery][0], 0.0) AS mastery_val
ORDER BY u.id, s.name
WITH u,
     collect(s.name) AS skill_names,
     avg(mastery_val) AS avg_mastery
RETURN u.id AS user_id,
       coalesce(u.first_name + ' ' + u.last_name, u.email) AS full_name,
       skill_names,
       avg_mastery
ORDER BY u.id
"""


# ── Feature 5: What-If Simulation ─────────────────────────────────────────

GET_CLASS_SKILL_MASTERY: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN_CLASS]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
WITH s, u,
     coalesce([(u)-[r:MASTERED]->(s) | r.mastery][0], 0.0) AS mastery_val
ORDER BY s.name, u.id
WITH s,
     collect({user_id: u.id, mastery: mastery_val}) AS student_masteries
RETURN s.name AS skill_name,
       student_masteries
ORDER BY skill_name
"""


# ── Feature 6b: Skill Co-Selection (for coherence analysis) ───────────────

GET_SKILL_CO_SELECTION: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN_CLASS]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s.name IN $skill_names
WITH u, s,
     coalesce([(u)-[r:MASTERED]->(s) | r.mastery][0], -1.0) AS mastery_score
RETURN u.id AS user_id,
       s.name AS skill_name,
       mastery_score
ORDER BY user_id, skill_name
"""


# ── Repository class ───────────────────────────────────────────────────────

VERIFY_TEACHES_CLASS: LiteralString = """
MATCH (t:USER:TEACHER {id: $teacher_id})-[:TEACHES_CLASS]->(c:CLASS {id: $course_id})
RETURN count(t) > 0 AS teaches
"""


class TeacherDigitalTwinRepository:
    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    def teacher_teaches_class(self, teacher_id: int, course_id: int) -> bool:
        result = self._session.run(
            VERIFY_TEACHES_CLASS, teacher_id=teacher_id, course_id=course_id
        )
        record = result.single()
        return bool(record["teaches"]) if record else False

    def get_skill_difficulty(self, course_id: int) -> list[dict]:
        result = self._session.run(GET_SKILL_DIFFICULTY, course_id=course_id)
        return [dict(r) for r in result]

    def get_skill_popularity(self, course_id: int) -> list[dict]:
        result = self._session.run(GET_SKILL_POPULARITY, course_id=course_id)
        return [dict(r) for r in result]

    def get_total_students(self, course_id: int) -> int:
        result = self._session.run(GET_COURSE_STUDENT_COUNT, course_id=course_id)
        record = result.single()
        return int(record["total_students"]) if record else 0

    def get_class_mastery(self, course_id: int) -> list[dict]:
        result = self._session.run(GET_CLASS_MASTERY, course_id=course_id)
        return [dict(r) for r in result]

    def get_student_pco_count(self, user_id: int) -> int:
        result = self._session.run(GET_STUDENT_PCO_COUNT, user_id=user_id)
        record = result.single()
        return int(record["pco_count"]) if record else 0

    def get_student_skills_for_grouping(self, course_id: int) -> list[dict]:
        result = self._session.run(GET_STUDENT_SKILLS, course_id=course_id)
        return [dict(r) for r in result]

    def get_class_skill_mastery(self, course_id: int) -> list[dict]:
        result = self._session.run(GET_CLASS_SKILL_MASTERY, course_id=course_id)
        return [dict(r) for r in result]

    def get_skill_co_selection(
        self, course_id: int, skill_names: list[str]
    ) -> list[dict]:
        """Return (user_id, skill_name, mastery_score) rows for coherence analysis."""
        result = self._session.run(
            GET_SKILL_CO_SELECTION, course_id=course_id, skill_names=skill_names
        )
        return [dict(r) for r in result]
