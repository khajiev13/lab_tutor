from __future__ import annotations

import re
from collections.abc import Iterable

from app.modules.marketdemandanalyst.countries import normalize_job_search_country

_SKILL_SPLIT_RE = re.compile(r"[,/|;\n]+")
_DESCRIPTION_SKILL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bfastapi\b", re.IGNORECASE), "FastAPI"),
    (re.compile(r"\bdocker\b", re.IGNORECASE), "Docker"),
    (re.compile(r"\bkubernetes\b", re.IGNORECASE), "Kubernetes"),
    (re.compile(r"\bpostgres(?:ql)?\b", re.IGNORECASE), "PostgreSQL"),
    (re.compile(r"\bpython\b", re.IGNORECASE), "Python"),
    (re.compile(r"\bsql\b", re.IGNORECASE), "SQL"),
    (re.compile(r"\baws\b", re.IGNORECASE), "AWS"),
    (re.compile(r"\bazure\b", re.IGNORECASE), "Azure"),
)


def search_jobs_for_titles(
    target_titles: list[str],
    country: str,
    location: str,
) -> list[dict]:
    terms = [title.strip() for title in target_titles if title.strip()]
    if not terms:
        return []

    selected_country = normalize_job_search_country(country or location)
    try:
        from jobspy import scrape_jobs
    except ImportError:
        return []

    jobs_by_url: dict[str, dict] = {}
    for term in terms:
        try:
            results = scrape_jobs(
                site_name=["indeed", "linkedin"],
                search_term=term,
                location=location.strip() or selected_country.location,
                results_wanted=20,
                hours_old=72,
                country_indeed=selected_country.jobspy_country,
                description_format="markdown",
                linkedin_fetch_description=True,
                verbose=0,
            )
        except Exception:
            continue

        for _, row in results.iterrows():
            url = str(row.get("job_url", "")).strip()
            if not url:
                continue
            jobs_by_url[url] = {
                "url": url,
                "title": str(row.get("title", "")).strip(),
                "company": str(row.get("company_name") or row.get("company", "")).strip(),
                "site": str(row.get("site", "")).strip() or None,
                "search_term": term,
                "country": selected_country.jobspy_country,
                "location": str(row.get("location", "")).strip() or location.strip(),
                "description": str(row.get("description", "")).strip(),
                "skills": row.get("skills"),
            }
    return list(jobs_by_url.values())


def extract_market_skills_for_jobs(jobs: list[dict]) -> dict[str, list[dict]]:
    return {
        str(job.get("url", "")): _extract_job_skills(job)
        for job in jobs
        if str(job.get("url", "")).strip()
    }


def _extract_job_skills(job: dict) -> list[dict]:
    explicit_skills = _extract_explicit_skills(job.get("skills"))
    if explicit_skills:
        return explicit_skills

    description = str(job.get("description", "") or "")
    inferred: list[dict] = []
    for pattern, skill_name in _DESCRIPTION_SKILL_PATTERNS:
        if pattern.search(description):
            inferred.append(
                {
                    "name": skill_name,
                    "category": "Market Skill",
                    "description": f"Inferred from job description for {job.get('title', 'role')}",
                }
            )
    return inferred


def _extract_explicit_skills(raw_skills: object) -> list[dict]:
    values = _coerce_skill_values(raw_skills)
    unique_names: set[str] = set()
    extracted: list[dict] = []
    for value in values:
        for piece in _SKILL_SPLIT_RE.split(value):
            skill_name = piece.strip()
            if not skill_name:
                continue
            key = skill_name.casefold()
            if key in unique_names:
                continue
            unique_names.add(key)
            extracted.append({"name": skill_name, "category": "Market Skill"})
    return extracted


def _coerce_skill_values(raw_skills: object) -> list[str]:
    if raw_skills is None:
        return []
    if isinstance(raw_skills, str):
        return [raw_skills]
    if isinstance(raw_skills, dict):
        return [str(raw_skills.get("name", "")).strip()]
    if isinstance(raw_skills, Iterable):
        values: list[str] = []
        for item in raw_skills:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                values.append(str(item.get("name", "")).strip())
        return values
    return []
