"""Cold checkpoint DDL belongs to startup, before authenticated read transactions."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from psycopg.errors import UndefinedColumn
from sqlalchemy import text

from app.core.database import async_engine, engine
from app.modules.marketdemandanalyst import graph as market_graph
from main import app
from tests.modules.test_market_workspace_chat import ScriptedModel


@pytest.fixture
def cold_checkpoint_schema(db_session):
    # Never touch the acceptance database or any deployment's checkpoints.
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT current_database()")) in {
            "lab_tutor_test",
            "lab_tutor_workspace_test",
        }
        connection.execute(
            text(
                "DROP TABLE IF EXISTS checkpoint_writes, checkpoint_blobs, "
                "checkpoints, checkpoint_migrations"
            )
        )
    assert market_graph._ASYNC_CHECKPOINTER is None
    assert market_graph._CONN_POOL is None
    yield


def register_course(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "cold-checkpoint@example.com",
            "password": "test-password",
            "first_name": "Cold",
            "last_name": "Start",
            "role": "teacher",
        },
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/auth/jwt/login",
        data={
            "username": "cold-checkpoint@example.com",
            "password": "test-password",
        },
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    course = client.post("/courses", json={"title": "Cold history"}, headers=headers)
    assert course.status_code == 201, course.text
    return course.json(), headers


async def bounded_history(course_id, headers):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await asyncio.wait_for(
            client.get(f"/courses/{course_id}/market-demand/history", headers=headers),
            timeout=3,
        )


def test_first_cold_authenticated_history_is_bounded_without_model_invocation(
    cold_checkpoint_schema, monkeypatch
):
    model = ScriptedModel()
    model_creations = []

    def create_model():
        model_creations.append(True)
        return model

    monkeypatch.setattr(market_graph, "_create_llm", create_model)
    with TestClient(app) as client:
        try:
            # Storage startup must not compile the workflow or require an LLM.
            assert model_creations == []
            assert market_graph._ASYNC_CHECKPOINTER is not None
            with engine.connect() as connection:
                indexes = connection.execute(
                    text(
                        "SELECT indexrelid::regclass::text, indisvalid FROM pg_index "
                        "WHERE indexrelid::regclass::text IN "
                        "('checkpoints_thread_id_idx', 'checkpoint_blobs_thread_id_idx', "
                        "'checkpoint_writes_thread_id_idx')"
                    )
                ).all()
            assert len(indexes) == 3 and all(valid for _, valid in indexes)
            course, headers = register_course(client)
            response = client.portal.call(bounded_history, course["id"], headers)
            assert response.status_code == 200, response.text
            assert response.json()["messages"] == []
            assert model.calls == []
            pool = market_graph._CONN_POOL
            assert pool is not None and not pool.closed
        finally:
            # SQLAlchemy's test pool must also be disposed in its owning loop.
            client.portal.call(async_engine.dispose)
    assert pool.closed
    assert market_graph._ASYNC_CHECKPOINTER is None
    assert market_graph._COMPILED_GRAPH is None


@pytest.mark.anyio
async def test_failed_real_setup_is_not_cached_and_can_retry(cold_checkpoint_schema):
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE checkpoint_migrations (wrong_column integer)")
        )
    try:
        with pytest.raises(UndefinedColumn, match='column "v" does not exist'):
            await market_graph._get_async_checkpointer()
        assert market_graph._ASYNC_CHECKPOINTER is None
        assert market_graph._CONN_POOL is None
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE checkpoint_migrations"))
        ready = await market_graph._get_async_checkpointer()
        assert (
            await ready.aget_tuple({"configurable": {"thread_id": "cold-start-empty"}})
            is None
        )
    finally:
        await market_graph.close_market_checkpoint_storage()


@pytest.mark.anyio
async def test_setup_does_not_publish_a_saver_while_migrations_are_blocked(
    cold_checkpoint_schema,
):
    # A real database lock holds setup in progress without a fake checkpointer.
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE checkpoint_migrations (v integer PRIMARY KEY)")
        )
    lock = engine.connect()
    transaction = lock.begin()
    lock.execute(text("LOCK TABLE checkpoint_migrations IN ACCESS EXCLUSIVE MODE"))
    initializations = [
        asyncio.create_task(market_graph._get_async_checkpointer()) for _ in range(2)
    ]
    try:
        async with asyncio.timeout(3):
            while True:
                with engine.connect() as probe:
                    waiting = probe.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                            "AND query LIKE '%checkpoint_migrations%'"
                        )
                    )
                if waiting:
                    break
                await asyncio.sleep(0.01)
        assert market_graph._ASYNC_CHECKPOINTER is None
        assert market_graph._CONN_POOL is None
        assert all(not task.done() for task in initializations)
        transaction.rollback()
        ready, concurrent = await asyncio.wait_for(
            asyncio.gather(*initializations), timeout=3
        )
        assert ready is concurrent is await market_graph._get_async_checkpointer()
    finally:
        if transaction.is_active:
            transaction.rollback()
        lock.close()
        for initialization in initializations:
            if not initialization.done():
                initialization.cancel()
        await asyncio.gather(*initializations, return_exceptions=True)
        await market_graph.close_market_checkpoint_storage()


@pytest.mark.anyio
async def test_lifespan_setup_failure_aborts_serving_then_can_restart(
    cold_checkpoint_schema,
    monkeypatch,
):
    model_creations = []

    def create_model():
        model_creations.append(True)
        return ScriptedModel()

    monkeypatch.setattr(market_graph, "_create_llm", create_model)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE checkpoint_migrations (wrong_column integer)")
        )
    try:
        with pytest.raises(UndefinedColumn, match='column "v" does not exist'):
            async with app.router.lifespan_context(app):
                pytest.fail("Startup served before checkpoint migrations succeeded")
        assert market_graph._ASYNC_CHECKPOINTER is None
        assert market_graph._CONN_POOL is None
        assert market_graph._CHECKPOINT_INIT_LOCK is None
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE checkpoint_migrations"))
        previous_pool = None
        for _ in range(2):
            async with app.router.lifespan_context(app):
                pool = market_graph._CONN_POOL
                assert pool is not None and not pool.closed
                assert pool is not previous_pool
                saver = await market_graph._get_async_checkpointer()
                assert (
                    await saver.aget_tuple(
                        {"configurable": {"thread_id": "startup-empty"}}
                    )
                    is None
                )
                assert market_graph._COMPILED_GRAPH is None
            assert pool.closed
            assert market_graph._ASYNC_CHECKPOINTER is None
            assert market_graph._CONN_POOL is None
            assert market_graph._CHECKPOINT_INIT_LOCK is None
            previous_pool = pool
        assert model_creations == []
    finally:
        await async_engine.dispose()
