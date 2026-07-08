from __future__ import annotations

from langgraph.types import Command

from app.modules.individual_learning.graph import build_individual_learning_graph


def test_graph_interrupts_for_profile_review() -> None:
    graph = build_individual_learning_graph()
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
    graph = build_individual_learning_graph()
    config = {"configurable": {"thread_id": "individual-7"}}
    graph.invoke(
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

    result = graph.invoke(
        Command(resume={"approved": True, "target_titles": ["Data Analyst"]}),
        config,
    )

    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value["kind"] == "choose_jobs_and_skills"


def test_graph_carries_candidate_jobs_and_skill_bank_from_first_resume() -> None:
    graph = build_individual_learning_graph()
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
                "candidate_jobs": candidate_jobs,
                "skill_bank": skill_bank,
            }
        ),
        config,
    )

    assert "__interrupt__" in result
    interrupt_value = result["__interrupt__"][0].value
    assert interrupt_value["kind"] == "choose_jobs_and_skills"
    assert interrupt_value["candidate_jobs"] == candidate_jobs
    assert interrupt_value["skill_bank"] == skill_bank


def test_graph_filters_selected_jobs_and_skills_against_market_inputs() -> None:
    graph = build_individual_learning_graph()
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
                "candidate_jobs": candidate_jobs,
                "skill_bank": skill_bank,
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


def test_graph_builder_uses_fresh_default_checkpointer_per_build() -> None:
    graph_a = build_individual_learning_graph()
    graph_b = build_individual_learning_graph()

    assert graph_a.checkpointer is not None
    assert graph_b.checkpointer is not None
    assert graph_a.checkpointer is not graph_b.checkpointer
