"""Pydantic v2 models for the Market Demand Analyst pipeline.

Every dict shape that flows through PipelineStore is defined here.
Using typed models eliminates the class of bugs where a dict key is
forgotten in STATE_KEYS (e.g. the SOURCED_FROM URL bug).
"""

from pydantic import BaseModel


class JobPosting(BaseModel):
    """A scraped job posting."""

    title: str
    company: str
    description: str
    url: str
    site: str
    search_term: str


class RawExtractedSkill(BaseModel):
    """Skill extracted from one job posting (pre-dedup). Internal to extractor."""

    name: str
    category: str
    source_url: str = ""
    source_title: str = ""
    source_company: str = ""


class ExtractedSkill(BaseModel):
    """Deduplicated + merged skill with frequency and URL provenance.

    source_urls carries the job posting URLs this skill was extracted from,
    eliminating the need for a separate skill_job_urls mapping dict.
    """

    name: str
    category: str
    frequency: int = 0
    pct: float = 0.0
    merged_from: list[str] = []
    source_urls: list[str] = []


class CurriculumMapping(BaseModel):
    """Result of mapping one skill to the curriculum."""

    name: str
    category: str = ""
    status: str = ""  # "covered" | "gap" | "new_topic_needed"
    target_chapter: str = ""
    related_concepts: list[str] = []
    priority: str = "medium"
    reasoning: str = ""


class SkillForInsertion(BaseModel):
    """Teacher-approved skill ready for Neo4j insertion."""

    name: str
    category: str = ""
    target_chapter: str = ""
    rationale: str = ""


class NewConcept(BaseModel):
    """A concept proposed by the Concept Linker."""

    name: str
    description: str = ""


class SkillConceptAnalysis(BaseModel):
    """Output of concept linking for one skill."""

    existing_concepts: list[str] = []
    new_concepts: list[NewConcept] = []
    chapter_title: str = ""
    category: str = ""
    frequency: int = 0
    demand_pct: float = 0.0
    priority: str = ""
    status: str = ""
    rationale: str = ""
    reasoning: str = ""
    source_job_urls: list[str] = []


class InsertionResults(BaseModel):
    """Stats from insert_market_skills_to_neo4j."""

    skills: int = 0
    job_postings: int = 0
    chapter_links: int = 0
    sourced_from: int = 0
    existing_concept_links: int = 0
    new_concepts: int = 0
    concepts_merged: int = 0
