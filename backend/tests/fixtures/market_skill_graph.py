"""Reusable disposable graph fixture; explicit configuration is mandatory."""

import os
from urllib.parse import urlsplit

import pytest
from neo4j import GraphDatabase


@pytest.fixture
def graph_driver(monkeypatch):
    uri = os.environ.get("MARKET_SKILL_TEST_NEO4J_URI", "")
    assert uri and urlsplit(uri).hostname == "lab_tutor_market_projection_test", (
        "Required disposable test graph must be explicitly configured"
    )
    username = os.environ["MARKET_SKILL_TEST_NEO4J_USERNAME"]
    password = os.environ["MARKET_SKILL_TEST_NEO4J_PASSWORD"]
    assert os.environ["MARKET_SKILL_TEST_NEO4J_DATABASE"] == "neo4j"
    from app.core.settings import settings

    # Tool-created repositories use settings; never inherit the app database.
    monkeypatch.setattr(settings, "neo4j_database", "neo4j")
    monkeypatch.setenv("LAB_TUTOR_NEO4J_DATABASE", "neo4j")
    driver = GraphDatabase.driver(
        uri,
        auth=(username, password),
        connection_timeout=3,
        max_transaction_retry_time=1,
    )
    driver.verify_connectivity()
    with driver.session(database="neo4j") as session:
        session.run("MATCH (n) DETACH DELETE n").consume()
        for statement in [
            "CREATE CONSTRAINT reference_id_unique IF NOT EXISTS FOR (r:COURSE_SKILL_REFERENCE) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT evidence_binding_id_unique IF NOT EXISTS FOR (b:SKILL_EVIDENCE_BINDING) REQUIRE b.id IS UNIQUE",
            "CREATE CONSTRAINT career_skill_id_unique IF NOT EXISTS FOR (s:CAREER_SKILL) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT market_skill_name_unique IF NOT EXISTS FOR (s:MARKET_SKILL) REQUIRE s.name IS UNIQUE",
            "CREATE CONSTRAINT career_evidence_id_unique IF NOT EXISTS FOR (e:CAREER_EVIDENCE) REQUIRE e.id IS UNIQUE",
        ]:
            session.run(statement).consume()
    yield driver
    with driver.session(database="neo4j") as session:
        session.run("MATCH (n) DETACH DELETE n").consume()
    driver.close()
