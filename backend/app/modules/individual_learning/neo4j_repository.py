"""Neo4j repository helpers for individual learning onboarding."""

from __future__ import annotations

from datetime import UTC, datetime

from neo4j import Session as Neo4jSession

from .schemas import CVSkillExtraction


def upsert_cv_skills(
    session: Neo4jSession,
    *,
    user_id: int,
    skills: list[CVSkillExtraction],
    cv_document_id: int,
    extraction_run_id: int,
) -> int:
    result = session.run(
        """
        UNWIND $skills AS skill
        MATCH (u:USER:INDIVIDUAL {id: $user_id})
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
        RETURN count(DISTINCT sk) AS written
        """,
        user_id=user_id,
        skills=[skill.model_dump() for skill in skills],
        cv_document_id=cv_document_id,
        extraction_run_id=extraction_run_id,
        now=datetime.now(UTC).isoformat(),
    )
    record = result.single()
    return int(record["written"] if record else 0)


def upsert_job_postings_and_market_skills(
    session: Neo4jSession,
    *,
    jobs: list[dict],
    skills_by_job_url: dict[str, list[dict]],
) -> dict[str, int]:
    job_result = session.run(
        """
        UNWIND $jobs AS job
        MERGE (jp:JOB_POSTING {url: job.url})
        SET jp.title = coalesce(job.title, ''),
            jp.company = coalesce(job.company, ''),
            jp.site = coalesce(job.site, ''),
            jp.search_term = coalesce(job.search_term, ''),
            jp.country = coalesce(job.country, ''),
            jp.location = coalesce(job.location, ''),
            jp.description = coalesce(job.description, '')
        RETURN count(DISTINCT jp) AS written
        """,
        jobs=jobs,
    )
    jobs_record = job_result.single()
    jobs_written = int(jobs_record["written"] if jobs_record else 0)

    pairs = [
        {"url": url, **skill}
        for url, skills in skills_by_job_url.items()
        for skill in skills
        if skill.get("name")
    ]
    skill_result = session.run(
        """
        UNWIND $pairs AS pair
        MATCH (jp:JOB_POSTING {url: pair.url})
        MERGE (sk:SKILL:MARKET_SKILL {name: pair.name})
        ON CREATE SET sk.created_at = datetime($now)
        SET sk.category = coalesce(pair.category, sk.category, ''),
            sk.description = coalesce(pair.description, sk.description, ''),
            sk.source = 'individual_job_search'
        MERGE (sk)-[:SOURCED_FROM]->(jp)
        RETURN count(DISTINCT sk) AS written
        """,
        pairs=pairs,
        now=datetime.now(UTC).isoformat(),
    )
    skills_record = skill_result.single()
    return {
        "jobs": jobs_written,
        "market_skills": int(skills_record["written"] if skills_record else 0),
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
        UNWIND $posting_urls AS url
        MATCH (u:USER:INDIVIDUAL {id: $user_id})
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


def get_individual_skill_bank(
    session: Neo4jSession,
    *,
    user_id: int,
) -> list[dict]:
    result = session.run(
        """
        MATCH (u:USER:INDIVIDUAL {id: $user_id})-[:INTERESTED_IN]->(jp:JOB_POSTING)
        WITH DISTINCT jp
        RETURN jp {
            .url,
            .title,
            .company,
            .site,
            .search_term,
            .country,
            .location,
            skills: COLLECT {
                MATCH (sk:SKILL:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
                RETURN sk {
                    .name,
                    .category,
                    .description
                } AS skill
                ORDER BY skill.name
            }
        } AS job_posting
        ORDER BY jp.title, jp.company, jp.url
        """,
        user_id=user_id,
    )
    return [record["job_posting"] for record in result]
