import io
import zipfile

import pytest
from langchain_core.runnables import RunnableLambda
from pypdf.errors import PdfReadError

from app.modules.individual_learning.cv_extractor import (
    StructuredCVProfileExtractor,
    extract_cv_text,
)
from app.modules.individual_learning.schemas import CVProfileExtraction


def _docx_bytes(text: str) -> bytes:
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", payload)
    return buf.getvalue()


def test_extract_cv_text_supports_docx() -> None:
    cv_text = (
        "Python SQL Azure FastAPI PostgreSQL Docker React TypeScript data analysis "
        "machine learning dashboards APIs cloud deployment testing architecture "
        "collaboration documentation monitoring orchestration pipelines"
    )
    text = extract_cv_text(
        filename="roma-cv.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        data=_docx_bytes(cv_text),
    )
    assert "Python SQL Azure FastAPI" in text


def test_extract_cv_text_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Only PDF and DOCX CV files are supported"):
        extract_cv_text(filename="cv.txt", content_type="text/plain", data=b"hello")


def test_extract_cv_text_rejects_malformed_pdf() -> None:
    with pytest.raises(ValueError, match="Invalid PDF CV file"):
        extract_cv_text(
            filename="cv.pdf",
            content_type="application/pdf",
            data=b"not a real pdf",
        )


def test_extract_cv_text_wraps_pdf_page_extraction_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenPage:
        def extract_text(self) -> str:
            raise PdfReadError("broken page")

    class _BrokenReader:
        pages = [_BrokenPage()]

    monkeypatch.setattr(
        "app.modules.individual_learning.cv_extractor.pypdf.PdfReader",
        lambda *_args, **_kwargs: _BrokenReader(),
    )

    with pytest.raises(ValueError, match="Invalid PDF CV file"):
        extract_cv_text(
            filename="cv.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.7",
        )


def test_structured_cv_extractor_uses_cv_profile_schema_and_validates_output() -> None:
    captured: dict[str, object] = {}

    class FakeLLM:
        def with_structured_output(self, schema, *, method: str):
            captured["schema"] = schema
            captured["method"] = method
            return RunnableLambda(
                lambda _prompt: {
                    "summary": "Backend engineer",
                    "skills": [
                        {
                            "name": "Python",
                            "category": "Programming",
                            "evidence": "Built FastAPI services",
                            "confidence": 0.95,
                        }
                    ],
                    "target_title_suggestions": ["Backend Engineer"],
                    "confidence_summary": {"skills": 0.95},
                }
            )

    extractor = StructuredCVProfileExtractor(
        llm_factory=lambda: FakeLLM(),
        model_provider="test-provider",
        model_name="test-model",
    )

    result = extractor.extract(
        "Private CV text that must stay inside the prompt boundary"
    )

    assert captured["schema"] is CVProfileExtraction
    assert captured["method"] == "function_calling"
    assert result.skills[0].name == "Python"
    assert result.target_title_suggestions == ["Backend Engineer"]
    assert result.confidence_summary == {"skills": 0.95}
    assert extractor.model_provider == "test-provider"
    assert extractor.model_name == "test-model"
