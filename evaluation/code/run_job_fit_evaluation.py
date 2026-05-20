"""Run the frozen Lab Tutor job-fit evaluation from JSON inputs.

The script is intentionally independent from Neo4j. It reads the exact
portfolios and job postings stored in ``evaluation/input/job_fit_inputs.json``
and calls an OpenAI-compatible chat-completions endpoint for each
(portfolio, job) pair.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


SATISFACTION_WEIGHTS = {
    "fully_satisfied": 1.0,
    "satisfied": 0.75,
    "partly_satisfied": 0.40,
    "not_satisfied": 0.0,
}

SYSTEM_PROMPT = """You are an expert technical recruiter scoring whether a candidate's
portfolio satisfies a specific job posting.

## LABEL DEFINITIONS

Assign EXACTLY ONE label per job-required skill:

- "fully_satisfied"   - the portfolio includes a skill that directly
    names this requirement or the same technology, tool, or competency.
- "satisfied"         - the portfolio includes equivalent coverage that
    would reasonably satisfy the requirement, even if phrased differently.
- "partly_satisfied"  - the portfolio includes a related, prerequisite,
    or supporting skill, but not enough to claim the requirement is met.
- "not_satisfied"     - the portfolio contains no meaningful coverage
    for this requirement.

## SCORING RULES

1. Score whether the portfolio covers the job requirement, not whether
   the requirement is broadly related to the course.
2. Do NOT infer unlisted skills; use only the portfolio skills provided.
3. Do NOT reward extra portfolio skills unless they satisfy the specific
   requirement being rated.
4. Cite exact portfolio skill strings as evidence. If no skill supports
   the requirement, use an empty evidence_skills array.

## OUTPUT FORMAT

Return STRICT JSON only - no prose, no preamble, no markdown fences.
Provide one rating per job-required skill, in the SAME ORDER as the
input list.

{
  "job_title": "<string>",
  "job_company": "<string>",
  "portfolio_name": "<string>",
  "ratings": [
    {
      "requirement": "<verbatim job-required skill string>",
      "label": "fully_satisfied|satisfied|partly_satisfied|not_satisfied",
      "evidence_skills": ["<verbatim portfolio skill string>", "..."],
      "justification": "<one sentence, <=25 words>"
    }
  ]
}

FIELD CONSTRAINTS:
- "requirement" must equal the input requirement string verbatim.
- "evidence_skills" must equal portfolio skill strings verbatim.
- "justification" is one short sentence (<=25 words) explaining the verdict.
"""

USER_PROMPT_TEMPLATE = """## JOB POSTING

- Title:   {job_title}
- Company: {job_company}

## JOB DESCRIPTION

{job_description}

## JOB-REQUIRED SKILLS TO RATE

{required_block}

## PORTFOLIO TO EVALUATE

- Portfolio name: {portfolio_name}
- Number of portfolio skills: {n_skills}

Portfolio skills:
{portfolio_block}
"""


def load_input_bundle(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "portfolios" not in data or "jobs" not in data:
        raise ValueError("Input bundle must contain 'portfolios' and 'jobs'.")
    return data


def slug(value: str, *, max_length: int = 80) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return (cleaned or "x")[:max_length]


def normalize_label(label: Any) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", str(label or "").strip().lower()).strip("_")
    aliases = {
        "full": "fully_satisfied",
        "fully": "fully_satisfied",
        "partial": "partly_satisfied",
        "partially_satisfied": "partly_satisfied",
        "partly": "partly_satisfied",
        "none": "not_satisfied",
        "not": "not_satisfied",
        "unsatisfied": "not_satisfied",
    }
    value = aliases.get(value, value)
    return value if value in SATISFACTION_WEIGHTS else "not_satisfied"


def score_ratings(
    requirements: list[str],
    ratings: list[dict[str, Any]],
) -> tuple[float, dict[str, int], list[dict[str, Any]]]:
    rating_by_requirement = {
        str(item.get("requirement", "")).strip(): item
        for item in ratings
        if str(item.get("requirement", "")).strip()
    }
    lower_lookup = {key.lower(): value for key, value in rating_by_requirement.items()}
    counts = {label: 0 for label in SATISFACTION_WEIGHTS}
    weighted = 0.0
    rows: list[dict[str, Any]] = []

    for requirement in requirements:
        item = rating_by_requirement.get(requirement) or lower_lookup.get(requirement.lower()) or {}
        label = normalize_label(item.get("label"))
        evidence = item.get("evidence_skills") if isinstance(item.get("evidence_skills"), list) else []
        justification = str(item.get("justification", "")).strip()
        weight = SATISFACTION_WEIGHTS[label]
        counts[label] += 1
        weighted += weight
        rows.append(
            {
                "required_skill": requirement,
                "label": label,
                "weight": weight,
                "evidence_skills": evidence,
                "justification": justification,
            }
        )

    score = round(weighted / len(requirements), 4) if requirements else 0.0
    return score, counts, rows


def build_user_prompt(portfolio: dict[str, Any], job: dict[str, Any]) -> str:
    portfolio_block = "\n".join(f"  - {skill}" for skill in portfolio["skills"])
    required_block = "\n".join(f"  - {skill}" for skill in job["required_skills"])
    return USER_PROMPT_TEMPLATE.format(
        job_title=job["title"],
        job_company=job["company"],
        job_description=job.get("description") or "(no description available)",
        required_block=required_block,
        portfolio_name=portfolio["name"],
        portfolio_block=portfolio_block,
        n_skills=len(portfolio["skills"]),
    )


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def coerce_ratings(parsed: dict[str, Any], portfolio_skills: set[str]) -> list[dict[str, Any]]:
    raw_ratings = parsed.get("ratings", [])
    if not isinstance(raw_ratings, list):
        raise ValueError("Judge response field 'ratings' is not a list.")
    coerced: list[dict[str, Any]] = []
    for item in raw_ratings:
        if not isinstance(item, dict):
            continue
        evidence = []
        for skill in item.get("evidence_skills", []):
            skill_text = str(skill).strip()
            if skill_text in portfolio_skills and skill_text not in evidence:
                evidence.append(skill_text)
        coerced.append(
            {
                "requirement": str(item.get("requirement", "")).strip(),
                "label": normalize_label(item.get("label")),
                "evidence_skills": evidence,
                "justification": str(item.get("justification", "")).strip()[:300],
            }
        )
    return coerced


def chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout_seconds: int,
    use_response_format: bool,
) -> tuple[dict[str, Any], str]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if use_response_format:
        payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    return data, content


def rate_pair(
    *,
    portfolio: dict[str, Any],
    job: dict[str, Any],
    output_dir: Path,
    model: str,
    family: str,
    base_url: str,
    api_key: str,
    max_tokens: int,
    timeout_seconds: int,
    retries: int,
    refresh: bool,
    use_response_format: bool,
) -> dict[str, Any]:
    audit_dir = output_dir / "audit" / portfolio["name"]
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"{slug(portfolio['name'])}__{slug(job['title'])}__{slug(job['company'])}.json"

    if audit_path.exists() and not refresh:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        ratings = coerce_ratings(audit["parsed"], set(portfolio["skills"]))
    else:
        user_prompt = build_user_prompt(portfolio, job)
        last_error: Optional[Exception] = None
        for attempt in range(1, retries + 2):
            try:
                raw_response, content = chat_completion(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                    use_response_format=use_response_format,
                )
                parsed = extract_json_object(content)
                ratings = coerce_ratings(parsed, set(portfolio["skills"]))
                audit_path.write_text(
                    json.dumps(
                        {
                            "family": family,
                            "model": model,
                            "job_title": job["title"],
                            "job_company": job["company"],
                            "portfolio_name": portfolio["name"],
                            "created_at": datetime.now().isoformat(timespec="seconds"),
                            "system_prompt": SYSTEM_PROMPT,
                            "user_prompt": user_prompt,
                            "parsed": {"ratings": ratings},
                            "raw_response": raw_response,
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                break
            except (urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError) as exc:
                last_error = exc
                if attempt > retries:
                    raise RuntimeError(
                        f"Judge failed for {portfolio['name']} / {job['title']} @ {job['company']}: {exc}"
                    ) from exc
                time.sleep(min(2 * attempt, 10))
        else:
            raise RuntimeError(f"Judge failed without an exception: {last_error}")

    return {
        "portfolio": portfolio["name"],
        "job": job,
        "requirements": [str(item).strip() for item in job["required_skills"] if str(item).strip()],
        "ratings": ratings,
    }


def write_outputs(results: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rating_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for result in sorted(results, key=lambda r: (r["portfolio"], r["job"]["title"], r["job"]["company"])):
        score, counts, rows = score_ratings(result["requirements"], result["ratings"])
        job = result["job"]
        for row in rows:
            rating_rows.append(
                {
                    "portfolio": result["portfolio"],
                    "job_title": job["title"],
                    "job_company": job["company"],
                    "required_skill": row["required_skill"],
                    "label": row["label"],
                    "weight": row["weight"],
                    "evidence_skills": json.dumps(row["evidence_skills"], ensure_ascii=False),
                    "justification": row["justification"],
                }
            )
        summary_rows.append(
            {
                "portfolio": result["portfolio"],
                "job_title": job["title"],
                "job_company": job["company"],
                "n_required_skills": len(result["requirements"]),
                "n_fully_satisfied": counts["fully_satisfied"],
                "n_satisfied": counts["satisfied"],
                "n_partly_satisfied": counts["partly_satisfied"],
                "n_not_satisfied": counts["not_satisfied"],
                "satisfaction_score": f"{score:.4f}",
            }
        )

    with (output_dir / "job_requirement_ratings.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "portfolio",
                "job_title",
                "job_company",
                "required_skill",
                "label",
                "weight",
                "evidence_skills",
                "justification",
            ],
        )
        writer.writeheader()
        writer.writerows(rating_rows)

    with (output_dir / "job_satisfaction_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "portfolio",
                "job_title",
                "job_company",
                "n_required_skills",
                "n_fully_satisfied",
                "n_satisfied",
                "n_partly_satisfied",
                "n_not_satisfied",
                "satisfaction_score",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("evaluation/input/job_fit_inputs.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--family", default="")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--api-key")
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--job-limit", type=int)
    parser.add_argument("--portfolio-only")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--no-response-format", action="store_true")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get(args.api_key_env) or os.environ.get("JUDGE_API_KEY")
    if not api_key:
        raise SystemExit(f"Missing API key. Set {args.api_key_env} or pass --api-key.")

    bundle = load_input_bundle(args.input)
    portfolios = list(bundle["portfolios"])
    jobs = list(bundle["jobs"])
    if args.portfolio_only:
        portfolios = [item for item in portfolios if item["name"] == args.portfolio_only]
    if args.job_limit:
        jobs = jobs[: args.job_limit]
    if not portfolios:
        raise SystemExit("No portfolios selected.")
    if not jobs:
        raise SystemExit("No jobs selected.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "family": args.family,
                "model": args.model,
                "base_url": args.base_url,
                "input": str(args.input),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "n_portfolios": len(portfolios),
                "n_jobs": len(jobs),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tasks = [(portfolio, job) for portfolio in portfolios for job in jobs]
    print(f"Running {len(tasks)} judge calls with model={args.model}")
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(
                rate_pair,
                portfolio=portfolio,
                job=job,
                output_dir=args.output_dir,
                model=args.model,
                family=args.family,
                base_url=args.base_url,
                api_key=api_key,
                max_tokens=args.max_tokens,
                timeout_seconds=args.timeout_seconds,
                retries=args.retries,
                refresh=args.refresh,
                use_response_format=not args.no_response_format,
            )
            for portfolio, job in tasks
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            print(f"progress {index}/{len(tasks)}", flush=True)

    write_outputs(results, args.output_dir)
    print(f"Wrote {args.output_dir / 'job_satisfaction_summary.csv'}")
    print(f"Wrote {args.output_dir / 'job_requirement_ratings.csv'}")


if __name__ == "__main__":
    main()
