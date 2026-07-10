"""Neo4j repository helpers for individual learning onboarding."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from neo4j import Session as Neo4jSession

from app.modules.question_generation.schemas import GeneratedQuestion

from .schemas import CVSkillExtraction

logger = logging.getLogger(__name__)


def upsert_cv_skills(
    session: Neo4jSession,
    *,
    user_id: int,
    skills: list[CVSkillExtraction],
    cv_document_id: int,
    extraction_run_id: int,
) -> int | None:
    normalized_skills: list[CVSkillExtraction] = []
    seen_skill_names: set[str] = set()
    for skill in skills:
        name = " ".join(skill.name.split())
        if not name or name.casefold() in seen_skill_names:
            continue
        seen_skill_names.add(name.casefold())
        normalized_skills.append(skill.model_copy(update={"name": name}))
    skill_names = [skill.name for skill in normalized_skills]
    result = session.run(
        """
        MERGE (u:USER {id: $user_id})
        SET u:INDIVIDUAL
        OPTIONAL MATCH (u)-[stale:HAS_SKILL]->(existing:SKILL:CV_SKILL)
        WITH u, [item IN collect({relationship: stale, name: existing.name})
                 WHERE item.relationship IS NOT NULL] AS current_skills
        FOREACH (item IN [item IN current_skills
                          WHERE NOT item.name IN $skill_names] |
            DELETE item.relationship
        )
        FOREACH (skill IN $skills |
            MERGE (sk:SKILL:CV_SKILL {name: skill.name})
            ON CREATE SET sk.created_at = datetime($now)
            SET sk.category = coalesce(skill.category, sk.category, ''),
                sk.source = 'cv'
            MERGE (u)-[r:HAS_SKILL]->(sk)
            SET r.source = 'cv',
                r.confidence = skill.confidence,
                r.evidence = skill.evidence,
                r.cv_document_id = $cv_document_id,
                r.extraction_run_id = $extraction_run_id,
                r.updated_at = datetime($now)
        )
        RETURN size($skills) AS written
        """,
        user_id=user_id,
        skill_names=skill_names,
        skills=[skill.model_dump() for skill in normalized_skills],
        cv_document_id=cv_document_id,
        extraction_run_id=extraction_run_id,
        now=datetime.now(UTC).isoformat(),
    )
    record = result.single()
    return int(record["written"]) if record is not None else None


def upsert_job_postings_and_market_skills(
    session: Neo4jSession,
    *,
    jobs: list[dict],
    skills_by_job_url: dict[str, list[dict]],
) -> dict[str, int]:
    job_skill_sets = [
        {
            "job": job,
            "skills": [
                skill
                for skill in skills_by_job_url.get(str(job.get("url", "")), [])
                if skill.get("name")
            ],
        }
        for job in jobs
    ]
    result = session.run(
        """
        UNWIND $job_skill_sets AS item
        WITH item.job AS job, item.skills AS skills
        MERGE (jp:JOB_POSTING {url: job.url})
        SET jp.title = coalesce(job.title, ''),
            jp.company = coalesce(job.company, ''),
            jp.site = coalesce(job.site, ''),
            jp.search_term = coalesce(job.search_term, ''),
            jp.country = coalesce(job.country, ''),
            jp.location = coalesce(job.location, ''),
            jp.description = coalesce(job.description, ''),
            jp.skill_extraction_status = coalesce(
                job.skill_extraction_status, 'completed'
            ),
            jp.skill_extraction_error = job.skill_extraction_error
        WITH jp, skills
        OPTIONAL MATCH (jp)<-[stale:SOURCED_FROM]-(:SKILL:MARKET_SKILL)
        WITH jp, skills, collect(stale) AS stale_relationships
        FOREACH (relationship IN stale_relationships | DELETE relationship)
        FOREACH (skill IN skills |
            MERGE (sk:SKILL:MARKET_SKILL {name: skill.name})
            ON CREATE SET sk.created_at = datetime($now)
            SET sk.category = coalesce(skill.category, sk.category, ''),
                sk.description = coalesce(skill.description, sk.description, ''),
                sk.source = 'individual_job_search'
            MERGE (sk)-[:SOURCED_FROM]->(jp)
        )
        RETURN count(DISTINCT jp) AS jobs,
               sum(size(skills)) AS market_skills
        """,
        job_skill_sets=job_skill_sets,
        now=datetime.now(UTC).isoformat(),
    )
    record = result.single()
    return {
        "jobs": int(record["jobs"] if record else 0),
        "market_skills": int(record["market_skills"] if record else 0),
    }


def select_job_postings(
    session: Neo4jSession,
    *,
    user_id: int,
    posting_urls: list[str],
    run_id: str,
) -> int:
    result = session.run(
        """
        MATCH (u:USER:INDIVIDUAL {id: $user_id})
        OPTIONAL MATCH (u)-[stale:INTERESTED_IN]->(:JOB_POSTING)
        WITH u, collect(stale) AS stale_relationships
        FOREACH (relationship IN stale_relationships | DELETE relationship)
        WITH u
        UNWIND $posting_urls AS url
        MATCH (jp:JOB_POSTING {url: url})
        MERGE (u)-[r:INTERESTED_IN]->(jp)
        ON CREATE SET r.selected_at = datetime($now)
        SET r.source = 'individual_job_search',
            r.job_search_run_id = $run_id
        RETURN count(DISTINCT jp) AS written
        """,
        user_id=user_id,
        posting_urls=posting_urls,
        run_id=run_id,
        now=datetime.now(UTC).isoformat(),
    )
    record = result.single()
    return int(record["written"] if record else 0)


def select_market_skills(
    session: Neo4jSession,
    *,
    user_id: int,
    skill_names: list[str],
    source: str = "individual_market_skill",
) -> int:
    result = session.run(
        """
        UNWIND $skill_names AS skill_name
        MATCH (u:USER:INDIVIDUAL {id: $user_id})
        MATCH (sk:SKILL:MARKET_SKILL {name: skill_name})
        MERGE (u)-[r:SELECTED_SKILL]->(sk)
        ON CREATE SET r.selected_at = datetime($now)
        SET r.source = $source
        RETURN count(DISTINCT sk) AS written
        """,
        user_id=user_id,
        skill_names=skill_names,
        source=source,
        now=datetime.now(UTC).isoformat(),
    )
    record = result.single()
    return int(record["written"] if record else 0)


def select_candidate_market_skills(
    session: Neo4jSession,
    *,
    user_id: int,
    skill_names: list[str],
    posting_urls: list[str],
    job_search_run_id: str,
    match_run_id: str,
) -> int:
    result = session.run(
        """
        MATCH (u:USER:INDIVIDUAL {id: $user_id})
        OPTIONAL MATCH (u)-[stale:SELECTED_SKILL]->(:SKILL:MARKET_SKILL)
        WITH u, collect(stale) AS stale_relationships
        FOREACH (relationship IN stale_relationships | DELETE relationship)
        WITH u
        UNWIND $skill_names AS skill_name
        MATCH (jp:JOB_POSTING)<-[:SOURCED_FROM]-(sk:SKILL:MARKET_SKILL {name: skill_name})
        WHERE jp.url IN $posting_urls
        WITH DISTINCT u, sk
        MERGE (u)-[r:SELECTED_SKILL]->(sk)
        ON CREATE SET r.selected_at = datetime($now)
        SET r.source = 'individual_market_skill',
            r.job_search_run_id = $job_search_run_id,
            r.match_run_id = $match_run_id
        RETURN count(DISTINCT sk) AS written
        """,
        user_id=user_id,
        skill_names=skill_names,
        posting_urls=posting_urls,
        job_search_run_id=job_search_run_id,
        match_run_id=match_run_id,
        now=datetime.now(UTC).isoformat(),
    )
    record = result.single()
    return int(record["written"] if record else 0)


def get_selected_market_skill_names(
    session: Neo4jSession,
    *,
    user_id: int,
) -> list[str]:
    result = session.run(
        """
        MATCH (:USER:INDIVIDUAL {id: $user_id})-[:SELECTED_SKILL]->(sk:MARKET_SKILL)
        RETURN sk.name AS name
        ORDER BY sk.name
        """,
        user_id=user_id,
    )
    return [record["name"] for record in result]


def resolve_market_skill_names(
    session: Neo4jSession,
    *,
    skill_names: list[str],
) -> list[str]:
    result = session.run(
        """
        UNWIND $skill_names AS skill_name
        MATCH (sk:SKILL:MARKET_SKILL {name: skill_name})
        RETURN DISTINCT sk.name AS name
        """,
        skill_names=skill_names,
    )
    resolved_names = {record["name"] for record in result}
    return [skill_name for skill_name in skill_names if skill_name in resolved_names]


def resolve_interested_market_skill_names(
    session: Neo4jSession,
    *,
    user_id: int,
    skill_names: list[str],
) -> list[str]:
    result = session.run(
        """
        MATCH (u:USER:INDIVIDUAL {id: $user_id})
        MATCH (u)-[:INTERESTED_IN]->(jp:JOB_POSTING)
        MATCH (sk:SKILL:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
        WHERE sk.name IN $skill_names
        RETURN DISTINCT sk.name AS name
        """,
        user_id=user_id,
        skill_names=skill_names,
    )
    resolved_names = {record["name"] for record in result}
    return [skill_name for skill_name in skill_names if skill_name in resolved_names]


def deselect_market_skills(
    session: Neo4jSession,
    *,
    user_id: int,
    skill_names: list[str],
) -> int:
    result = session.run(
        """
        UNWIND $skill_names AS skill_name
        MATCH (u:USER:INDIVIDUAL {id: $user_id})-[r:SELECTED_SKILL]->(sk:SKILL:MARKET_SKILL {name: skill_name})
        DELETE r
        RETURN count(*) AS deleted
        """,
        user_id=user_id,
        skill_names=skill_names,
    )
    record = result.single()
    return int(record["deleted"] if record else 0)


def get_market_skill_profiles(
    session: Neo4jSession,
    *,
    skill_names: list[str],
) -> list[dict]:
    result = session.run(
        """
        UNWIND $skill_names AS skill_name
        MATCH (sk:SKILL:MARKET_SKILL {name: skill_name})
        RETURN sk {
            .name,
            .description,
            .category,
            concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | {
                name: CASE
                    WHEN valueType(c.name) STARTS WITH 'STRING' THEN c.name
                    ELSE head(c.name)
                END,
                definition: coalesce(c.description, '')
            }],
            job_evidence: [(sk)-[:SOURCED_FROM]->(jp:JOB_POSTING) | jp.description][0..3]
        } AS skill
        """,
        skill_names=skill_names,
    )
    profiles_by_name = {record["skill"]["name"]: record["skill"] for record in result}
    return [
        profiles_by_name[skill_name]
        for skill_name in skill_names
        if skill_name in profiles_by_name
    ]


def get_selected_market_skill_profiles(
    session: Neo4jSession,
    *,
    user_id: int,
) -> list[dict]:
    selected_names = get_selected_market_skill_names(session, user_id=user_id)
    if not selected_names:
        return []
    return get_market_skill_profiles(session, skill_names=selected_names)


def write_market_skill_questions(
    session: Neo4jSession,
    skill_name: str,
    questions: list[GeneratedQuestion],
) -> int:
    now = datetime.now(UTC).isoformat()
    question_dicts = [
        {
            "id": str(uuid.uuid4()),
            "text": question.text,
            "difficulty": question.difficulty,
            "options": question.options,
            "correct_option": question.correct_option,
            "answer": question.answer,
            "skill_name": skill_name,
            "created_at": now,
        }
        for question in questions
    ]

    result = session.run(
        """
        MATCH (sk:SKILL:MARKET_SKILL {name: $skill_name})
        OPTIONAL MATCH (sk)-[:HAS_QUESTION]->(existing:QUESTION)
        WITH sk, collect(existing) AS existing_questions
        FOREACH (node IN existing_questions | DETACH DELETE node)
        WITH sk
        UNWIND $questions AS q
        CREATE (qn:QUESTION {
            id: q.id,
            text: q.text,
            difficulty: q.difficulty,
            options: q.options,
            correct_option: q.correct_option,
            answer: q.answer,
            skill_name: q.skill_name,
            created_at: datetime(q.created_at)
        })
        MERGE (sk)-[:HAS_QUESTION]->(qn)
        RETURN count(qn) AS written
        """,
        skill_name=skill_name,
        questions=question_dicts,
    )
    record = result.single()
    count = int(record["written"] if record else 0)
    logger.info("Wrote %d market-skill questions for skill %s", count, skill_name)
    return count


def get_individual_skill_bank(
    session: Neo4jSession,
    *,
    user_id: int,
) -> dict[str, list[dict] | list[str]]:
    interested_result = session.run(
        """
        MATCH (u:USER:INDIVIDUAL {id: $user_id})-[r:INTERESTED_IN]->(jp:JOB_POSTING)
        RETURN jp.url AS url
        """,
        user_id=user_id,
    )
    interested_urls = [record["url"] for record in interested_result]

    selected_names = get_selected_market_skill_names(session, user_id=user_id)

    bank_result = session.run(
        """
        UNWIND $interested_urls AS url
        MATCH (jp:JOB_POSTING {url: url})
        OPTIONAL MATCH (jp)<-[:SOURCED_FROM]-(ms:MARKET_SKILL)
        WITH jp, [skill IN collect(ms { .name, .description, .category })
                  WHERE skill.name IS NOT NULL] AS market_skills
        RETURN jp {
            .url, .title, .company, .site, .search_term,
            .skill_extraction_status, .skill_extraction_error,
            skills: market_skills
        } AS posting
        ORDER BY jp.title, jp.company, jp.url
        """,
        interested_urls=interested_urls,
    )
    return {
        "postings": [record["posting"] for record in bank_result],
        "selected_skill_names": selected_names,
        "interested_posting_urls": interested_urls,
    }


def get_individual_learning_path(
    session: Neo4jSession,
    *,
    user_id: int,
) -> dict[str, object]:
    result = session.run(
        """
        MATCH (u:USER:INDIVIDUAL {id: $user_id})-[sel:SELECTED_SKILL]->(sk:SKILL:MARKET_SKILL)
        OPTIONAL MATCH (sk)-[:HAS_READING]->(rr:READING_RESOURCE)
        OPTIONAL MATCH (sk)-[:HAS_VIDEO]->(vr:VIDEO_RESOURCE)
        OPTIONAL MATCH (sk)-[:HAS_QUESTION]->(q:QUESTION)
        WITH sk, sel,
             [item IN collect(DISTINCT CASE
                 WHEN rr IS NULL THEN NULL
                 ELSE rr {
                     .id,
                     .title,
                     .url,
                     .domain,
                     .snippet,
                     .search_content,
                     .resource_type,
                     .final_score
                 }
             END) WHERE item IS NOT NULL] AS readings,
             [item IN collect(DISTINCT CASE
                 WHEN vr IS NULL THEN NULL
                 ELSE vr {
                     .id,
                     .title,
                     .url,
                     .domain,
                     .snippet,
                     .search_content,
                     .video_id,
                     .resource_type,
                     .final_score
                 }
             END) WHERE item IS NOT NULL] AS videos,
             [item IN collect(DISTINCT CASE
                 WHEN q IS NULL THEN NULL
                 ELSE q {
                     .id,
                     .text,
                     .difficulty,
                     options: coalesce(q.options, [])
                 }
             END) WHERE item IS NOT NULL] AS questions
        RETURN sk {
            .name,
            .description,
            source: sel.source,
            selected_at: toString(sel.selected_at),
            readings: readings,
            videos: videos,
            questions: questions
        } AS skill
        ORDER BY sk.name
        """,
        user_id=user_id,
    )
    skills = [record["skill"] for record in result]
    return {
        "user_id": user_id,
        "selected_skills": skills,
        "total_selected_skills": len(skills),
        "skills_with_resources": sum(
            1 for skill in skills if skill.get("readings") or skill.get("videos")
        ),
    }
