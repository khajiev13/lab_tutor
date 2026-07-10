from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import pypdf
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.settings import settings
from app.modules.courses.file_processing import handle_docx_bytes

from .schemas import CVProfileExtraction

PDF_CONTENT_TYPES = {"application/pdf"}
DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}

_CV_EXTRACTION_PROMPT = """
Extract a factual professional profile from the CV text below.

Return only information supported by the CV. Keep skill evidence concise and avoid
inventing dates, employers, qualifications, or target roles. Suggest a short ordered
list of realistic target job titles. Confidence values must be between 0 and 1.
Never use -1; use 0 when confidence is unknown.

CV text:
{cv_text}
""".strip()


class StructuredCVProfileExtractor:
    """OpenAI-compatible structured CV extraction boundary."""

    def __init__(
        self,
        *,
        llm_factory: Callable[[], Any] | None = None,
        model_provider: str = "openai-compatible",
        model_name: str | None = None,
    ) -> None:
        self.model_provider = model_provider
        self.model_name = model_name or settings.llm_model
        llm = llm_factory() if llm_factory is not None else self._build_llm()
        method = "json_mode" if "gpt-4o" in self.model_name else "function_calling"
        prompt = PromptTemplate.from_template(_CV_EXTRACTION_PROMPT)
        self._chain = prompt | llm.with_structured_output(
            CVProfileExtraction,
            method=method,
        )

    def _build_llm(self) -> ChatOpenAI:
        if not settings.llm_api_key:
            raise ValueError(
                "LLM is required for CV extraction. Set LAB_TUTOR_LLM_API_KEY."
            )
        return ChatOpenAI(
            model=self.model_name,
            base_url=settings.llm_base_url,
            api_key=SecretStr(settings.llm_api_key),
            temperature=0,
            timeout=settings.llm_timeout_seconds,
            max_completion_tokens=settings.llm_max_completion_tokens,
        )

    def extract(self, text: str) -> CVProfileExtraction:
        raw = self._chain.invoke({"cv_text": text})
        if raw is None:
            raise ValueError("LLM returned an empty CV profile")
        if isinstance(raw, CVProfileExtraction):
            return raw
        return CVProfileExtraction.model_validate(raw)


def is_supported_cv_file(*, filename: str, content_type: str | None) -> bool:
    name = filename.lower().strip()
    content_type_value = (content_type or "").lower().strip()
    return (
        name.endswith(".pdf")
        or content_type_value in PDF_CONTENT_TYPES
        or name.endswith(".docx")
        or content_type_value in DOCX_CONTENT_TYPES
    )


def _extract_pdf_text(data: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except pypdf.errors.PyPdfError as exc:
        raise ValueError("Invalid PDF CV file") from exc

    return "\n\n".join(page for page in pages if page).strip()


def extract_cv_text(*, filename: str, content_type: str | None, data: bytes) -> str:
    name = filename.lower().strip()
    ct = (content_type or "").lower().strip()

    if name.endswith(".pdf") or ct in PDF_CONTENT_TYPES:
        text = _extract_pdf_text(data)
    elif name.endswith(".docx") or ct in DOCX_CONTENT_TYPES:
        text = handle_docx_bytes(data)
    else:
        raise ValueError("Only PDF and DOCX CV files are supported")

    if len(text.split()) < 20:
        raise ValueError("CV text is too short to analyze")

    return text
