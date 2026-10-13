"""Actual source coordinator and HTTP configuration with real PostgreSQL."""

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pandas as pd
import pytest
from sqlalchemy import select

from app.modules.marketdemandanalyst.state import bind_tool_store


def owned_run(db_session, client, teacher_auth_headers, config=None):
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    course = client.post(
        "/courses", json={"title": "Orchestration"}, headers=teacher_auth_headers
    ).json()
    run = MarketReviewRepository(db_session).create_run(
        course["id"],
        course["teacher_id"],
        config
        or {
            "country": "Uzbekistan",
            "sources": ["linkedin"],
            "evidence_sources": ["jobs"],
        },
    )
    db_session.commit()
    return course, run


def test_coordinator_persists_short_and_long_full_records_before_filter(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot
    from app.modules.marketdemandanalyst.service import MarketSourceService

    course, run = owned_run(db_session, client, teacher_auth_headers)

    def scraper(**kwargs):
        return pd.DataFrame(
            [
                {
                    "id": str(i),
                    "title": "Same",
                    "company": "Same",
                    "description": text,
                    "job_url": f"https://www.linkedin.com/jobs/view/{i}",
                }
                for i, text in enumerate(["x", "Python " * 1000])
            ]
        )

    svc = MarketSourceService(
        jobs=JobSourceService(jobspy_scraper=scraper),
        session_factory=lambda: db_session,
    )
    result = svc.collect_sources(
        {
            "run_id": str(run.id),
            "course_id": course["id"],
            "teacher_id": course["teacher_id"],
            **run.config,
        },
        ["Python"],
    )
    snapshots = list(db_session.scalars(select(MarketVacancySnapshot)))
    assert len(snapshots) == 2
    assert sorted(len(s.description_text) for s in snapshots) == [1, 7000]
    assert len(result["jobs"]) == 1 and result["jobs"][0]["snapshot_id"]
    assert result["source_outcomes"]["linkedin"]["received_count"] == 2


def test_onet_only_never_activates_provider_and_yields_missing_job_support(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.service import MarketSourceService
    from app.modules.occupation_reference.service import OccupationReferenceService

    course, run = owned_run(
        db_session,
        client,
        teacher_auth_headers,
        {
            "country": "Uzbekistan",
            "sources": [],
            "evidence_sources": ["onet"],
            "onet_release": "31.0",
            "onet_selection_confirmed": True,
            "selected_onet_occupations": [{"soc_code": "15-1252.00"}],
        },
    )
    evidence = {
        "id": str(run.id),
        "label": "Programming",
        "family": "transferable",
        "soc_code": "15-1252.00",
        "ratings": {"IM": {"value": 4, "status": "reported"}},
        "release": "31.0",
    }
    monkeypatch.setattr(
        OccupationReferenceService, "get_skill_evidence", lambda *args: [evidence]
    )

    def forbidden(**kwargs):
        raise AssertionError("provider must not run")

    svc = MarketSourceService(
        jobs=JobSourceService(jobspy_scraper=forbidden),
        session_factory=lambda: db_session,
    )
    result = svc.collect_sources(
        {
            "run_id": str(run.id),
            "course_id": course["id"],
            "teacher_id": course["teacher_id"],
            **run.config,
        },
        [],
    )
    assert not result["jobs"]
    assert set(result["source_outcomes"]) == {"onet"}
    assert result["candidates"][0]["posting_support"] == "missing"
    assert (
        result["candidates"][0]["onet_associations"][0]["evidence"]["ratings"]["IM"][
            "value"
        ]
        == 4
    )


def test_production_fetch_tool_uses_config_selected_provider(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.service import MarketSourceService

    course, run = owned_run(db_session, client, teacher_auth_headers)

    def scraper(**kwargs):
        assert kwargs["site_name"] == ["linkedin"]
        assert "country_indeed" not in kwargs
        return pd.DataFrame(
            [
                {
                    "id": "10",
                    "title": "Engineer",
                    "description": "Python " * 1000,
                    "job_url": "https://www.linkedin.com/jobs/view/10",
                }
            ]
        )

    svc = MarketSourceService(
        jobs=JobSourceService(jobspy_scraper=scraper),
        session_factory=lambda: db_session,
    )
    monkeypatch.setattr(tools, "get_market_source_service", lambda: svc)
    state = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        "job_search_country": "Uzbekistan",
        "job_search_country_confirmed": True,
        **run.config,
    }
    with bind_tool_store(state):
        result = tools.fetch_jobs.invoke({"search_terms": "Python"})
    assert "1" in result
    assert state["fetched_jobs"][0]["snapshot_id"]
    assert len(state["fetched_jobs"][0]["description"]) == 7000


def test_chat_applies_and_locks_explicit_sources(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun

    graph = AsyncMock()

    async def stream(*args, **kwargs):
        if False:
            yield None

    graph.astream = stream
    course = client.post(
        "/courses", json={"title": "Config"}, headers=teacher_auth_headers
    ).json()
    url = f"/courses/{course['id']}/market-demand/chat"
    with patch(
        "app.modules.marketdemandanalyst.routes.get_graph", return_value=(graph, None)
    ):
        response = client.post(
            url,
            json={
                "country": "Uzbekistan",
                "sources": ["linkedin"],
                "evidence_sources": ["jobs"],
            },
            headers=teacher_auth_headers,
        )
        assert response.status_code == 200
        run = db_session.scalar(select(MarketAnalysisRun))
        assert run.config["sources"] == ["linkedin"]
        assert run.config["country"] == "Uzbekistan"
        run.source_outcomes = {"linkedin": {"status": "empty", "received_count": 0}}
        db_session.commit()
        response = client.post(
            url,
            json={"country": "USA", "sources": ["indeed"]},
            headers=teacher_auth_headers,
        )
        assert response.status_code == 409
        db_session.expire_all()
        assert run.config["sources"] == ["linkedin"]


def test_model_cannot_publish_new_run_before_teacher_final_approval(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.review_service import SkillReviewService
    from app.modules.marketdemandanalyst.tools import insert_market_skills_to_neo4j

    course, run = owned_run(db_session, client, teacher_auth_headers)
    repo = MarketReviewRepository(db_session)
    repo.save_configuration_snapshot(
        SkillReviewService.thread_id(course["id"], course["teacher_id"]),
        {"run_id": str(run.id)},
    )
    db_session.commit()
    with bind_tool_store(
        {
            "run_id": str(run.id),
            "selected_for_insertion": [{"name": "Programming"}],
            "course_id": course["id"],
            "teacher_id": course["teacher_id"],
        }
    ):
        result = insert_market_skills_to_neo4j.invoke({})
    assert "approval" in result.lower()
    db_session.refresh(run)
    assert run.publication_revision == 0
    assert run.approved_references == []


def test_purge_refetch_never_sends_erased_content_to_extraction(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.service import MarketSourceService

    course, run = owned_run(db_session, client, teacher_auth_headers)

    def scraper(**kwargs):
        return pd.DataFrame(
            [
                {
                    "id": "10",
                    "title": "Engineer",
                    "description": "Python " * 1000,
                    "job_url": "https://www.linkedin.com/jobs/view/10",
                }
            ]
        )

    svc = MarketSourceService(
        jobs=JobSourceService(jobspy_scraper=scraper),
        session_factory=lambda: db_session,
    )
    config = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        **run.config,
    }
    first = svc.collect_sources(config, ["Python"])
    repo = MarketReviewRepository(db_session)
    repo.purge_vacancy_content(
        UUID(first["jobs"][0]["snapshot_id"]), reason="provider_removal"
    )
    db_session.commit()
    second = svc.collect_sources(config, ["Python"])
    assert second["jobs"] == []
    assert db_session.scalar(select(MarketVacancySnapshot)).description_text is None
    from app.modules.marketdemandanalyst import extractor, tools

    monkeypatch.setattr(tools, "get_market_source_service", lambda: svc)
    monkeypatch.setattr(
        extractor,
        "_get_extraction_llm",
        lambda **kwargs: pytest.fail("Purged content reached LLM"),
    )
    state = {
        **config,
        "job_search_country": "Uzbekistan",
        "job_search_country_confirmed": True,
        "selected_jobs": first["jobs"],
    }
    with bind_tool_store(state):
        tools.fetch_jobs.invoke({"search_terms": "Python"})
        tools.start_extraction.invoke({})
    assert state["fetched_jobs"] == [] and state["selected_jobs"] == []


@pytest.mark.parametrize("autoflush", [True, False])
def test_mixed_sources_overlap_before_coordinator_commit(
    db_session, client, teacher_auth_headers, monkeypatch, autoflush
):
    from threading import Barrier

    from sqlalchemy.orm import sessionmaker

    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.service import MarketSourceService
    from app.modules.occupation_reference.service import OccupationReferenceService

    barrier = Barrier(2, timeout=8)
    config = {
        "country": "Uzbekistan",
        "sources": ["linkedin"],
        "evidence_sources": ["jobs", "onet"],
        "onet_release": "31.0",
        "onet_selection_confirmed": True,
        "selected_onet_occupations": [{"soc_code": "15-1252.00"}],
    }
    course, run = owned_run(db_session, client, teacher_auth_headers, config)

    def scrape(**kwargs):
        barrier.wait()
        return pd.DataFrame(
            [
                {
                    "id": "10",
                    "title": "Engineer",
                    "description": "Python " * 20,
                    "job_url": "https://www.linkedin.com/jobs/view/10",
                }
            ]
        )

    def lookup(*args):
        barrier.wait()
        return [
            {
                "id": str(run.id),
                "label": "Programming",
                "family": "transferable",
                "soc_code": "15-1252.00",
                "ratings": {},
                "release": "31.0",
            }
        ]

    monkeypatch.setattr(OccupationReferenceService, "get_skill_evidence", lookup)
    svc = MarketSourceService(
        jobs=JobSourceService(jobspy_scraper=scrape),
        session_factory=sessionmaker(bind=db_session.get_bind(), autoflush=autoflush),
    )
    result = svc.collect_sources(
        {
            "run_id": str(run.id),
            "course_id": course["id"],
            "teacher_id": course["teacher_id"],
            **config,
        },
        ["Python"],
    )
    assert result["source_outcomes"]["linkedin"]["status"] == "success"
    assert result["source_outcomes"]["onet"]["status"] == "success"
    assert result["candidates"][0]["posting_support"] == "missing"

    from app.modules.marketdemandanalyst.repository import MarketReviewRepository

    with sessionmaker(bind=db_session.get_bind(), autoflush=False)() as readback:
        stored = MarketReviewRepository(readback).get_run(
            run.id, course["id"], course["teacher_id"]
        )
        assert stored is not None
        assert stored.source_outcomes == result["source_outcomes"]
        assert stored.candidate_revision == result["candidate_revision"]


def test_source_failure_requires_exact_ack_and_never_waives_posting_support(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.service import (
        MarketSourceService,
        available_evidence_omissions,
    )

    course, run = owned_run(db_session, client, teacher_auth_headers)
    run.source_outcomes = {"linkedin": {"status": "error", "received_count": 0}}
    run.candidate_manifest = {"candidates": []}
    db_session.commit()
    svc = MarketSourceService(
        jobs=JobSourceService(), session_factory=lambda: db_session
    )
    state = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
    }
    with pytest.raises(ValueError, match="Continue"):
        svc.require_available_evidence(state)
    run = MarketReviewRepository(db_session).get_run(
        UUID(state["run_id"]), course["id"], course["teacher_id"]
    )
    run.candidate_manifest = {
        "candidates": [],
        "acknowledged_omissions": available_evidence_omissions(run),
    }
    db_session.commit()
    svc.require_available_evidence(state)
    assert not run.candidate_manifest["candidates"]


def test_actual_extraction_subgraph_commits_distinct_support_and_keeps_exclusion(
    db_session, client, teacher_auth_headers, monkeypatch
):
    import asyncio
    import json
    from types import SimpleNamespace

    from langgraph.graph import END, START, StateGraph
    from sqlalchemy.orm import sessionmaker

    from app.modules.marketdemandanalyst import extractor
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.service import MarketSourceService

    course, run = owned_run(db_session, client, teacher_auth_headers)

    def scrape(**kwargs):
        return pd.DataFrame(
            [
                {
                    "id": str(i),
                    "title": "Engineer",
                    "description": "a" * 4300 + " Explain results to stakeholders.",
                    "job_url": f"https://www.linkedin.com/jobs/view/{i}",
                }
                for i in [10, 11]
            ]
        )

    svc = MarketSourceService(
        jobs=JobSourceService(jobspy_scraper=scrape),
        session_factory=sessionmaker(bind=db_session.get_bind()),
    )
    config = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        **run.config,
    }
    fetched = svc.collect_sources(config, ["Engineer"])

    class LLM:
        def invoke(self, prompt, **kwargs):
            rows = (
                [
                    {
                        "name": "Explain results",
                        "category": "communication",
                        "original_phrase": "Explain results",
                        "excerpt": "Explain results to stakeholders",
                    }
                ]
                if "stakeholders" in prompt
                else []
            )
            return SimpleNamespace(content=json.dumps(rows + rows))

    monkeypatch.setattr(extractor, "_get_extraction_llm", lambda **kwargs: LLM())
    import app.modules.marketdemandanalyst.service as service_module

    monkeypatch.setattr(service_module, "get_market_source_service", lambda: svc)
    parent = StateGraph(extractor.ExtractorState)
    parent.add_node("skill_extractor", extractor.skill_extractor_subgraph)
    parent.add_node("skill_finder", lambda state: {})
    parent.add_edge(START, "skill_extractor")
    parent.add_edge("skill_finder", END)
    graph = parent.compile()
    state = {**config, "selected_jobs": fetched["jobs"]}
    with bind_tool_store(state):
        asyncio.run(graph.ainvoke({"skills": [], "assessments": []}))
    db_session.expire_all()
    run = MarketReviewRepository(db_session).get_run(
        UUID(config["run_id"]), course["id"], course["teacher_id"]
    )
    candidate = run.candidate_manifest["candidates"][0]
    assert candidate["job_metrics"] == {
        "supporting_posting_count": 2,
        "assessed_posting_count": 2,
        "selected_posting_count": 2,
        "percentage": 100.0,
        "coverage_status": "full",
    }
    assert len(candidate["evidence_references"]) == 2
    assert all(ref["excerpt_start"] == 4301 for ref in candidate["evidence_references"])
    candidate_id = candidate["candidate_id"]
    run.excluded_candidate_ids = [candidate_id]
    db_session.commit()
    with bind_tool_store(state):
        asyncio.run(graph.ainvoke({"skills": [], "assessments": []}))
    db_session.expire_all()
    run = MarketReviewRepository(db_session).get_run(
        UUID(config["run_id"]), course["id"], course["teacher_id"]
    )
    assert run.candidate_manifest["candidates"][0]["candidate_id"] == candidate_id
    assert run.excluded_candidate_ids == [candidate_id]


def test_onet_only_fetch_does_not_require_country_confirmation(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.service import MarketSourceService
    from app.modules.occupation_reference.service import OccupationReferenceService

    config = {
        "country": "USA",
        "sources": [],
        "evidence_sources": ["onet"],
        "onet_release": "31.0",
        "onet_selection_confirmed": True,
        "selected_onet_occupations": [{"soc_code": "15-1252.00"}],
    }
    course, run = owned_run(db_session, client, teacher_auth_headers, config)
    monkeypatch.setattr(
        OccupationReferenceService,
        "get_skill_evidence",
        lambda *args: [
            {
                "id": str(run.id),
                "label": "Programming",
                "family": "transferable",
                "soc_code": "15-1252.00",
                "ratings": {},
                "release": "31.0",
            }
        ],
    )
    svc = MarketSourceService(
        jobs=JobSourceService(
            jobspy_scraper=lambda **kwargs: pytest.fail("unselected provider")
        ),
        session_factory=lambda: db_session,
    )
    monkeypatch.setattr(tools, "get_market_source_service", lambda: svc)
    state = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        "evidence_sources": ["onet"],
    }
    with bind_tool_store(state):
        tools.fetch_jobs.invoke({"search_terms": ""})
    assert state["extracted_skills"][0]["posting_support"] == "missing"


def test_partial_extraction_can_retry_without_acknowledging_failed_extraction(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from langgraph.types import Command

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.service import MarketSourceService

    course, run = owned_run(db_session, client, teacher_auth_headers)
    run.extraction_coverage = {
        "status": "partial",
        "warnings": ["one chunk failed"],
        "acknowledged": False,
    }
    db_session.commit()
    svc = MarketSourceService(session_factory=lambda: db_session)
    monkeypatch.setattr(tools, "get_market_source_service", lambda: svc)
    state = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        "selected_jobs": [{"snapshot_id": str(run.id)}],
        "extracted_skills": [{"name": "Explain results"}],
        "extraction_coverage": {"status": "partial"},
    }
    with bind_tool_store(state):
        result = tools.start_extraction.invoke({})
    assert isinstance(result, Command) and result.goto == "skill_extractor"


@pytest.mark.parametrize("sibling_order", [None, "before", "after"])
def test_extraction_handoff_returns_completed_tool_history_to_skill_finder(
    db_session, client, teacher_auth_headers, monkeypatch, sibling_order
):
    import json
    from types import SimpleNamespace

    from langchain.tools import tool
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langgraph.graph import START, StateGraph
    from langgraph.prebuilt import create_react_agent
    from langgraph_swarm import SwarmState
    from sqlalchemy.orm import sessionmaker

    import app.modules.marketdemandanalyst.service as service_module
    from app.modules.marketdemandanalyst import extractor, tools
    from app.modules.marketdemandanalyst.graph import _make_prompt
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.prompts import SKILL_FINDER_PROMPT
    from app.modules.marketdemandanalyst.service import MarketSourceService
    from tests.modules.test_market_workspace_chat import ScriptedModel

    course, run = owned_run(db_session, client, teacher_auth_headers)
    svc = MarketSourceService(
        jobs=JobSourceService(
            jobspy_scraper=lambda **kwargs: pd.DataFrame(
                [
                    {
                        "id": "completed-extraction",
                        "title": "Engineer",
                        "description": "Explain results to stakeholders. " * 10,
                        "job_url": "https://www.linkedin.com/jobs/view/completed-extraction",
                    }
                ]
            )
        ),
        session_factory=sessionmaker(bind=db_session.get_bind()),
    )
    config = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        **run.config,
    }
    fetched = svc.collect_sources(config, ["Engineer"])
    monkeypatch.setattr(tools, "get_market_source_service", lambda: svc)
    monkeypatch.setattr(service_module, "get_market_source_service", lambda: svc)
    monkeypatch.setattr(
        extractor,
        "_get_extraction_llm",
        lambda **kwargs: SimpleNamespace(
            invoke=lambda *args, **kw: SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "name": "Explain results",
                            "category": "communication",
                            "original_phrase": "Explain results",
                            "excerpt": "Explain results to stakeholders",
                        }
                    ]
                )
            )
        ),
    )

    @tool
    def read_only_probe() -> str:
        """Inspect a read-only value while checking the extraction handoff."""
        return "The original read-only value is preserved."

    extraction_call = {
        "name": "start_extraction",
        "args": {},
        "id": "completed-extraction",
    }
    sibling_call = {"name": "read_only_probe", "args": {}, "id": "read-only-call"}
    calls = [extraction_call]
    if sibling_order:
        calls = (
            [sibling_call, extraction_call]
            if sibling_order == "before"
            else [extraction_call, sibling_call]
        )
    replies = [AIMessage(content="", tool_calls=calls)]
    completion_id = "completed-extraction"
    if sibling_order:
        completion_id = "completed-extraction-alone"
        replies.append(
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "start_extraction", "args": {}, "id": completion_id}
                ],
            )
        )
    replies.append(
        AIMessage(content="The assessed candidates are ready for teacher review.")
    )
    model = ScriptedModel(replies=replies)
    finder = create_react_agent(
        model,
        tools=tools.owned_sync_tools([tools.start_extraction, read_only_probe]),
        prompt=_make_prompt(SKILL_FINDER_PROMPT),
        name="skill_finder",
    )
    parent = StateGraph(SwarmState)
    parent.add_node("skill_finder", finder)
    parent.add_node("skill_extractor", extractor.skill_extractor_subgraph)
    parent.add_edge(START, "skill_finder")
    state = {**config, "selected_jobs": fetched["jobs"]}
    with bind_tool_store(state):
        client.portal.call(
            parent.compile().ainvoke,
            {
                "messages": [HumanMessage(content="Extract the approved job group.")],
                "active_agent": "skill_finder",
            },
        )

    resumed_messages = model.calls[-1][0]
    assert any(
        isinstance(message, AIMessage)
        and any(call["id"] == completion_id for call in message.tool_calls)
        for message in resumed_messages
    ), "Extraction handoff lost the original tool request"
    assert any(
        isinstance(message, ToolMessage)
        and message.tool_call_id == completion_id
        and message.status == "success"
        for message in resumed_messages
    ), "Skill Finder did not receive extraction completion"
    if sibling_order:
        assert [
            message.content
            for message in resumed_messages
            if isinstance(message, ToolMessage)
            and message.tool_call_id == "read-only-call"
        ] == ["The original read-only value is preserved."]
        assert any(
            isinstance(message, ToolMessage)
            and message.tool_call_id == "completed-extraction"
            and message.status == "error"
            for message in resumed_messages
        ), "The bundled extraction must be rejected before handing off"
    assert state["extraction_coverage"]["assessed_postings"] == 1


def test_id_pass_through_mapping_retains_exact_candidate_evidence(
    db_session, client, teacher_auth_headers, monkeypatch
):
    import json

    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from tests.market_skill_fixtures import seed_review

    course, _, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, labels=("Explain results",)
    )
    candidate = candidates[0]
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    fields = service.load_confirmed_selection(
        course["id"], course["teacher_id"], revision
    )
    state = {
        **fields,
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
    }
    with bind_tool_store(state):
        result = tools.save_curriculum_mapping.invoke(
            {
                "mapping_json": json.dumps(
                    [
                        {
                            "candidate_id": candidate["candidate_id"],
                            "name": "Explain results",
                            "status": "covered",
                            "category": candidate["category_id"],
                        }
                    ]
                )
            }
        )
    assert "Saved" in result
    assert (
        state["curriculum_mapping"][0]["evidence_references"]
        == candidate["evidence_references"]
    )
    assert state["curriculum_mapping"][0]["candidate_id"] == candidate["candidate_id"]


def test_refetch_reconciles_purged_candidate_support(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.service import MarketSourceService

    course, run = owned_run(db_session, client, teacher_auth_headers)
    config = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        **run.config,
    }

    def scrape(**kwargs):
        return pd.DataFrame(
            [
                {
                    "id": "10",
                    "title": "Engineer",
                    "description": "Python " * 20,
                    "job_url": "https://www.linkedin.com/jobs/view/10",
                }
            ]
        )

    svc = MarketSourceService(
        jobs=JobSourceService(jobspy_scraper=scrape), session_factory=lambda: db_session
    )
    fetched = svc.collect_sources(config, ["Python"])
    job = fetched["jobs"][0]
    ref = {
        "snapshot_id": job["snapshot_id"],
        "original_url": job["url"],
        "provider": "linkedin",
        "evidence_kind": "extracted_text",
        "original_phrase": "Python",
        "excerpt": "Python",
        "excerpt_start": 0,
        "excerpt_end": 6,
    }
    assessment = {
        "snapshot_id": job["snapshot_id"],
        "demand_identity": job["demand_identity"],
        "status": "full",
        "total_chunks": 1,
        "assessed_chunks": 1,
        "warnings": [],
    }
    draft = svc.save_extraction(
        config,
        [
            {
                "name": "Use Python",
                "category": "language",
                "identity_key": "python",
                "evidence_references": [ref],
            }
        ],
        [assessment],
    )
    candidate_id = draft["candidates"][0]["candidate_id"]
    MarketReviewRepository(db_session).purge_vacancy_content(
        UUID(job["snapshot_id"]), reason="provider_removal"
    )
    db_session.commit()
    result = svc.collect_sources(config, ["Python"])
    assert result["jobs"] == []
    assert result["candidates"][0]["candidate_id"] == candidate_id
    assert result["candidates"][0]["posting_support"] == "missing"
    assert result["candidates"][0]["evidence_references"] == []
    assert result["source_outcomes"]["linkedin"]["received_count"] == 1
    assert result["source_outcomes"]["linkedin"]["usable_count"] == 0


@pytest.mark.parametrize("retry", [False, True])
def test_cached_selection_purged_before_start_or_retry_never_calls_model(
    db_session, client, teacher_auth_headers, monkeypatch, retry
):
    import asyncio

    from langgraph.graph import END, START, StateGraph
    from sqlalchemy.orm import sessionmaker

    import app.modules.marketdemandanalyst.service as service_module
    from app.modules.marketdemandanalyst import extractor, tools
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.service import MarketSourceService

    course, run = owned_run(db_session, client, teacher_auth_headers)
    svc = MarketSourceService(
        jobs=JobSourceService(
            jobspy_scraper=lambda **kwargs: pd.DataFrame(
                [
                    {
                        "id": "cached",
                        "title": "Engineer",
                        "description": "Private retained text " * 20,
                        "job_url": "https://www.linkedin.com/jobs/view/cached",
                    }
                ]
            )
        ),
        session_factory=sessionmaker(bind=db_session.get_bind()),
    )
    config = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        **run.config,
    }
    fetched = svc.collect_sources(config, ["Engineer"])
    MarketReviewRepository(db_session).purge_vacancy_content(
        UUID(fetched["jobs"][0]["snapshot_id"]), reason="provider content removed"
    )
    db_session.commit()
    monkeypatch.setattr(tools, "get_market_source_service", lambda: svc)
    monkeypatch.setattr(service_module, "get_market_source_service", lambda: svc)
    monkeypatch.setattr(
        extractor,
        "_get_extraction_llm",
        lambda **kwargs: pytest.fail("Purged cached text reached model"),
    )
    parent = StateGraph(extractor.ExtractorState)
    parent.add_node("skill_extractor", extractor.skill_extractor_subgraph)
    parent.add_node("skill_finder", lambda state: {})
    parent.add_edge(START, "skill_extractor")
    parent.add_edge("skill_finder", END)
    graph = parent.compile()
    state = {**config, "selected_jobs": fetched["jobs"]}
    if retry:
        state["extracted_skills"] = [{"name": "Previous skill"}]
    with bind_tool_store(state):
        tools.start_extraction.invoke({})
        asyncio.run(graph.ainvoke({"skills": [], "assessments": []}))
    assert state["selected_jobs"] == []
    db_session.expire_all()
    run = MarketReviewRepository(db_session).get_run(
        UUID(config["run_id"]), course["id"], course["teacher_id"]
    )
    assert run.extraction_coverage["selected_postings"] == 1
    assert run.extraction_coverage["assessed_postings"] == 0
    assert run.extraction_coverage["status"] == "failed"


def test_failed_chat_snapshot_write_rolls_back_run_config_and_active_pointer(
    db_session, client, teacher_auth_headers
):
    from copy import deepcopy

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState

    graph = AsyncMock()

    async def stream(*args, **kwargs):
        if False:
            yield None

    graph.astream = stream
    course = client.post(
        "/courses", json={"title": "Atomic config"}, headers=teacher_auth_headers
    ).json()
    path = f"/courses/{course['id']}/market-demand/chat"
    with patch(
        "app.modules.marketdemandanalyst.routes.get_graph", return_value=(graph, None)
    ):
        assert (
            client.post(path, json={}, headers=teacher_auth_headers).status_code == 200
        )
        run = db_session.scalar(select(MarketAnalysisRun))
        initial_config = deepcopy(run.config)
        initial_state = deepcopy(db_session.scalar(select(MDAThreadState)).state_json)
        db_session.execute(
            text(
                "ALTER TABLE mda_thread_state ADD CONSTRAINT task4_reject_config_snapshot CHECK ((state_json -> 'sources') IS DISTINCT FROM '[\"linkedin\"]'::jsonb)"
            )
        )
        db_session.commit()
        try:
            with pytest.raises(IntegrityError):
                client.post(
                    path,
                    json={"country": "Uzbekistan", "sources": ["linkedin"]},
                    headers=teacher_auth_headers,
                )
            db_session.rollback()
            db_session.expire_all()
            assert db_session.get(MarketAnalysisRun, run.id).config == initial_config
            assert db_session.scalar(select(MDAThreadState)).state_json == initial_state
        finally:
            db_session.rollback()
            db_session.execute(
                text(
                    "ALTER TABLE mda_thread_state DROP CONSTRAINT task4_reject_config_snapshot"
                )
            )
            db_session.commit()


@pytest.mark.anyio
async def test_cancelled_snapshot_hydration_drains_before_final_state_capture(
    db_session, client, teacher_auth_headers, monkeypatch
):
    import asyncio
    import threading

    from langgraph.graph import END, START, StateGraph
    from sqlalchemy.orm import sessionmaker

    import app.modules.marketdemandanalyst.service as service_module
    from app.modules.marketdemandanalyst import extractor
    from app.modules.marketdemandanalyst.job_sources import JobSourceService
    from app.modules.marketdemandanalyst.repository import MarketReviewRepository
    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.service import MarketSourceService
    from app.modules.marketdemandanalyst.thread_state_service import (
        ThreadBusy,
        ThreadStateService,
    )

    course, run = owned_run(db_session, client, teacher_auth_headers)
    svc = MarketSourceService(
        jobs=JobSourceService(
            jobspy_scraper=lambda **kwargs: pd.DataFrame(
                [
                    {
                        "id": "late",
                        "title": "Engineer",
                        "description": "Private retained text " * 20,
                        "job_url": "https://www.linkedin.com/jobs/view/late",
                    }
                ]
            )
        ),
        session_factory=sessionmaker(bind=db_session.get_bind()),
    )
    config = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        **run.config,
    }
    fetched = svc.collect_sources(config, ["Engineer"])
    MarketReviewRepository(db_session).purge_vacancy_content(
        UUID(fetched["jobs"][0]["snapshot_id"]), reason="provider content removed"
    )
    db_session.commit()
    entered, proceed, completed, captured_early = (threading.Event() for _ in range(4))
    cancelled = asyncio.Event()
    prepare = svc.prepare_extraction_jobs

    def delayed_prepare(*args):
        entered.set()
        assert proceed.wait(5)
        try:
            return prepare(*args)
        finally:
            completed.set()

    monkeypatch.setattr(svc, "prepare_extraction_jobs", delayed_prepare)
    monkeypatch.setattr(service_module, "get_market_source_service", lambda: svc)
    monkeypatch.setattr(
        extractor,
        "_get_extraction_llm",
        lambda **kwargs: pytest.fail("Purged text reached model"),
    )
    parent = StateGraph(extractor.ExtractorState)
    parent.add_node("skill_extractor", extractor.skill_extractor_subgraph)
    parent.add_node("skill_finder", lambda state: {})
    parent.add_edge(START, "skill_extractor")
    parent.add_edge("skill_finder", END)
    compiled = parent.compile()

    class ObservedGraph:
        async def astream(self, *args, **kwargs):
            try:
                async for item in compiled.astream(*args, **kwargs):
                    yield item
            except asyncio.CancelledError:
                cancelled.set()
                raise

    service = ThreadStateService()
    save = service.save

    def observed_save(lease, snapshot):
        if not completed.is_set():
            captured_early.set()
        return save(lease, snapshot)

    monkeypatch.setattr(service, "save", observed_save)
    lease = await service.claim("cancelled-snapshot-hydration")
    stream = _sse_stream(
        ObservedGraph(),
        {"skills": [], "assessments": []},
        {"configurable": {"thread_id": lease.thread_id}},
        bound_state={
            **config,
            "selected_jobs": fetched["jobs"],
            "fetched_jobs": fetched["jobs"],
        },
        lease=lease,
        state_service=service,
    )

    async def consume():
        async for _ in stream:
            pass

    consumer = asyncio.create_task(consume())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        lease.producer.cancel()
        await asyncio.wait_for(cancelled.wait(), 3)
        assert not await asyncio.to_thread(captured_early.wait, 0.5), (
            "Final state captured before actual hydration finished"
        )
        with pytest.raises(ThreadBusy):
            await ThreadStateService().claim(lease.thread_id)
        proceed.set()
        await asyncio.wait_for(lease.finished.wait(), 5)
        restored = await service.load(lease.thread_id)
        assert restored["selected_jobs"] == []
        assert restored["fetched_jobs"] == []
    finally:
        proceed.set()
        await asyncio.wait_for(lease.finished.wait(), 5)
        await asyncio.wait_for(consumer, 5)
        assert await asyncio.to_thread(completed.wait, 3)


def test_chat_validates_pending_onet_enable_and_same_soc_release_change(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState
    from app.modules.occupation_reference.models import OnetOccupation, OnetRelease

    for release in ("30.0", "31.0"):
        db_session.add(OnetRelease(version=release, manifest={}, attribution="O*NET"))
        db_session.flush()
        db_session.add(
            OnetOccupation(
                release=release,
                soc_code="15-2051.00",
                title=f"Data Scientists {release}",
                description=f"Description {release}",
            )
        )
    db_session.commit()
    graph = AsyncMock()

    async def stream(*args, **kwargs):
        if False:
            yield None

    graph.astream = stream
    course = client.post(
        "/courses",
        json={"title": "Pending configuration"},
        headers=teacher_auth_headers,
    ).json()
    url = f"/courses/{course['id']}/market-demand/chat"
    with patch(
        "app.modules.marketdemandanalyst.routes.get_graph", return_value=(graph, None)
    ):
        response = client.post(
            url,
            json={
                "country": "Uzbekistan",
                "sources": ["linkedin"],
                "evidence_sources": ["jobs"],
            },
            headers=teacher_auth_headers,
        )
        assert response.status_code == 200
        run = db_session.scalar(select(MarketAnalysisRun))
        original_run_id = run.id
        for release in ("30.0", "31.0"):
            response = client.post(
                url,
                json={
                    "sources": ["linkedin"],
                    "evidence_sources": ["jobs", "onet"],
                    "onet_release": release,
                    "onet_occupation_codes": ["15-2051.00"],
                },
                headers=teacher_auth_headers,
            )
            assert response.status_code == 200
            db_session.expire_all()
            assert run.id == original_run_id
            assert run.config["onet_release"] == release
            assert run.config["onet_selection_confirmed"]
            assert run.config["selected_onet_occupations"] == [
                {
                    "soc_code": "15-2051.00",
                    "title": f"Data Scientists {release}",
                    "description": f"Description {release}",
                }
            ]
        durable = dict(run.config)
        snapshot = db_session.scalar(select(MDAThreadState)).state_json.copy()
        # Same SOC must be checked in the new release, not carried from 31.0.
        db_session.add(OnetRelease(version="32.0", manifest={}, attribution="O*NET"))
        db_session.commit()
        response = client.post(
            url,
            json={"onet_release": "32.0", "onet_occupation_codes": ["15-2051.00"]},
            headers=teacher_auth_headers,
        )
        assert response.status_code == 422
        db_session.expire_all()
        assert run.config == durable
        assert db_session.scalar(select(MDAThreadState)).state_json == snapshot
        run.source_outcomes = {"linkedin": {"status": "empty", "received_count": 0}}
        db_session.commit()
        response = client.post(
            url,
            json={"onet_release": "30.0", "onet_occupation_codes": ["15-2051.00"]},
            headers=teacher_auth_headers,
        )
        assert response.status_code == 409
        db_session.expire_all()
        assert run.config == durable
