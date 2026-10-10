"""Durable tools carry every confirmed ID through cleaning and final review."""

import json
from uuid import uuid4

from sqlalchemy.orm import Session

from tests.market_skill_fixtures import seed_review


def test_all_covered_mapper_results_reach_linker_with_ids(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    fields = service.load_confirmed_selection(
        course["id"], course["teacher_id"], revision
    )
    with bind_tool_store(
        {**fields, "course_id": course["id"], "teacher_id": course["teacher_id"]}
    ):
        result = tools.save_curriculum_mapping.invoke(
            {
                "mapping_json": json.dumps(
                    [
                        {
                            "candidate_id": candidates[0]["candidate_id"],
                            "name": "Python",
                            "status": "covered",
                            "target_chapter": "Programming",
                            "graph_target_id": "book-1",
                            "origin": "book",
                        }
                    ]
                )
            }
        )
        assert "Saved" in result
        result = tools.finalize_cleaned_skills.invoke({})
        prepared = tools.tool_store.get("selected_for_insertion", [])
        assert len(prepared) == 1, result
        assert prepared[0]["candidate_id"] == candidates[0]["candidate_id"]
        assert prepared[0]["disposition"] == "covered"
        assert (
            prepared[0]["evidence_references"] == candidates[0]["evidence_references"]
        )
        assert prepared[0]["graph_target_id"] == "book-1"


def test_cleaner_merge_preserves_each_candidates_own_evidence(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, labels=("Python", "SQL")
    )
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    fields = service.load_confirmed_selection(
        course["id"], course["teacher_id"], revision
    )
    mapping = [
        {
            "candidate_id": c["candidate_id"],
            "name": c["display_name"],
            "status": "gap",
            "target_chapter": "Programming",
        }
        for c in candidates
    ]
    cleaned = [
        {
            "chapter": "Programming",
            "kept": [candidates[0]["candidate_id"]],
            "dropped": [candidates[1]["candidate_id"]],
            "details": {
                "kept": [{"candidate_id": candidates[0]["candidate_id"]}],
                "dropped": [
                    {
                        "candidate_id": candidates[1]["candidate_id"],
                        "graph_target_id": "book-sql",
                        "origin": "book",
                        "reason": "Same competency",
                    }
                ],
            },
        }
    ]
    with bind_tool_store(
        {
            **fields,
            "course_id": course["id"],
            "teacher_id": course["teacher_id"],
            "curriculum_mapping": mapping,
            "_cleaned_results": cleaned,
        }
    ):
        result = tools.finalize_cleaned_skills.invoke({})
        prepared = tools.tool_store.get("selected_for_insertion", [])
        assert len(prepared) == 2, result
        by_id = {row["candidate_id"]: row for row in prepared}
        assert by_id[candidates[1]["candidate_id"]]["disposition"] == "merged"
        assert (
            by_id[candidates[1]["candidate_id"]]["evidence_references"]
            == candidates[1]["evidence_references"]
        )
        assert by_id[candidates[1]["candidate_id"]]["graph_target_id"] == "book-sql"
        from app.modules.marketdemandanalyst.state import restore_state, snapshot_state

        restore_state(snapshot_state())
        assert "Finalized" in tools.finalize_cleaned_skills.invoke({})
        recovered = tools.tool_store["selected_for_insertion"]
        assert {row["candidate_id"] for row in recovered} == set(by_id)
        assert (
            recovered[1]["evidence_references"] == candidates[1]["evidence_references"]
        )


def test_mapper_cannot_use_stale_confirmation_or_substitute_foreign_id(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    fields = service.load_confirmed_selection(
        course["id"], course["teacher_id"], revision
    )
    with bind_tool_store(
        {**fields, "course_id": course["id"], "teacher_id": course["teacher_id"]}
    ):
        result = tools.save_curriculum_mapping.invoke(
            {
                "mapping_json": json.dumps(
                    [
                        {
                            "candidate_id": str(uuid4()),
                            "name": "Python",
                            "status": "gap",
                            "target_chapter": "Programming",
                        }
                    ]
                )
            }
        )
        assert "candidate_id" in result and not tools.tool_store.get(
            "curriculum_mapping"
        )
        run.selection_confirmation = None
        db_session.commit()
        result = tools.save_curriculum_mapping.invoke(
            {
                "mapping_json": json.dumps(
                    [
                        {
                            "candidate_id": candidates[0]["candidate_id"],
                            "name": "Python",
                            "status": "gap",
                            "target_chapter": "Programming",
                        }
                    ]
                )
            }
        )
        assert "confirm" in result.lower() and not tools.tool_store.get(
            "curriculum_mapping"
        )
