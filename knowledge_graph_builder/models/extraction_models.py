"""
Pydantic models for structured concept extraction using LangChain.

These models define the expected output structure for canonical concept extraction
in the relationship-centric approach.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ConceptExtraction(BaseModel):
    """A single concept with its canonical name, contextual definition, and text evidence."""

    name: str = Field(
        description="Canonical concept name without redundant suffixes (e.g., 'Machine Learning', 'HDFS'). "
                   "Only extract concepts explicitly mentioned in source text."
    )
    definition: str = Field(
        description="Brief definition from the source text showing how this concept is used in the document."
    )
    text_evidence: str = Field(
        description="Exact verbatim quote from source where concept is mentioned. "
                   "Word-for-word copy, not paraphrase."
    )


class CanonicalExtractionResult(BaseModel):
    """Complete structured extraction result for canonical relationship-centric approach."""
    
    topic: str = Field(
        description="Concise title summarizing the document's subject."
    )

    summary: str = Field(
        description="Clear summary covering major sections (30-50% of original length)."
    )

    keywords: List[str] = Field(
        description="5-10 central terms from the text.",
        min_length=0,
        max_length=15  # Allow some flexibility
    )

    concepts: List[ConceptExtraction] = Field(
        description="Important concepts with canonical names and definitions.",
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
