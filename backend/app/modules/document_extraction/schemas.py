from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConceptExtraction(BaseModel):
    """A single extracted concept with contextual definition and evidence."""

    name: str = Field(
        description="Technical concept name exactly as mentioned in the text."
    )
    definition: str = Field(
        description="Definition grounded in the source text (context-specific)."
    )
    text_evidence: str = Field(
        description="Verbatim quote from the source text supporting the definition."
    )


class CanonicalExtractionResult(BaseModel):
    """Structured output for a single document."""

    topic: str = Field(description="Single concise title summarizing the document.")
    summary: str = Field(description="Coherent summary (30–50% of original length).")
    keywords: list[str] = Field(
        min_length=5,
        max_length=10,
        description="5–10 central keywords/terms.",
    )
    concepts: list[ConceptExtraction] = Field(
        default_factory=list,
        description="Extracted concepts.",
    )


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction run."""

    source_filename: str | None = Field(default=None, description="Source filename")
    original_text_length: int = Field(default=0, description="Raw text length (chars)")
    processed_text_length: int = Field(
        default=0, description="Processed/cleaned text length (chars)"
    )
    model_used: str | None = Field(default=None, description="LLM model used")


class CompleteExtractionResult(BaseModel):
    """Extraction plus metadata and success flag."""

    extraction: CanonicalExtractionResult
    metadata: ExtractionMetadata
    success: bool = True
    error_message: str | None = None


class ExtractionRunResult(BaseModel):
    """High-level runtime status for an extraction run (multi-file)."""

    course_id: int
    processed_files: int = 0
    failed_files: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)
