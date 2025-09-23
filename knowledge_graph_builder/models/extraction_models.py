"""
Pydantic models for structured concept extraction from technical and educational transcripts.

These models define the expected output structure for extracting topics, summaries,
keywords, and concepts from lecture transcripts and technical documents.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ConceptExtraction(BaseModel):
    """A single concept representing theories, models, technologies, frameworks, or technical terms."""

    name: str = Field(
        description="Technical concept name preserving specificity and terminology intact "
                   "(e.g., 'MapReduce', 'ODBC', 'DIKW pyramid'). Extract exactly as mentioned in text."
    )
    definition: str = Field(
        description="Precise definition using the text's exact meaning. Avoid paraphrasing unless "
                   "clarification is necessary. Derive definition directly from source text."
    )
    text_evidence: str = Field(
        description="Exact verbatim quote from source text where this concept is mentioned or defined. "
                   "Must be word-for-word copy from the original text."
    )


class CanonicalExtractionResult(BaseModel):
    """Complete structured extraction result for technical document analysis."""

    topic: str = Field(
        description="Single concise title summarizing the session's overall subject. "
                   "Extract exactly one TOPIC that captures the main theme."
    )

    summary: str = Field(
        description="Clear and coherent summary reduced to 30-50% of original length, "
                   "covering all major sections and arguments while maintaining logical flow."
    )

    keywords: List[str] = Field(
        description="Comma-separated list of 5-10 high-value terms, phrases, or entities "
                   "most central to the lecture. Focus on technical terminology and key concepts.",
        min_length=5,
        max_length=10
    )

    concepts: List[ConceptExtraction] = Field(
        description="All important theories, models, technologies, frameworks, or technical terms. "
                   "Each must include precise definition derived from the text.",
        min_length=0
    )


class CanonicalExtractionWithText(CanonicalExtractionResult):
    """Extended extraction result that includes the original processed text."""

    original_text: str = Field(
        description="Cleaned text sent to the model for extraction.",
        default=""
    )


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction process."""
    
    source_file: Optional[str] = Field(
        default=None,
        description="Source file path"
    )

    original_text_length: int = Field(
        description="Original text length"
    )

    processed_text_length: int = Field(
        description="Processed text length"
    )

    model_used: str = Field(
        description="LLM model used"
    )


class CompleteExtractionResult(BaseModel):
    """Complete extraction result including both content and metadata."""
    
    extraction: CanonicalExtractionResult = Field(
        description="Main extraction results"
    )

    metadata: ExtractionMetadata = Field(
        description="Extraction metadata"
    )

    success: bool = Field(
        default=True,
        description="Extraction success status"
    )

    error_message: Optional[str] = Field(
        default=None,
        description="Error message if failed"
    )
