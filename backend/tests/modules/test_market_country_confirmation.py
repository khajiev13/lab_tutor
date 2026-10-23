"""Country confirmation updates a draft's SQL configuration before collection."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

import pandas as pd
import pytest
from langchain_core.messages import AIMessage
from sqlalchemy.orm import sessionmaker

from app.modules.marketdemandanalyst import tools
from app.modules.marketdemandanalyst.job_sources import JobSourceService
from app.modules.marketdemandanalyst.repository import MarketReviewRepository
from app.modules.marketdemandanalyst.service import MarketSourceService
from app.modules.marketdemandanalyst.state import bind_tool_store
from tests.course_material_fixtures import seed_ready_materials
from tests.modules import test_market_workspace_chat

live_graph = test_market_workspace_chat.live_graph


@pytest.fixture
def draft_market(db_session, client, teacher_auth_headers, monkeypatch):
    course = client.post(
        "/courses", json={"title": "Big Data"}, headers=teacher_auth_headers
    ).json()
    run = MarketReviewRepository(db_session).create_run(
        course["id"],
        course["teacher_id"],
        {
            "country": "USA",
            "sources": ["indeed", "linkedin"],
            "evidence_sources": ["jobs"],
        },
    )
    db_session.commit()
    state = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        "job_search_country": "USA",
        "job_search_country_confirmed": False,
        "sources": ["indeed", "linkedin"],
        "evidence_sources": ["jobs"],
    }

    def scraper(**kwargs):
        assert kwargs["location"] == "Uzbekistan"
        assert kwargs["site_name"] == ["linkedin"]
        assert "country_indeed" not in kwargs
        return pd.DataFrame()

    source_service = MarketSourceService(
        jobs=JobSourceService(jobspy_scraper=scraper),
        session_factory=sessionmaker(bind=db_session.get_bind()),
    )
    monkeypatch.setattr(tools, "get_market_source_service", lambda: source_service)
    return state, run, source_service


def test_confirming_uzbekistan_updates_draft_and_allows_collection(
    draft_market, db_session
):
    state, run, source_service = draft_market
    with bind_tool_store(state):
        result = tools.set_job_search_country.invoke({"country": "Uzbekistan"})
        assert "set to Uzbekistan" in result
        assert state["job_search_country"] == "Uzbekistan"
        assert state["job_search_country_confirmed"] is True
        assert source_service.load_config(state)["country"] == "Uzbekistan"
        result = tools.fetch_jobs.invoke(
            {"search_terms": "Data Engineer, Data Scientist"}
        )
    assert "Select a job market" not in result
    assert state["source_outcomes"]["linkedin"]["status"] == "empty"
    assert state["source_outcomes"]["indeed"]["status"] == "skipped"
    db_session.refresh(run)
    assert run.config["country"] == "Uzbekistan"
    assert run.config["sources"] == ["indeed", "linkedin"]


@pytest.mark.parametrize("status", ["empty", "error", "success"])
@pytest.mark.parametrize("chat_country", ["USA", "Uzbekistan"])
def test_country_change_remains_locked_after_collection_even_without_jobs(
    draft_market, db_session, status, chat_country
):
    state, run, _ = draft_market
    run.source_outcomes = {"linkedin": {"status": status}}
    state["job_search_country"] = chat_country
    db_session.commit()
    before = deepcopy(state)
    with bind_tool_store(state):
        result = tools.set_job_search_country.invoke({"country": "Uzbekistan"})
    assert "start a new analysis" in result.lower()
    assert state == before
    db_session.refresh(run)
    assert run.config["country"] == "USA"


def test_chat_country_confirmation_survives_reload_and_skill_finder_handoff(
    draft_market, db_session, client, teacher_auth_headers, live_graph
):
    state, run, _ = draft_market
    seed_ready_materials(state["course_id"])
    repo = MarketReviewRepository(db_session)
    thread = f"mda-{state['teacher_id']}-course-{state['course_id']}"
    repo.save_configuration_snapshot(thread, state)
    db_session.commit()
    model, _, checkpoint = live_graph
    checkpoint(thread)
    model.replies.extend(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "confirm-country",
                        "name": "set_job_search_country",
                        "args": {"country": "Uzbekistan"},
                    }
                ],
            ),
            AIMessage(content="Country confirmed. Choose search terms."),
        ]
    )
    url = f"/courses/{state['course_id']}/market-demand"
    response = client.post(
        f"{url}/chat", json={"message": "Uzbekistan"}, headers=teacher_auth_headers
    )
    assert response.status_code == 200, response.text
    saved = client.get(f"{url}/state", headers=teacher_auth_headers).json()
    assert saved["job_search_country"] == "Uzbekistan"
    assert saved["job_search_country_confirmed"] is True
    model.replies.extend(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "handoff-finder",
                        "name": "transfer_to_skill_finder",
                        "args": {},
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "fetch-jobs",
                        "name": "fetch_jobs",
                        "args": {"search_terms": "Data Engineer, Data Scientist"},
                    }
                ],
            ),
            AIMessage(content="No postings were returned for these terms."),
        ]
    )
    response = client.post(
        f"{url}/chat",
        json={"message": "Data engineer and scientist"},
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200, response.text
    saved = client.get(f"{url}/state", headers=teacher_auth_headers).json()
    assert saved["job_search_country"] == "Uzbekistan"
    assert saved["source_outcomes"]["linkedin"]["status"] == "empty"
    db_session.refresh(run)
    assert run.config["country"] == "Uzbekistan"
    assert run.source_outcomes["linkedin"]["status"] == "empty"


def test_same_country_confirmation_uses_durable_config_over_stale_chat_state(
    draft_market, db_session
):
    state, run, _ = draft_market
    run.config = {**run.config, "country": "Uzbekistan"}
    run.source_outcomes = {"linkedin": {"status": "empty"}}
    db_session.commit()
    with bind_tool_store(state):
        result = tools.set_job_search_country.invoke({"country": "Uzbekistan"})
    assert "set to Uzbekistan" in result
    assert state["job_search_country"] == "Uzbekistan"
    assert state["job_search_country_confirmed"] is True


def test_unavailable_market_does_not_change_state_or_saved_configuration(
    draft_market, db_session
):
    state, run, _ = draft_market
    run.config = {**run.config, "sources": ["indeed"]}
    state["sources"] = ["indeed"]
    db_session.commit()
    before = deepcopy(state)
    with bind_tool_store(state):
        result = tools.set_job_search_country.invoke({"country": "Uzbekistan"})
    assert "No available job provider" in result
    assert state == before
    db_session.refresh(run)
    assert run.config["country"] == "USA"


def test_country_confirmation_preserves_parallel_tool_state(draft_market, monkeypatch):
    state, _, source_service = draft_market
    state["selected_jobs"] = []
    configured = Event()
    selected = Event()
    configure = source_service.configure_country

    def paused_confirmation(*args):
        update = configure(*args)
        configured.set()
        assert selected.wait(timeout=5)
        return update

    monkeypatch.setattr(source_service, "configure_country", paused_confirmation)

    def confirm():
        with bind_tool_store(state):
            return tools.set_job_search_country.invoke({"country": "USA"})

    with ThreadPoolExecutor(max_workers=1) as executor:
        confirmation = executor.submit(confirm)
        try:
            assert configured.wait(timeout=5)
            state["selected_jobs"] = [{"title": "Data Engineer"}]
        finally:
            selected.set()
        assert "set to United States" in confirmation.result(timeout=5)
    assert state["selected_jobs"] == [{"title": "Data Engineer"}]
