"""Neo4j repository for student learning paths.

Handles SELECTED_SKILL, INTERESTED_IN relationships, skill banks with
selection overlay, peer counts, and full learning path reads.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from neo4j import Session as Neo4jSession

from app.modules.courses.neo4j_repository import CourseGraphRepository

from .schemas import (
    PrerequisiteEdge,
    SkillSelectionRange,
    StudentSkillBankBook,
    StudentSkillBankBookChapter,
    StudentSkillBankJobPosting,
    StudentSkillBankResponse,
    StudentSkillBankSkill,
)

logger = logging.getLogger(__name__)

QUESTION_OPTIONS_KEY = "options"
QUESTION_CORRECT_OPTION_KEY = "correct_option"
INTERESTED_IN_REL_TYPE = "INTERESTED_IN"

_BOOK_SKILL_BANKS_QUERY = """
MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(b:BOOK)
WITH b ORDER BY b.title
RETURN b {
    book_id: coalesce(b.id, elementId(b)),
    title: coalesce(b.title, 'Untitled book'),
    .authors,
    chapters: COLLECT {
        MATCH (b)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)
        RETURN ch {
            chapter_id: coalesce(ch.id, elementId(ch)),
            title: coalesce(
                ch.title,
                CASE
                    WHEN ch.chapter_index IS NOT NULL THEN 'Chapter ' + toString(ch.chapter_index)
                    ELSE 'Untitled chapter'
                END
            ),
            chapter_index: coalesce(ch.chapter_index, 0),
            skills: COLLECT {
                MATCH (ch)-[:HAS_SKILL]->(bs:BOOK_SKILL)
                RETURN bs {
                    .name,
                    .description
                } AS skill
                ORDER BY bs.name
            }
        } AS chapter
        ORDER BY ch.chapter_index
    }
} AS book
ORDER BY b.title
"""

_MARKET_SKILL_BANK_QUERY = """
MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
      <-[:MAPPED_TO]-(ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp:JOB_POSTING)
WHERE ms.course_id = $course_id OR ms.course_id IS NULL
WITH DISTINCT jp
RETURN jp {
    .url,
    .title,
    .company,
    .site,
    .search_term,
    skills: COLLECT {
        MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
              <-[:MAPPED_TO]-(ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
        WHERE ms.course_id = $course_id OR ms.course_id IS NULL
        WITH ms
        ORDER BY ms.name, CASE WHEN ms.course_id = $course_id THEN 0 ELSE 1 END
        WITH ms.name AS skill_name, collect(ms {
            .name,
            .description,
            .category
        }) AS candidates
        RETURN head(candidates) AS skill
        ORDER BY skill.name
    }
} AS job_posting
ORDER BY jp.title, jp.company, jp.url
"""

_INTERESTED_JOB_POSTING_URLS_QUERY = """
MATCH (u:USER:STUDENT {id: $student_id})-[r]->(jp:JOB_POSTING)
WHERE type(r) = $relationship_type
RETURN jp.url AS url
"""


def _build_quiz_progress_map(progress_rows: list[dict]) -> dict[int, dict[str, int]]:
    return {
        row["chapter_index"]: {
            "easy_question_count": row["easy_question_count"],
            "answered_count": row["answered_count"],
        }
        for row in progress_rows
    }


def _resolve_quiz_status(chapter_index: int, answered_count: int) -> str:
    if chapter_index == 1:
        return "quiz_required" if answered_count == 0 else "learning"
    return "locked"


def select_skills(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
    skill_names: list[str],
    source: str,
) -> int:
    """Write SELECTED_SKILL relationships. Idempotent via MERGE."""
    now = datetime.now(UTC).isoformat()
    if source == "book":
        skill_match = """
        MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)
              -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(candidate:BOOK_SKILL {name: skill_name})
        WITH u, skill_name, head(collect(DISTINCT candidate)) AS sk
        """
    else:
        skill_match = """
        MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
              <-[:MAPPED_TO]-(candidate:MARKET_SKILL {name: skill_name})
        WHERE candidate.course_id = $course_id OR candidate.course_id IS NULL
        WITH u, skill_name, candidate
        ORDER BY CASE WHEN candidate.course_id = $course_id THEN 0 ELSE 1 END
        WITH u, skill_name, head(collect(candidate)) AS sk
        """
    query = (
        """
        UNWIND $skill_names AS skill_name
        MATCH (u:USER:STUDENT {id: $student_id})
        """
        + skill_match
        + """
        WHERE sk IS NOT NULL
        MERGE (u)-[r:SELECTED_SKILL]->(sk)
        ON CREATE SET r.selected_at = datetime($now), r.source = $source
        ON MATCH SET r.source = $source
        RETURN count(DISTINCT sk) AS written
        """
    )
    result = session.run(
        query,
        student_id=student_id,
        course_id=course_id,
        skill_names=skill_names,
        source=source,
        now=now,
    )
    record = result.single()
    return record["written"] if record else 0


def deselect_skills(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
    skill_names: list[str],
) -> int:
    """Remove SELECTED_SKILL relationships."""
    result = session.run(
        """
        UNWIND $skill_names AS skill_name
        MATCH (u:USER:STUDENT {id: $student_id})-[r:SELECTED_SKILL]->(sk:SKILL {name: skill_name})
        WHERE EXISTS {
            MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)
                  -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(sk)
        } OR EXISTS {
            MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
                  <-[:MAPPED_TO]-(sk)
        }
        DELETE r
        RETURN count(*) AS deleted
        """,
        student_id=student_id,
        course_id=course_id,
        skill_names=skill_names,
    )
    record = result.single()
    return record["deleted"] if record else 0


def select_job_postings(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
    posting_urls: list[str],
) -> int:
    """Write INTERESTED_IN + transitive SELECTED_SKILL for market skills sourced from each posting."""
    now = datetime.now(UTC).isoformat()
    result = session.run(
        """
        UNWIND $posting_urls AS url
        MATCH (u:USER:STUDENT {id: $student_id}), (jp:JOB_POSTING {url: url})
        WHERE EXISTS {
            MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
                  <-[:MAPPED_TO]-(ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
            WHERE ms.course_id = $course_id OR ms.course_id IS NULL
        }
        MERGE (u)-[r:INTERESTED_IN]->(jp)
        ON CREATE SET r.selected_at = datetime($now)
        WITH DISTINCT u, jp
        MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
              <-[:MAPPED_TO]-(ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
        WHERE ms.course_id = $course_id OR ms.course_id IS NULL
        WITH u, jp, ms.name AS skill_name, ms
        ORDER BY CASE WHEN ms.course_id = $course_id THEN 0 ELSE 1 END
        WITH u, jp, skill_name, head(collect(ms)) AS ms
        MERGE (u)-[r2:SELECTED_SKILL]->(ms)
        ON CREATE SET r2.selected_at = datetime($now), r2.source = 'job_posting'
        RETURN count(DISTINCT jp) AS postings_linked
        """,
        student_id=student_id,
        course_id=course_id,
        posting_urls=posting_urls,
        now=now,
    )
    record = result.single()
    return record["postings_linked"] if record else 0


def deselect_job_posting(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
    posting_url: str,
) -> int:
    """Remove INTERESTED_IN and orphaned SELECTED_SKILL relationships."""
    result = session.run(
        """
        MATCH (u:USER:STUDENT {id: $student_id})-[r]->(jp:JOB_POSTING {url: $url})
        WHERE type(r) = $relationship_type
        DELETE r
        WITH u, jp
        MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
              <-[:MAPPED_TO]-(ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
        WHERE ms.course_id = $course_id OR ms.course_id IS NULL
        MATCH (u)-[r2:SELECTED_SKILL {source: 'job_posting'}]->(ms)
        WHERE NOT EXISTS {
            MATCH (u)-[ri]->(:JOB_POSTING)<-[:SOURCED_FROM]-(ms)
            WHERE type(ri) = $relationship_type
        }
        DELETE r2
        RETURN count(r2) AS orphans_deleted
        """,
        student_id=student_id,
        course_id=course_id,
        url=posting_url,
        relationship_type=INTERESTED_IN_REL_TYPE,
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
        MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)<-[:MAPPED_TO]-(sk)
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
        MATCH (u:USER:STUDENT {id: $student_id})-[r]->(jp:JOB_POSTING)
        WHERE type(r) = $relationship_type
        RETURN jp {
            .url, .title, .company,
            skills: COLLECT {
                MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
                      <-[:MAPPED_TO]-(ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
                WHERE ms.course_id = $course_id OR ms.course_id IS NULL
                WITH ms
                ORDER BY ms.name, CASE WHEN ms.course_id = $course_id THEN 0 ELSE 1 END
                WITH ms.name AS skill_name, collect(ms) AS candidates
                RETURN head(candidates).name AS skill_name
                ORDER BY skill_name
            ]
        } AS posting
        """,
        student_id=student_id,
        course_id=course_id,
        relationship_type=INTERESTED_IN_REL_TYPE,
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
            size([(sk)-[:HAS_QUESTION]->(:QUESTION) | 1]) AS question_count,
            size([
                (sk)-[:HAS_QUESTION]->(q:QUESTION)
                WHERE size(coalesce(q[$options_key], [])) = 4
                  AND q[$correct_option_key] IN ['A', 'B', 'C', 'D']
                | 1
            ]) AS mcq_question_count
        """,
        skill_names=skill_names,
        options_key=QUESTION_OPTIONS_KEY,
        correct_option_key=QUESTION_CORRECT_OPTION_KEY,
    )
    status: dict[str, dict] = {}
    for r in result:
        status[r["name"]] = {
            "has_readings": r["reading_count"] > 0,
            "has_videos": r["video_count"] > 0,
            "has_questions": r["question_count"] == 3 and r["mcq_question_count"] == 3,
        }
    return status


def get_chapter_easy_questions(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
    chapter_index: int,
) -> dict:
    """Return easy quiz questions for the student's selected skills in a chapter."""
    result = session.run(
        """
        MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER {chapter_index: $chapter_index})
        MATCH (ch)<-[:MAPPED_TO]-(sk:SKILL)<-[:SELECTED_SKILL]-(u:USER:STUDENT {id: $student_id})
        MATCH (sk)-[:HAS_QUESTION]->(q:QUESTION {difficulty: 'easy'})
        OPTIONAL MATCH (u)-[a:ANSWERED]->(q)
        RETURN ch.title AS chapter_title,
               q.id AS id,
               q.text AS text,
               sk.name AS skill_name,
               coalesce(q[$options_key], []) AS options,
               CASE
                   WHEN a IS NULL THEN NULL
                   ELSE {
                       selected_option: a.selected_option,
                       answered_right: a.answered_right,
                       answered_at: toString(a.answered_at)
                   }
               END AS previous_answer
        ORDER BY sk.name
        """,
        student_id=student_id,
        course_id=course_id,
        chapter_index=chapter_index,
        options_key=QUESTION_OPTIONS_KEY,
    )

    questions: list[dict] = []
    previous_answers: dict[str, dict] = {}
    chapter_title = ""

    for record in result:
        chapter_title = record["chapter_title"] or chapter_title
        question = {
            "id": record["id"],
            "skill_name": record["skill_name"],
            "text": record["text"],
            "options": record["options"],
        }
        questions.append(question)

        previous_answer = record["previous_answer"]
        if previous_answer:
            previous_answers[record["id"]] = previous_answer

    return {
        "chapter_title": chapter_title,
        "questions": questions,
        "previous_answers": previous_answers,
    }


def submit_chapter_answers(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
    chapter_index: int,
    submissions: list[dict[str, str]],
) -> list[dict]:
    """Persist entry-quiz answers for the student's selected skills in a chapter."""
    result = session.run(
        """
        MATCH (u:USER:STUDENT {id: $student_id})
        UNWIND $submissions AS sub
        MATCH (q:QUESTION {id: sub.question_id, difficulty: 'easy'})
        MATCH (sk:SKILL)-[:HAS_QUESTION]->(q)
        MATCH (u)-[:SELECTED_SKILL]->(sk)
        MATCH (sk)-[:MAPPED_TO]->(ch:COURSE_CHAPTER {chapter_index: $chapter_index})
        MATCH (:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch)
        WITH u, q, sk, sub,
             (sub.selected_option = q[$correct_option_key]) AS correct
        MERGE (u)-[a:ANSWERED]->(q)
        SET a.answered_at = datetime(),
            a.answered_right = correct,
            a.selected_option = sub.selected_option
        RETURN q.id AS question_id,
               sk.name AS skill_name,
               sub.selected_option AS selected_option,
               correct AS answered_right,
               q[$correct_option_key] AS correct_option
        ORDER BY sk.name
        """,
        student_id=student_id,
        course_id=course_id,
        chapter_index=chapter_index,
        submissions=submissions,
        correct_option_key=QUESTION_CORRECT_OPTION_KEY,
    )
    return [record.data() if hasattr(record, "data") else record for record in result]


def get_chapter_quiz_progress(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
) -> list[dict]:
    """Return easy-question counts and answer counts for selected-skill chapters."""
    result = session.run(
        """
        MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)
        WHERE EXISTS {
            MATCH (ch)<-[:MAPPED_TO]-(:SKILL)<-[:SELECTED_SKILL]-(:USER:STUDENT {id: $student_id})
        }
        OPTIONAL MATCH (ch)<-[:MAPPED_TO]-(sk:SKILL)<-[:SELECTED_SKILL]-(u:USER:STUDENT {id: $student_id})
        OPTIONAL MATCH (sk)-[:HAS_QUESTION]->(q:QUESTION {difficulty: 'easy'})
        OPTIONAL MATCH (u)-[a:ANSWERED]->(q)
        RETURN ch.chapter_index AS chapter_index,
               count(DISTINCT q) AS easy_question_count,
               count(DISTINCT CASE WHEN a IS NULL THEN NULL ELSE q END) AS answered_count
        ORDER BY ch.chapter_index
        """,
        student_id=student_id,
        course_id=course_id,
    )
    return [record.data() if hasattr(record, "data") else record for record in result]


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
        MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)
        WHERE EXISTS { (ch)<-[:MAPPED_TO]-()<-[:SELECTED_SKILL]-(:USER:STUDENT {id: $student_id}) }
        WITH ch ORDER BY ch.chapter_index
        RETURN ch {
            .title,
            .chapter_index,
            description: ch.description,
            selected_skills: COLLECT {
                MATCH (ch)<-[:MAPPED_TO]-(sk:SKILL)<-[sel:SELECTED_SKILL]-(:USER:STUDENT {id: $student_id})
                RETURN sk {
                    .name,
                    .description,
                    source: sel.source,
                    skill_type: CASE WHEN sk:BOOK_SKILL THEN 'book' ELSE 'market' END,
                    is_known: EXISTS {
                        MATCH (:USER:STUDENT {id: $student_id})-[a:ANSWERED {answered_right: true}]->(:QUESTION {difficulty: 'easy'})<-[:HAS_QUESTION]-(sk)
                    },
                    concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c { .name, .description }],
                    readings: [(sk)-[:HAS_READING]->(rr:READING_RESOURCE) | rr {
                        .title, .url,
                        domain: coalesce(rr.domain, ''),
                        snippet: coalesce(rr.snippet, ''),
                        search_content: coalesce(rr.search_content, ''),
                        search_result_url: coalesce(rr.search_result_url, ''),
                        search_result_domain: coalesce(rr.search_result_domain, ''),
                        source_engine: coalesce(rr.source_engine, ''),
                        source_engines: coalesce(rr.source_engines, []),
                        search_metadata_json: coalesce(rr.search_metadata_json, '[]'),
                        .resource_type, .final_score,
                        concepts_covered: coalesce(rr.concepts_covered, [])
                    }],
                    videos: [(sk)-[:HAS_VIDEO]->(vr:VIDEO_RESOURCE) | vr {
                        .title, .url,
                        domain: coalesce(vr.domain, ''),
                        snippet: coalesce(vr.snippet, ''),
                        search_content: coalesce(vr.search_content, ''),
                        video_id: coalesce(vr.video_id, ''),
                        search_result_url: coalesce(vr.search_result_url, ''),
                        search_result_domain: coalesce(vr.search_result_domain, ''),
                        source_engine: coalesce(vr.source_engine, ''),
                        source_engines: coalesce(vr.source_engines, []),
                        search_metadata_json: coalesce(vr.search_metadata_json, '[]'),
                        .resource_type, .final_score,
                        concepts_covered: coalesce(vr.concepts_covered, [])
                    }],
                    questions: COLLECT {
                        MATCH (sk)-[:HAS_QUESTION]->(q:QUESTION)
                        RETURN q {
                            .id,
                            .text,
                            .difficulty,
                            options: coalesce(q[$options_key], [])
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
        options_key=QUESTION_OPTIONS_KEY,
    )

    chapters = []
    total_skills = 0
    skills_with_resources = 0
    quiz_progress_by_chapter = _build_quiz_progress_map(
        get_chapter_quiz_progress(session, student_id, course_id)
    )

    for r in result:
        ch = r["chapter"]
        quiz_progress = quiz_progress_by_chapter.get(
            ch["chapter_index"],
            {"easy_question_count": 0, "answered_count": 0},
        )
        ch["easy_question_count"] = quiz_progress["easy_question_count"]
        ch["answered_count"] = quiz_progress["answered_count"]
        ch["quiz_status"] = _resolve_quiz_status(
            ch["chapter_index"],
            ch["answered_count"],
        )
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
        MATCH (sk:SKILL)<-[:SELECTED_SKILL]-(s:STUDENT)
        WHERE EXISTS {
            MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)
                  -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(sk)
        } OR EXISTS {
            MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
                  <-[:MAPPED_TO]-(sk)
        }
        RETURN sk.name AS skill_name, count(DISTINCT s) AS student_count
        """,
        course_id=course_id,
    )
    return {r["skill_name"]: r["student_count"] for r in result}


def get_prerequisite_edges(
    session: Neo4jSession,
    course_id: int,
) -> list[PrerequisiteEdge]:
    result = session.run(
        """
        MATCH (cl:CLASS {id: $course_id})
        MATCH (cl)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
              <-[:MAPPED_TO]-(prerequisite:SKILL)-[r:PREREQUISITE]->(dependent:SKILL)
        RETURN
            prerequisite.name AS prerequisite_name,
            dependent.name AS dependent_name,
            coalesce(r.confidence, 'medium') AS confidence,
            coalesce(r.reasoning, '') AS reasoning
        UNION
        MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)
              -[:HAS_SKILL]->(prerequisite:SKILL)-[r:PREREQUISITE]->(dependent:SKILL)
        RETURN
            prerequisite.name AS prerequisite_name,
            dependent.name AS dependent_name,
            coalesce(r.confidence, 'medium') AS confidence,
            coalesce(r.reasoning, '') AS reasoning
        """,
        course_id=course_id,
    )
    return [
        PrerequisiteEdge.model_validate(
            record.data() if hasattr(record, "data") else record
        )
        for record in result
    ]


def get_student_skill_banks(
    session: Neo4jSession,
    student_id: int,
    course_id: int,
) -> StudentSkillBankResponse:
    """Skill banks with selection overlay + peer counts.

    Returns the same structure as teacher skill banks but augmented with
    is_selected, source, and peer_count per skill.
    """
    # Selected skills for this student
    selected_result = session.run(
        """
        MATCH (u:USER:STUDENT {id: $student_id})-[r:SELECTED_SKILL]->(sk:SKILL)
        WHERE EXISTS {
            MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)
                  -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(sk)
        } OR EXISTS {
            MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
                  <-[:MAPPED_TO]-(sk)
        }
        RETURN sk.name AS name, r.source AS source
        """,
        student_id=student_id,
        course_id=course_id,
    )
    selected_map = {r["name"]: r["source"] for r in selected_result}

    # Interested postings
    interested_result = session.run(
        _INTERESTED_JOB_POSTING_URLS_QUERY,
        student_id=student_id,
        relationship_type=INTERESTED_IN_REL_TYPE,
    )
    interested_urls = [r["url"] for r in interested_result]
    interested_url_set = set(interested_urls)

    # Peer counts
    peer_counts = get_peer_selection_counts(session, course_id)
    selection_range = SkillSelectionRange.model_validate(
        CourseGraphRepository(session).get_skill_selection_range(course_id=course_id)
    )
    prerequisite_edges = get_prerequisite_edges(session, course_id)

    book_result = session.run(_BOOK_SKILL_BANKS_QUERY, course_id=course_id)
    book_skill_banks = []
    for record in book_result:
        book = record["book"]
        chapters = []
        for chapter in book.get("chapters") or []:
            chapter_index = chapter.get("chapter_index")
            chapter_title = chapter.get("title") or (
                f"Chapter {chapter_index}"
                if chapter_index is not None
                else "Untitled chapter"
            )
            raw_skills = chapter.get("skills") or []
            skills = [
                StudentSkillBankSkill(
                    name=skill.get("name", ""),
                    description=skill.get("description"),
                    is_selected=skill.get("name", "") in selected_map,
                    source=selected_map.get(skill.get("name", "")),
                    peer_count=peer_counts.get(skill.get("name", ""), 0),
                )
                for skill in raw_skills
                if skill and skill.get("name")
            ]
            chapters.append(
                StudentSkillBankBookChapter(
                    chapter_id=chapter.get("chapter_id", ""),
                    title=chapter_title,
                    chapter_index=chapter_index or 0,
                    skills=skills,
                )
            )
        book_skill_banks.append(
            StudentSkillBankBook(
                book_id=book.get("book_id", ""),
                title=book.get("title") or "Untitled book",
                authors=book.get("authors"),
                chapters=chapters,
            )
        )

    market_result = session.run(_MARKET_SKILL_BANK_QUERY, course_id=course_id)
    market_skill_bank = []
    for record in market_result:
        posting = record["job_posting"]
        raw_skills = posting.get("skills") or []
        skills = [
            StudentSkillBankSkill(
                name=skill.get("name", ""),
                description=skill.get("description"),
                category=skill.get("category"),
                is_selected=skill.get("name", "") in selected_map,
                source=selected_map.get(skill.get("name", "")),
                peer_count=peer_counts.get(skill.get("name", ""), 0),
            )
            for skill in raw_skills
            if skill and skill.get("name")
        ]
        market_skill_bank.append(
            StudentSkillBankJobPosting(
                url=posting.get("url", ""),
                title=posting.get("title", ""),
                company=posting.get("company") or "",
                site=posting.get("site"),
                search_term=posting.get("search_term"),
                is_interested=posting.get("url", "") in interested_url_set,
                skills=skills,
            )
        )

    market_skill_bank.sort(
        key=lambda posting: (
            not posting.is_interested,
            posting.title.casefold(),
            posting.company.casefold(),
            posting.url,
        )
    )

    return StudentSkillBankResponse(
        book_skill_banks=book_skill_banks,
        market_skill_bank=market_skill_bank,
        selected_skill_names=list(selected_map.keys()),
        interested_posting_urls=interested_urls,
        peer_selection_counts=peer_counts,
        selection_range=selection_range,
        prerequisite_edges=prerequisite_edges,
    )
