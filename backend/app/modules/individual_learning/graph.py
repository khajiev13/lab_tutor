from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class IndividualLearningState(TypedDict, total=False):
    user_id: int
    cv_document_id: int
    profile: dict[str, Any]
    target_titles: list[str]
    candidate_jobs: list[dict[str, Any]]
    skill_bank: list[dict[str, Any]]
    selected_posting_urls: list[str]
    selected_skill_names: list[str]


def review_profile_and_roles(state: IndividualLearningState) -> dict[str, Any]:
    profile = dict(state.get("profile", {}))
    decision = interrupt(
        {
            "kind": "review_profile_and_roles",
            "profile": profile,
            "target_title_suggestions": list(
                profile.get("target_title_suggestions", [])
            ),
        }
    )
    return {
        "profile": dict(decision.get("profile", profile)),
        "target_titles": list(decision.get("target_titles", [])),
        "candidate_jobs": list(decision.get("candidate_jobs", [])),
        "skill_bank": list(decision.get("skill_bank", [])),
    }


def _derive_skill_bank(candidate_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    skill_bank: list[dict[str, Any]] = []
    for job in candidate_jobs:
        for raw_skill in job.get("skills", []):
            name = str(raw_skill.get("name", "")).strip()
            if not name:
                continue
            category = str(raw_skill.get("category", "")).strip()
            description = str(raw_skill.get("description", "")).strip()
            key = (name, category, description)
            if key in seen:
                continue
            seen.add(key)
            skill_bank.append(
                {
                    "name": name,
                    "category": category,
                    "description": description,
                }
            )
    return skill_bank


def load_candidate_jobs(state: IndividualLearningState) -> dict[str, Any]:
    candidate_jobs = list(state.get("candidate_jobs", []))
    skill_bank = list(state.get("skill_bank", [])) or _derive_skill_bank(candidate_jobs)
    return {
        "candidate_jobs": candidate_jobs,
        "skill_bank": skill_bank,
    }


def choose_jobs_and_skills(state: IndividualLearningState) -> dict[str, Any]:
    candidate_jobs = list(state.get("candidate_jobs", []))
    skill_bank = list(state.get("skill_bank", []))
    decision = interrupt(
        {
            "kind": "choose_jobs_and_skills",
            "candidate_jobs": candidate_jobs,
            "skill_bank": skill_bank,
        }
    )
    available_posting_urls = {
        str(job.get("url", "")).strip() for job in candidate_jobs if job.get("url")
    }
    available_skill_names = {
        str(skill.get("name", "")).strip() for skill in skill_bank if skill.get("name")
    }
    selected_posting_urls = [
        url
        for url in decision.get("selected_posting_urls", [])
        if isinstance(url, str)
        and url in available_posting_urls
    ]
    selected_skill_names = [
        name
        for name in decision.get("selected_skill_names", [])
        if isinstance(name, str)
        and name in available_skill_names
    ]
    return {
        "selected_posting_urls": selected_posting_urls,
        "selected_skill_names": selected_skill_names,
    }


def build_individual_learning_graph(checkpointer=None):
    builder = StateGraph(IndividualLearningState)
    builder.add_node("review_profile_and_roles", review_profile_and_roles)
    builder.add_node("search_jobs", load_candidate_jobs)
    builder.add_node("choose_jobs_and_skills", choose_jobs_and_skills)
    builder.add_edge(START, "review_profile_and_roles")
    builder.add_edge("review_profile_and_roles", "search_jobs")
    builder.add_edge("search_jobs", "choose_jobs_and_skills")
    builder.add_edge("choose_jobs_and_skills", END)
    if checkpointer is None:
        checkpointer = InMemorySaver()
    return builder.compile(checkpointer=checkpointer)
