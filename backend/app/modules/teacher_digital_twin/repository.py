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
MATCH (u:USER:STUDENT)-[:ENROLLED_IN]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
OPTIONAL MATCH (u)-[r:MASTERY_OF]->(s)
RETURN s.name AS skill_name,
       count(DISTINCT u) AS student_count,
       avg(coalesce(r.mastery, 0.0)) AS avg_mastery,
       1.0 - avg(coalesce(r.mastery, 0.0)) AS perceived_difficulty
ORDER BY perceived_difficulty DESC
"""


# ── Feature 2: Skill Popularity ───────────────────────────────────────────

GET_SKILL_POPULARITY: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
RETURN s.name AS skill_name, count(DISTINCT u) AS selection_count
ORDER BY selection_count DESC
"""

GET_COURSE_STUDENT_COUNT: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN]->(cl:CLASS {id: $course_id})
RETURN count(u) AS total_students
"""


# ── Feature 3: Class Mastery ───────────────────────────────────────────────

GET_CLASS_MASTERY: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
OPTIONAL MATCH (u)-[r:MASTERY_OF]->(s)
WITH u,
     count(DISTINCT s) AS selected_skill_count,
     avg(coalesce(r.mastery, 0.0)) AS avg_mastery,
     sum(CASE WHEN coalesce(r.mastery, 0.0) >= 0.90 THEN 1 ELSE 0 END) AS mastered_count,
     sum(CASE WHEN coalesce(r.mastery, 0.0) < 0.40 THEN 1 ELSE 0 END) AS struggling_count
RETURN u.id AS user_id,
       coalesce(u.first_name + ' ' + u.last_name, u.email) AS full_name,
       u.email AS email,
       selected_skill_count,
       avg_mastery,
       mastered_count,
       struggling_count
ORDER BY avg_mastery ASC
"""

GET_STUDENT_PCO_COUNT: LiteralString = """
MATCH (u:USER:STUDENT {id: $user_id})-[r:MASTERY_OF]->(s)
WHERE coalesce(r.mastery, 0.0) < 0.40 AND coalesce(r.decay, 1.0) < 0.60
RETURN count(s) AS pco_count
"""


# ── Feature 4: Student Groups ──────────────────────────────────────────────

GET_STUDENT_SKILLS: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
OPTIONAL MATCH (u)-[r:MASTERY_OF]->(s)
RETURN u.id AS user_id,
       coalesce(u.first_name + ' ' + u.last_name, u.email) AS full_name,
       collect(s.name) AS skill_names,
       avg(coalesce(r.mastery, 0.0)) AS avg_mastery
"""


# ── Feature 5: What-If Simulation ─────────────────────────────────────────

GET_CLASS_SKILL_MASTERY: LiteralString = """
MATCH (u:USER:STUDENT)-[:ENROLLED_IN]->(cl:CLASS {id: $course_id})
MATCH (u)-[:SELECTED_SKILL]->(s)
WHERE s:BOOK_SKILL OR s:MARKET_SKILL OR s:SKILL
OPTIONAL MATCH (u)-[r:MASTERY_OF]->(s)
RETURN s.name AS skill_name,
       collect({user_id: u.id, mastery: coalesce(r.mastery, 0.0)}) AS student_masteries
"""


# ── Repository class ───────────────────────────────────────────────────────


class TeacherDigitalTwinRepository:
    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

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
