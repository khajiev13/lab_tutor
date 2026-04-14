"""Textual Resource Analyst — self-contained service.

Wraps the shared resource pipeline with TRA-specific config (prompts, weights,
blacklist domains). Provides a single entry point for fetching reading resources.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.core.resource_pipeline.pipeline import process_single_skill
from app.core.resource_pipeline.schemas import (
    CandidateResource,
    ProgressCallback,
    ResourceScore,
    SkillProfile,
)

from . import config

logger = logging.getLogger(__name__)


def fetch_readings_for_skill(
    skill: SkillProfile,
    *,
    progress: ProgressCallback | None = None,
) -> list[tuple[CandidateResource, ResourceScore, float]]:
    """Run the full reading discovery pipeline for a single skill.

    Returns scored resources, ready to be written to Neo4j.
    """
    current_year = datetime.now().year

    return process_single_skill(
        skill,
        query_gen_system=config.query_gen_system(current_year),
        query_user_message=config.query_user_message(skill.build_profile_text()),
        scoring_system=config.scoring_system(current_year),
        weights=config.WEIGHTS,
        blacklist_domains=config.BLACKLIST_DOMAINS,
        exclude_sites=config.QUERY_EXCLUDE_SITES,
        tavily_include_domains=config.TAVILY_INCLUDE_DOMAINS,
        resolve_video_pages=False,
        top_k=config.TOP_K_FINAL,
        progress=progress,
    )
