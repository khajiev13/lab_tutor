"""Pydantic models used across the book-selection workflow."""

from __future__ import annotations

import json
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, field_validator, model_validator

# ═══════════════════════════════════════════════════════════════
# Discovery Pydantic Models
# ═══════════════════════════════════════════════════════════════


class SearchQueryBatch(BaseModel):
    """LLM-generated batch of search queries for book discovery."""

    rationale: str = Field(
        default="",
        description=(
            "Brief explanation: what subject/discipline was identified "
            "and what query strategy was used."
        ),
    )
    queries: list[str] = Field(
        ...,
        min_length=6,
        max_length=15,
        description=(
            "10-12 diverse, short (3-12 word) search queries. "
            "Each query will be executed on BOTH Google Books and Tavily."
        ),
    )

    @field_validator("rationale", mode="before")
    @classmethod
    def coerce_rationale(cls, v: Any) -> str:
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        if v is None:
            return ""
        return str(v)

    @model_validator(mode="before")
    @classmethod
    def normalize_query_fields(cls, data: Any) -> Any:
        """Accept alternate field names for queries."""
        if isinstance(data, dict) and "queries" not in data:
            for alt in ("search_queries", "query_list", "search_terms"):
                if alt in data:
                    data["queries"] = data.pop(alt)
                    break
        return data


class DiscoveredBook(BaseModel):
    title: str
    authors: str = ""
    publisher: str = ""
    year: str = ""
    reason: str = Field("", description="Why this book is relevant")


class DiscoveredBookList(BaseModel):
    """Robust wrapper — accepts 'books', 'textbooks', 'items', or 'results'."""

    books: list[DiscoveredBook]

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, data: Any) -> Any:
        if isinstance(data, dict) and "books" not in data:
            for alt in ("textbooks", "items", "results", "book_list", "deduplicated_books"):
                if alt in data:
                    data["books"] = data.pop(alt)
                    break
            else:
                lists = [v for v in data.values() if isinstance(v, list)]
                if len(lists) == 1:
                    data["books"] = lists[0]
        return data


# ═══════════════════════════════════════════════════════════════
# Scoring Pydantic Models
# ═══════════════════════════════════════════════════════════════

CRITERIA_KEYS = ("topic", "struc", "scope", "pub", "auth", "time", "prac")


def _norm_score(value: Any) -> float:
    """Clamp scores into [0, 1]. Accepts 0-1, 0-5, or 0-100 scales."""
    if value is None:
        return 0.0
    v = float(value)
    if v <= 1.0:
        return max(0.0, v)
    if v <= 5.0:
        return v / 5.0
    if v <= 100.0:
        return v / 100.0
    return 1.0


def _norm_rationale(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class CriterionScore(BaseModel):
    """A single criterion evaluation: score + rationale."""

    s: float = Field(0.0, ge=0, le=1, description="Score in [0, 1]")
    r: str = Field("", description="Rationale (≤2 sentences)")

    @model_validator(mode="before")
    @classmethod
    def coerce(cls, data: Any) -> Any:
        # Scalar → treat as score with empty rationale
        if isinstance(data, (int, float)):
            return {"s": _norm_score(data), "r": ""}
        if not isinstance(data, dict):
            return data
        # Accept alternate keys: score/value/rating → s, rationale/reason → r
        s = data.get("s")
        if s is None:
            s = data.get("score") or data.get("value") or data.get("rating") or 0.0
        r = data.get("r")
        if r is None:
            r = data.get("rationale") or data.get("reason") or data.get("justification") or ""
        return {"s": _norm_score(s), "r": _norm_rationale(r)}


class BookMeritScores(BaseModel):
    """7-criteria book evaluation. Each criterion is {s: float, r: str}."""

    C_topic: CriterionScore = Field(default_factory=CriterionScore)
    C_struc: CriterionScore = Field(default_factory=CriterionScore)
    C_scope: CriterionScore = Field(default_factory=CriterionScore)
    C_pub: CriterionScore = Field(default_factory=CriterionScore)
    C_auth: CriterionScore = Field(default_factory=CriterionScore)
    C_time: CriterionScore = Field(default_factory=CriterionScore)
    C_prac: CriterionScore = Field(default_factory=CriterionScore)

    @model_validator(mode="before")
    @classmethod
    def normalize_scoring_payload(cls, data: Any) -> Any:
        """Accept multiple LLM output shapes and normalise to {C_x: {s, r}}.

        Handles:
        - nested: {C_topic: {s: 0.8, r: "..."}, ...}  ← preferred
        - flat:   {C_topic: 0.8, C_topic_rationale: "...", ...}
        - split:  {scores: {C_topic: 0.8}, rationales: {C_topic: "..."}}
        """
        if not isinstance(data, dict):
            return data

        normalized: dict[str, Any] = {}

        # Possible nested containers
        nested_scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
        nested_rats = data.get("rationales") or data.get("reasons")
        nested_rats = nested_rats if isinstance(nested_rats, dict) else {}

        for key in CRITERIA_KEYS:
            ckey = f"C_{key}"
            raw = data.get(ckey)

            # Already a dict → pass through to CriterionScore.coerce
            if isinstance(raw, dict):
                normalized[ckey] = raw
                continue

            # Flat or split: assemble {s, r}
            score_val = raw  # may be float/int/None
            if score_val is None:
                for alt in (f"{key}_score", f"{key}Score", key):
                    if alt in data and not isinstance(data.get(alt), dict):
                        score_val = data[alt]
                        break
            if score_val is None:
                for alt in (ckey, key):
                    if alt in nested_scores:
                        score_val = nested_scores[alt]
                        break

            rat_val = data.get(f"{ckey}_rationale")
            if rat_val is None:
                for alt in (
                    f"{key}_rationale", f"{key}_reason",
                    f"{key}Rationale", f"{key}Reason",
                ):
                    if alt in data:
                        rat_val = data[alt]
                        break
            if rat_val is None:
                for alt in (ckey, key, f"{key}_rationale"):
                    if alt in nested_rats:
                        rat_val = nested_rats[alt]
                        break

            normalized[ckey] = {"s": score_val, "r": rat_val}

        return normalized

    # ── helpers ──────────────────────────────────────────────

    def to_flat_dict(self) -> dict[str, Any]:
        """Flatten to legacy format for storage / compute_finals.

        Returns: {C_topic: 0.8, C_topic_rationale: "...", ...}
        """
        out: dict[str, Any] = {}
        for key in CRITERIA_KEYS:
            cs: CriterionScore = getattr(self, f"C_{key}")
            out[f"C_{key}"] = cs.s
            out[f"C_{key}_rationale"] = cs.r
        return out


# ═══════════════════════════════════════════════════════════════
# Download Pydantic Models
# ═══════════════════════════════════════════════════════════════


class CandidateURL(BaseModel):
    """A candidate download URL found by the search agent."""

    url: str = Field(..., description="Direct download URL or download page URL")
    confidence: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Confidence this is a real download link (1.0=direct PDF link)",
    )


class CandidateURLList(BaseModel):
    """Extracted candidate URLs from search results."""

    urls: list[CandidateURL] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# LangGraph State TypedDicts
# ═══════════════════════════════════════════════════════════════

DEFAULT_WEIGHTS: dict[str, float] = {
    "C_topic": 0.30,
    "C_struc": 0.20,
    "C_scope": 0.15,
    "C_pub": 0.15,
    "C_auth": 0.10,
    "C_time": 0.10,
}
DEFAULT_W_PRAC: float = 0.0

VALID_COURSE_LEVELS = {"bachelor", "master", "phd"}
DEFAULT_COURSE_LEVEL = "bachelor"


class DiscoveryState(TypedDict, total=False):
    course_context: dict
    search_queries: list[str]
    query_rationale: str
    raw_books: Annotated[list[dict], operator.add]
    discovered_books: list[dict]


class ScoringState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_rounds: int
    book: dict
    course_context: dict
    course_level: str
    weights: dict[str, float]
    w_prac: float
    final_scores: dict


class DownloadState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_rounds: int
    book: dict
    candidate_urls: list[dict]
    download_result: dict


class WorkflowState(TypedDict, total=False):
    course_id: int
    course_context: dict
    course_level: str
    weights: dict[str, float]
    w_prac: float
    discovered_books: list[dict]
    scored_books: Annotated[list[dict], operator.add]
    top_books: list[dict]
    download_results: Annotated[list[dict], operator.add]
