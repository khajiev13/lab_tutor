"""Typed pipeline state for the Market Demand Analyst.

Replaces the raw ``tool_store: dict`` with a ``PipelineStore`` class whose
every field is an explicit, typed attribute.  Serialization (snapshot/restore)
is automatic — no more STATE_KEYS list to keep in sync.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel

from .schemas import (
    CurriculumMapping,
    ExtractedSkill,
    InsertionResults,
    JobPosting,
    SkillConceptAnalysis,
    SkillForInsertion,
)

logger = logging.getLogger(__name__)


# ── Field descriptors for automatic snapshot/restore ──────────────


class _Field:
    """Metadata for one PipelineStore attribute."""

    __slots__ = ("default_factory", "model_class", "is_dict_of_models", "persist")

    def __init__(
        self,
        *,
        default_factory: Any = None,
        model_class: type[BaseModel] | None = None,
        is_dict_of_models: bool = False,
        persist: bool = True,
    ):
        self.default_factory = default_factory or (lambda: None)
        self.model_class = model_class
        self.is_dict_of_models = is_dict_of_models
        self.persist = persist


# Registry: field name → metadata.  Order matters for STATE_KEYS compat.
_FIELDS: dict[str, _Field] = {
    "fetched_jobs": _Field(default_factory=list, model_class=JobPosting),
    "job_groups": _Field(default_factory=dict),
    "selected_jobs": _Field(default_factory=list, model_class=JobPosting),
    "extracted_skills": _Field(default_factory=list, model_class=ExtractedSkill),
    "total_jobs_for_extraction": _Field(default_factory=lambda: 0),
    "existing_graph_skills": _Field(default_factory=list),
    "existing_concepts": _Field(default_factory=list),
    "curated_skills": _Field(default_factory=list, model_class=ExtractedSkill),
    "curriculum_mapping": _Field(default_factory=list, model_class=CurriculumMapping),
    "mapped_skills": _Field(default_factory=dict),
    "final_skills": _Field(default_factory=list),
    "selected_for_insertion": _Field(
        default_factory=list, model_class=SkillForInsertion
    ),
    "skill_concepts": _Field(
        default_factory=dict,
        model_class=SkillConceptAnalysis,
        is_dict_of_models=True,
    ),
    "insertion_results": _Field(
        default_factory=lambda: None, model_class=InsertionResults
    ),
}

# Keys exposed to routes.py for SSE state_update diffing (same order as before)
STATE_KEYS: list[str] = list(_FIELDS.keys())


# ── PipelineStore ─────────────────────────────────────────────────


class PipelineStore:
    """Typed pipeline state — replaces the raw dict ``tool_store``.

    Every persistent field is an explicit attribute.  ``snapshot()``
    serializes them to JSON-compatible dicts; ``restore()`` deserializes
    back.  No more STATE_KEYS to keep in sync.

    Transient fields (prefixed with ``_``) are NOT persisted.
    """

    # ── Persistent fields ──
    fetched_jobs: list[JobPosting]
    job_groups: dict[str, list[int]]
    selected_jobs: list[JobPosting]
    extracted_skills: list[ExtractedSkill]
    total_jobs_for_extraction: int
    existing_graph_skills: list[dict]
    existing_concepts: list[str]
    curated_skills: list[ExtractedSkill]
    curriculum_mapping: list[CurriculumMapping]
    mapped_skills: dict[str, list[str]]
    final_skills: list[str]
    selected_for_insertion: list[SkillForInsertion]
    skill_concepts: dict[str, SkillConceptAnalysis]
    insertion_results: InsertionResults | None

    # ── Transient fields (not persisted, lost on restore) ──
    _raw_extracted_skills: list[ExtractedSkill]
    _cleaned_results: list[dict]
    chapters: list[dict]

    def __init__(self) -> None:
        self.clear()

    # ── Core API ──

    def clear(self) -> None:
        """Reset every field to its default value."""
        for name, field in _FIELDS.items():
            setattr(self, name, field.default_factory())
        # Transient
        self._raw_extracted_skills = []
        self._cleaned_results = []
        self.chapters = []

    def snapshot(self) -> dict[str, Any]:
        """Serialize all persistent fields to a JSON-compatible dict."""
        result: dict[str, Any] = {}
        for name, field in _FIELDS.items():
            val = getattr(self, name, None)
            if val is None:
                result[name] = None
            elif field.model_class and field.is_dict_of_models:
                # dict[str, Model] → dict[str, dict]
                result[name] = {
                    k: v.model_dump() if isinstance(v, BaseModel) else v
                    for k, v in val.items()
                }
            elif field.model_class and isinstance(val, list):
                # list[Model] → list[dict]
                result[name] = [
                    item.model_dump() if isinstance(item, BaseModel) else item
                    for item in val
                ]
            elif field.model_class and isinstance(val, BaseModel):
                # Single model → dict
                result[name] = val.model_dump()
            elif isinstance(val, (list, dict, str, int, float, bool)):
                result[name] = val
            else:
                result[name] = str(val)
        return result

    def restore(self, data: dict[str, Any]) -> None:
        """Restore from a persisted JSON dict."""
        self.clear()
        for name, field in _FIELDS.items():
            raw = data.get(name)
            if raw is None:
                continue
            if field.model_class and field.is_dict_of_models and isinstance(raw, dict):
                setattr(
                    self,
                    name,
                    {
                        k: field.model_class.model_validate(v)
                        if isinstance(v, dict)
                        else v
                        for k, v in raw.items()
                    },
                )
            elif field.model_class and isinstance(raw, list):
                setattr(
                    self,
                    name,
                    [
                        field.model_class.model_validate(item)
                        if isinstance(item, dict)
                        else item
                        for item in raw
                    ],
                )
            elif (
                field.model_class
                and not field.is_dict_of_models
                and isinstance(raw, dict)
            ):
                setattr(self, name, field.model_class.model_validate(raw))
            else:
                setattr(self, name, raw)


# Module-level singleton (replaces ``tool_store: dict = {}``)
store = PipelineStore()


# ── Backward-compat aliases (routes.py imports these) ─────────────


def snapshot_state() -> dict[str, Any]:
    return store.snapshot()


def restore_state(state_json: dict[str, Any]) -> None:
    store.restore(state_json)


# ── Pipeline summary (injected into agent system prompts) ─────────


def pipeline_summary() -> str:
    """Build a concise summary of current pipeline progress.

    Returned text is injected into the system prompt so every agent knows
    where the pipeline stands without needing to call show_current_state.
    """
    parts: list[str] = []
    s = store

    if s.insertion_results:
        parts.append(
            f"Pipeline COMPLETE. Insertion results: {s.insertion_results.model_dump()}"
        )
        return " | ".join(parts)

    if s.fetched_jobs:
        parts.append(
            f"Fetched {len(s.fetched_jobs)} jobs in {len(s.job_groups)} groups"
        )
    if s.selected_jobs:
        parts.append(f"Selected {len(s.selected_jobs)} jobs for analysis")
    if s.extracted_skills:
        parts.append(f"Extracted {len(s.extracted_skills)} skills")
    if s.curated_skills:
        parts.append(f"Teacher curated {len(s.curated_skills)} skills")
    if s.curriculum_mapping:
        covered = sum(1 for m in s.curriculum_mapping if m.status == "covered")
        gap = sum(1 for m in s.curriculum_mapping if m.status == "gap")
        new_t = sum(1 for m in s.curriculum_mapping if m.status == "new_topic_needed")
        parts.append(
            f"Curriculum mapping: {covered} covered, {gap} gaps, {new_t} new topics"
        )
    if s.mapped_skills:
        total_mapped = sum(len(skills) for skills in s.mapped_skills.values())
        parts.append(f"Mapped {total_mapped} skills to {len(s.mapped_skills)} chapters")
    if s.final_skills:
        parts.append(f"Cleaned to {len(s.final_skills)} final skills")
    if s.selected_for_insertion:
        parts.append(
            f"Teacher approved {len(s.selected_for_insertion)} skills for insertion"
        )
    if s.skill_concepts:
        parts.append(f"Concept linking done for {len(s.skill_concepts)} skills")

    if not parts:
        parts.append("Pipeline not started yet — no jobs fetched")

    # Determine next step
    if not s.fetched_jobs:
        parts.append("NEXT: Fetch jobs")
    elif not s.selected_jobs:
        parts.append("NEXT: Ask teacher which job groups to select")
    elif not s.extracted_skills:
        parts.append("NEXT: Extract skills from selected jobs")
    elif not s.curated_skills:
        parts.append("NEXT: Teacher picks skills from extracted list")
    elif not s.curriculum_mapping:
        parts.append("NEXT: Map curated skills to curriculum")
    elif not s.final_skills:
        parts.append("NEXT: Clean skills (remove redundant vs book skills)")
    elif not s.skill_concepts:
        parts.append("NEXT: Link concepts for final skills")
    elif not s.insertion_results:
        parts.append("NEXT: Update Knowledge Map")

    return " | ".join(parts)


class AgentState(TypedDict):
    """State for the Market Demand Agent conversation."""

    messages: Annotated[list, add_messages]
    fetched_jobs: list[dict]
    selected_jobs: list[dict]
    extracted_skills: list[dict]
    existing_graph_skills: list[dict]
    existing_graph_concepts: list[str]
    curriculum_mapping: list[dict]
    selected_skills_for_insertion: list[dict]
    course_title: str
    course_description: str
