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
