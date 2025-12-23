from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.settings import settings

from .prompts.extraction_prompts import (
    COMPLETE_EXTRACTION_PROMPT,
    EXTRACTION_PROMPT_WITH_EXAMPLES,
)
from .schemas import (
    CanonicalExtractionResult,
    CompleteExtractionResult,
    ExtractionMetadata,
)

logger = logging.getLogger(__name__)


class DocumentLLMExtractor:
    """LLM-based document extractor using LangChain structured outputs."""

    def __init__(self, *, use_examples: bool = True) -> None:
        self.use_examples = use_examples

        if not settings.llm_api_key:
            raise ValueError(
                "LLM is required for extraction. Set LAB_TUTOR_LLM_API_KEY (or XiaoCase fallback env vars)."
            )

        prompt_content = (
            EXTRACTION_PROMPT_WITH_EXAMPLES
            if self.use_examples
            else COMPLETE_EXTRACTION_PROMPT
        )
        self.prompt_template = PromptTemplate.from_template(prompt_content)

        base_llm = ChatOpenAI(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=SecretStr(settings.llm_api_key),
            temperature=0,
            timeout=settings.llm_timeout_seconds,
            max_completion_tokens=settings.llm_max_completion_tokens,
        )

        # json_mode tends to be reliable for OpenAI-ish models.
        method = "json_mode" if "gpt-4o" in settings.llm_model else "function_calling"
        self.chain = self.prompt_template | base_llm.with_structured_output(
            CanonicalExtractionResult, method=method
        )

    def preprocess_text(self, text: str) -> str:
        """Remove boilerplate/noise to improve extraction quality."""
        lines = text.split("\n")
        cleaned_lines: list[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip page numbers / timestamps / numeric artifacts.
            if re.match(r"^[\d\s\-:.,]+$", line):
                continue

            # Skip very short lines likely to be artifacts.
            if len(line) < 10:
                continue

            # Skip lines with excessive punctuation/special characters.
            if len(re.findall(r"[^\w\s]", line)) > len(line) * 0.3:
                continue

            cleaned_lines.append(line)

        cleaned_text = "\n".join(cleaned_lines)
        cleaned_text = re.sub(r"\n\s*\n", "\n\n", cleaned_text)
        cleaned_text = re.sub(r" +", " ", cleaned_text)
        return cleaned_text.strip()

    def extract(
        self, *, text: str, source_filename: str | None = None
    ) -> CompleteExtractionResult:
        raw_text = text or ""
        cleaned_text = self.preprocess_text(raw_text)

        try:
            raw: Any = self.chain.invoke({"text": cleaned_text})
            extraction: CanonicalExtractionResult = (
                raw
                if isinstance(raw, CanonicalExtractionResult)
                else CanonicalExtractionResult.model_validate(raw)
            )
            return CompleteExtractionResult(
                extraction=extraction,
                metadata=ExtractionMetadata(
                    source_filename=source_filename,
                    original_text_length=len(raw_text),
                    processed_text_length=len(cleaned_text),
                    model_used=settings.llm_model,
                ),
                success=True,
            )
        except Exception as e:
            logger.exception("LLM extraction failed")
            return CompleteExtractionResult(
                extraction=CanonicalExtractionResult(
                    topic="Extraction Failed",
                    summary="Extraction failed due to an error.",
                    keywords=["extraction", "failed", "error", "processing", "system"],
                    concepts=[],
                ),
                metadata=ExtractionMetadata(
                    source_filename=source_filename,
                    original_text_length=len(raw_text),
                    processed_text_length=len(cleaned_text),
                    model_used=settings.llm_model,
                ),
                success=False,
                error_message=str(e),
            )


