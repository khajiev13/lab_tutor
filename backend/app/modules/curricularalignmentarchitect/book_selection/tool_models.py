from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchResultItem(BaseModel):
    """A single normalized search result."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field("", description="Human-readable page/book title")
    url: str | None = Field(None, description="Canonical URL, if available")
    snippet: str | None = Field(None, description="Short cleaned snippet")
    source: str = Field("", description="Source system identifier")
    score: float | None = Field(
        None, description="Relevance score, if provided by the API"
    )


ToolName = Literal[
    "tavily_search",
    "googlebooksqueryrun",
    "duckduckgo_search",
    "open_library_search",
    "download_file_from_url",
]


class SearchResponse(BaseModel):
    """Standard tool response envelope."""

    model_config = ConfigDict(extra="ignore")

    ok: bool = Field(..., description="True when the request succeeded")
    tool: ToolName = Field(..., description="Tool identifier")
    query: str = Field(..., description="Final cleaned query used")
    results: list[SearchResultItem] = Field(default_factory=list)
    error: str | None = Field(default=None, description="Error message when ok=False")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")
