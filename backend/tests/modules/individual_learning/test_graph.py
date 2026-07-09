from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.modules.individual_learning.graph import build_individual_learning_graph


def test_graph_interrupts_for_profile_review() -> None:
    graph = build_individual_learning_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "individual-7"}}

    result = graph.invoke(
        {
            "user_id": 7,
            "cv_document_id": 3,
            "profile": {"skills": [], "target_title_suggestions": ["Data Analyst"]},
            "target_titles": [],
            "selected_posting_urls": [],
            "selected_skill_names": [],
        },
        config,
    )

    assert "__interrupt__" in result
    interrupt_value = result["__interrupt__"][0].value
    assert interrupt_value["kind"] == "review_profile_and_roles"


def test_graph_resumes_to_skill_selection_interrupt() -> None:
    graph = build_individual_learning_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "individual-7"}}
    candidate_jobs = [
        {
            "url": "https://jobs.example/backend",
            "title": "Backend Engineer",
            "skills": [{"name": "Python", "category": "Programming"}],
        }
    ]
    skill_bank = [
        {
            "name": "Python",
            "category": "Programming",
            "description": "Write backend services",
        }
    ]
    graph.invoke(
        {
            "user_id": 7,
            "cv_document_id": 3,
            "profile": {"skills": [], "target_title_suggestions": ["Data Analyst"]},
            "target_titles": [],
            "candidate_jobs": candidate_jobs,
            "skill_bank": skill_bank,
            "selected_posting_urls": [],
            "selected_skill_names": [],
        },
        config,
    )

    result = graph.invoke(
        Command(resume={"approved": True, "target_titles": ["Data Analyst"]}),
        config,
    )

    assert "__interrupt__" in result
    interrupt_value = result["__interrupt__"][0].value
    assert interrupt_value["kind"] == "choose_jobs_and_skills"
    assert interrupt_value["candidate_jobs"] == candidate_jobs
    assert interrupt_value["skill_bank"] == skill_bank


def test_graph_ignores_resume_payload_attempts_to_override_server_candidate_jobs_and_skill_bank() -> (
    None
):
    graph = build_individual_learning_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "individual-7"}}
    candidate_jobs = [
        {
            "url": "https://jobs.example/backend",
            "title": "Backend Engineer",
            "skills": [{"name": "Python", "category": "Programming"}],
        }
    ]
    skill_bank = [
        {
            "name": "Python",
            "category": "Programming",
            "description": "Write backend services",
        }
    ]
    graph.invoke(
        {
            "user_id": 7,
            "cv_document_id": 3,
            "profile": {"skills": [], "target_title_suggestions": ["Data Analyst"]},
            "target_titles": [],
            "candidate_jobs": candidate_jobs,
            "skill_bank": skill_bank,
            "selected_posting_urls": [],
            "selected_skill_names": [],
        },
        config,
    )

    result = graph.invoke(
        Command(
            resume={
                "approved": True,
                "target_titles": ["Data Analyst"],
                "candidate_jobs": [{"url": "https://jobs.example/injected"}],
                "skill_bank": [{"name": "Injected"}],
            }
        ),
        config,
    )

    assert "__interrupt__" in result
    interrupt_value = result["__interrupt__"][0].value
    assert interrupt_value["kind"] == "choose_jobs_and_skills"
    assert interrupt_value["candidate_jobs"] == candidate_jobs
    assert interrupt_value["skill_bank"] == skill_bank


def test_graph_derives_skill_bank_from_server_candidate_jobs_when_state_has_no_skill_bank() -> (
    None
):
    graph = build_individual_learning_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "individual-7"}}
    candidate_jobs = [
        {
            "url": "https://jobs.example/backend",
            "title": "Backend Engineer",
            "skills": [
                {
                    "name": "Python",
                    "category": "Programming",
                    "description": "Write backend services",
                },
                {
                    "name": "SQL",
                    "category": "Data",
                    "description": "Query relational databases",
                },
            ],
        }
    ]
    graph.invoke(
        {
            "user_id": 7,
            "cv_document_id": 3,
            "profile": {"skills": [], "target_title_suggestions": ["Data Analyst"]},
            "target_titles": [],
            "candidate_jobs": candidate_jobs,
            "skill_bank": [],
            "selected_posting_urls": [],
            "selected_skill_names": [],
        },
        config,
    )

    result = graph.invoke(
        Command(resume={"approved": True, "target_titles": ["Data Analyst"]}),
        config,
    )

    assert "__interrupt__" in result
    interrupt_value = result["__interrupt__"][0].value
    assert interrupt_value["kind"] == "choose_jobs_and_skills"
    assert interrupt_value["candidate_jobs"] == candidate_jobs
    assert interrupt_value["skill_bank"] == [
        {
            "name": "Python",
            "category": "Programming",
            "description": "Write backend services",
        },
        {
            "name": "SQL",
            "category": "Data",
            "description": "Query relational databases",
        },
    ]


def test_graph_filters_selected_jobs_and_skills_against_market_inputs() -> None:
    graph = build_individual_learning_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "individual-7"}}
    candidate_jobs = [
        {
            "url": "https://jobs.example/backend",
            "title": "Backend Engineer",
            "skills": [{"name": "Python", "category": "Programming"}],
        }
    ]
    skill_bank = [
        {
            "name": "Python",
            "category": "Programming",
            "description": "Write backend services",
        }
    ]
    graph.invoke(
        {
            "user_id": 7,
            "cv_document_id": 3,
            "profile": {"skills": [], "target_title_suggestions": ["Data Analyst"]},
            "target_titles": [],
            "candidate_jobs": candidate_jobs,
            "skill_bank": skill_bank,
            "selected_posting_urls": [],
            "selected_skill_names": [],
        },
        config,
    )
    graph.invoke(
        Command(
            resume={
                "approved": True,
                "target_titles": ["Data Analyst"],
            }
        ),
        config,
    )

    result = graph.invoke(
        Command(
            resume={
                "selected_posting_urls": [
                    "https://jobs.example/backend",
                    "https://jobs.example/other",
                ],
                "selected_skill_names": ["Python", "Excel"],
            }
        ),
        config,
    )

    assert "__interrupt__" not in result
    assert result["selected_posting_urls"] == ["https://jobs.example/backend"]
    assert result["selected_skill_names"] == ["Python"]


def test_graph_builder_requires_explicit_checkpointer() -> None:
    with pytest.raises(ValueError, match="checkpointer is required"):
        build_individual_learning_graph()
