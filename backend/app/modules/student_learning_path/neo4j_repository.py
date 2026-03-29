"""Neo4j repository for student learning paths.

Handles SELECTED_SKILL, INTERESTED_IN relationships, skill banks with
selection overlay, peer counts, and full learning path reads.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from neo4j import Session as Neo4jSession

logger = logging.getLogger(__name__)


def select_skills(
    session: Neo4jSession,
    student_id: int,
    skill_names: list[str],
    source: str,
) -> int:
    """Write SELECTED_SKILL relationships. Idempotent via MERGE."""
    now = datetime.now(UTC).isoformat()
    result = session.run(
        """
        UNWIND $skill_names AS skill_name
        MATCH (u:USER:STUDENT {id: $student_id}), (sk:SKILL {name: skill_name})
        MERGE (u)-[r:SELECTED_SKILL]->(sk)
        ON CREATE SET r.selected_at = datetime($now), r.source = $source
        ON MATCH SET r.source = $source
        RETURN count(r) AS written
        """,
        student_id=student_id,
        skill_names=skill_names,
        source=source,
        now=now,
    )
    record = result.single()
    return record["written"] if record else 0


def deselect_skills(
    session: Neo4jSession,
    student_id: int,
    skill_names: list[str],
) -> int:
    """Remove SELECTED_SKILL relationships."""
    result = session.run(
        """
        UNWIND $skill_names AS skill_name
        MATCH (u:USER:STUDENT {id: $student_id})-[r:SELECTED_SKILL]->(sk:SKILL {name: skill_name})
        DELETE r
        RETURN count(*) AS deleted
        """,
        student_id=student_id,
        skill_names=skill_names,
    )
    record = result.single()
    return record["deleted"] if record else 0


def select_job_postings(
    session: Neo4jSession,
    student_id: int,
    posting_urls: list[str],
) -> int:
    """Write INTERESTED_IN + transitive SELECTED_SKILL for market skills sourced from each posting."""
    now = datetime.now(UTC).isoformat()
    result = session.run(
        """
        UNWIND $posting_urls AS url
        MATCH (u:USER:STUDENT {id: $student_id}), (jp:JOB_POSTING {url: url})
        MERGE (u)-[r:INTERESTED_IN]->(jp)
        ON CREATE SET r.selected_at = datetime($now)
        WITH u, jp
        MATCH (ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
        MERGE (u)-[r2:SELECTED_SKILL]->(ms)
        ON CREATE SET r2.selected_at = datetime($now), r2.source = 'job_posting'
        RETURN count(DISTINCT jp) AS postings_linked
        """,
        student_id=student_id,
        posting_urls=posting_urls,
        now=now,
    )
    record = result.single()
    return record["postings_linked"] if record else 0


def deselect_job_posting(
    session: Neo4jSession,
    student_id: int,
    posting_url: str,
) -> int:
    """Remove INTERESTED_IN and orphaned SELECTED_SKILL relationships."""
    result = session.run(
        """
        MATCH (u:USER:STUDENT {id: $student_id})-[r:INTERESTED_IN]->(jp:JOB_POSTING {url: $url})
        DELETE r
        WITH u, jp
        MATCH (ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
        MATCH (u)-[r2:SELECTED_SKILL {source: 'job_posting'}]->(ms)
        WHERE NOT EXISTS {
            MATCH (u)-[:INTERESTED_IN]->(:JOB_POSTING)<-[:SOURCED_FROM]-(ms)
        }
        DELETE r2
        RETURN count(r2) AS orphans_deleted
        """,
        student_id=student_id,
        url=posting_url,
    )
    record = result.single()
    return record["orphans_deleted"] if record else 0


def get_selected_skills(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
) -> list[dict]:
    """Return selected skills for a student in a course."""
    result = session.run(
        """
        MATCH (u:USER:STUDENT {id: $student_id})-[r:SELECTED_SKILL]->(sk:SKILL)
        MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(sk)
        RETURN sk {
            .name, .description,
            source: r.source,
            selected_at: toString(r.selected_at),
            chapter_title: ch.title,
            chapter_index: ch.chapter_index,
            skill_type: CASE WHEN sk:BOOK_SKILL THEN 'book' ELSE 'market' END,
            concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c { .name, .description }]
        } AS skill
        ORDER BY ch.chapter_index, sk.name
        """,
        student_id=student_id,
        course_id=course_id,
    )
    return [r["skill"] for r in result]


def get_selected_job_postings(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
) -> list[dict]:
    """Return job postings the student is interested in."""
    result = session.run(
        """
        MATCH (u:USER:STUDENT {id: $student_id})-[:INTERESTED_IN]->(jp:JOB_POSTING)
        RETURN jp {
            .url, .title, .company,
            skills: [
                (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)
                -[:HAS_SKILL]->(ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
                | ms.name
            ]
        } AS posting
        """,
        student_id=student_id,
        course_id=course_id,
    )
    return [r["posting"] for r in result]


def get_skill_resource_status(
    session: Neo4jSession,
    skill_names: list[str],
) -> dict[str, dict]:
    """Check existing resources and questions per skill."""
    result = session.run(
        """
        UNWIND $skill_names AS skill_name
        MATCH (sk:SKILL {name: skill_name})
        RETURN sk.name AS name,
            size([(sk)-[:HAS_READING]->(:READING_RESOURCE) | 1]) AS reading_count,
            size([(sk)-[:HAS_VIDEO]->(:VIDEO_RESOURCE) | 1]) AS video_count,
            size([(sk)-[:HAS_QUESTION]->(:QUESTION) | 1]) AS question_count
        """,
        skill_names=skill_names,
    )
    status: dict[str, dict] = {}
    for r in result:
        status[r["name"]] = {
            "has_readings": r["reading_count"] > 0,
            "has_videos": r["video_count"] > 0,
            "has_questions": r["question_count"] > 0,
        }
    return status


def get_learning_path(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
) -> dict:
    """Full personalized learning path: chapters → selected skills → resources + questions."""
    # Get course title
    course_row = session.run(
        "MATCH (cl:CLASS {id: $course_id}) RETURN cl.title AS title",
        course_id=course_id,
    ).single()
    course_title = course_row["title"] if course_row else ""

    # Get chapters with selected skills and their resources using nested COLLECT
    result = session.run(
        """
        MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)
        WHERE EXISTS { (ch)-[:HAS_SKILL]->()<-[:SELECTED_SKILL]-(:USER:STUDENT {id: $student_id}) }
        WITH ch ORDER BY ch.chapter_index
        RETURN ch {
            .title,
            .chapter_index,
            description: ch.summary,
            selected_skills: COLLECT {
                MATCH (ch)-[:HAS_SKILL]->(sk:SKILL)<-[sel:SELECTED_SKILL]-(:USER:STUDENT {id: $student_id})
                RETURN sk {
                    .name,
                    .description,
                    source: sel.source,
                    skill_type: CASE WHEN sk:BOOK_SKILL THEN 'book' ELSE 'market' END,
                    concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c { .name, .description }],
                    readings: [(sk)-[:HAS_READING]->(rr:READING_RESOURCE) | rr {
                        .title, .url, .domain, .snippet, .resource_type,
                        .final_score, .concepts_covered
                    }],
                    videos: [(sk)-[:HAS_VIDEO]->(vr:VIDEO_RESOURCE) | vr {
                        .title, .url, .domain, .snippet, .video_id,
                        .resource_type, .final_score, .concepts_covered
                    }],
                    questions: COLLECT {
                        MATCH (sk)-[:HAS_QUESTION]->(q:QUESTION)
                        RETURN q {
                            .id, .text, .difficulty, .answer
                        } AS question
                        ORDER BY CASE q.difficulty
                            WHEN 'easy' THEN 0
                            WHEN 'medium' THEN 1
                            WHEN 'hard' THEN 2
                        END
                    }
                } AS skill
                ORDER BY sk.name
            }
        } AS chapter
        """,
        student_id=student_id,
        course_id=course_id,
    )

    chapters = []
    total_skills = 0
    skills_with_resources = 0

    for r in result:
        ch = r["chapter"]
        # Populate resource_status and counts
        for sk in ch["selected_skills"]:
            has_resources = (
                len(sk.get("readings", [])) > 0 or len(sk.get("videos", [])) > 0
            )
            sk["resource_status"] = "loaded" if has_resources else "pending"
            total_skills += 1
            if has_resources:
                skills_with_resources += 1
        chapters.append(ch)

    return {
        "course_id": course_id,
        "course_title": course_title,
        "chapters": chapters,
        "total_selected_skills": total_skills,
        "skills_with_resources": skills_with_resources,
    }


def get_peer_selection_counts(
    session: Neo4jSession,
    course_id: int,
) -> dict[str, int]:
    """Count how many students selected each skill (for peer badges)."""
    result = session.run(
        """
        MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)
              -[:HAS_SKILL]->(sk:SKILL)<-[:SELECTED_SKILL]-(s:STUDENT)
        RETURN sk.name AS skill_name, count(DISTINCT s) AS student_count
        """,
        course_id=course_id,
    )
    return {r["skill_name"]: r["student_count"] for r in result}


def get_student_skill_banks(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
) -> dict:
    """Skill banks with selection overlay + peer counts.

    Returns the same structure as teacher skill banks but augmented with
    is_selected, source, and peer_count per skill.
    """
    # Selected skills for this student
    selected_result = session.run(
        """
        MATCH (u:USER:STUDENT {id: $student_id})-[r:SELECTED_SKILL]->(sk:SKILL)
        MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(sk)
        RETURN sk.name AS name, r.source AS source
        """,
        student_id=student_id,
        course_id=course_id,
    )
    selected_map = {r["name"]: r["source"] for r in selected_result}

    # Interested postings
    interested_result = session.run(
        """
        MATCH (u:USER:STUDENT {id: $student_id})-[:INTERESTED_IN]->(jp:JOB_POSTING)
        RETURN jp.url AS url
        """,
        student_id=student_id,
    )
    interested_urls = [r["url"] for r in interested_result]

    # Peer counts
    peer_counts = get_peer_selection_counts(session, course_id)

    return {
        "selected_skill_names": list(selected_map.keys()),
        "selected_map": selected_map,
        "interested_posting_urls": interested_urls,
        "peer_selection_counts": peer_counts,
    }
