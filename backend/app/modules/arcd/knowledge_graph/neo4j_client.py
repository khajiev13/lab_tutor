"""Neo4j client for the ARCD module.

Re-uses the project's core Neo4j driver (app.core.neo4j / app.core.settings)
so that connection configuration stays in one place — the LAB_TUTOR env vars
(LAB_TUTOR_NEO4J_URI, LAB_TUTOR_NEO4J_USERNAME, LAB_TUTOR_NEO4J_PASSWORD).
"""

from __future__ import annotations

from functools import lru_cache

from neo4j import Driver

from app.core.neo4j import create_neo4j_driver


@lru_cache(maxsize=1)
def get_neo4j_driver() -> Driver:
    """Return a cached Neo4j driver using the project's settings."""
    driver = create_neo4j_driver()
    if driver is None:
        raise RuntimeError(
            "Neo4j is not configured. Set LAB_TUTOR_NEO4J_URI, "
            "LAB_TUTOR_NEO4J_USERNAME, and LAB_TUTOR_NEO4J_PASSWORD."
        )
    return driver
