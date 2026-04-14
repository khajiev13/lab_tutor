from __future__ import annotations

import os
from functools import lru_cache

from neo4j import Driver, GraphDatabase


@lru_cache(maxsize=1)
def get_neo4j_driver() -> Driver:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password123")
    return GraphDatabase.driver(uri, auth=(user, password))
