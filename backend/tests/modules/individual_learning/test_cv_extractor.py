import io
import zipfile

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError
from pypdf.errors import PdfReadError

from app.modules.individual_learning.cv_extractor import (
    MAX_CV_PDF_PAGES,
    MAX_CV_TEXT_CHARS,
    MAX_DOCX_ARCHIVE_ENTRIES,
    MAX_DOCX_UNCOMPRESSED_BYTES,
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


def test_extract_cv_text_rejects_pdf_over_page_limit_before_extracting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _UnexpectedPage:
        def extract_text(self) -> str:
            raise AssertionError("over-limit PDF pages must not be extracted")

    class _OversizedReader:
        pages = [_UnexpectedPage() for _ in range(MAX_CV_PDF_PAGES + 1)]

    monkeypatch.setattr(
        "app.modules.individual_learning.cv_extractor.pypdf.PdfReader",
        lambda *_args, **_kwargs: _OversizedReader(),
    )

    with pytest.raises(ValueError, match="PDF CV exceeds the page limit"):
        extract_cv_text(
            filename="cv.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.7",
        )


def test_extract_cv_text_rejects_pdf_text_over_character_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _OversizedPage:
        def extract_text(self) -> str:
            return "x" * (MAX_CV_TEXT_CHARS + 1)

    class _OversizedReader:
        pages = [_OversizedPage()]

    monkeypatch.setattr(
        "app.modules.individual_learning.cv_extractor.pypdf.PdfReader",
        lambda *_args, **_kwargs: _OversizedReader(),
    )

    with pytest.raises(ValueError, match="CV text exceeds the character limit"):
        extract_cv_text(
            filename="cv.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.7",
        )


def test_extract_cv_text_accepts_pdf_at_page_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoundaryPage:
        def extract_text(self) -> str:
            return "supported"

    class _BoundaryReader:
        pages = [_BoundaryPage() for _ in range(MAX_CV_PDF_PAGES)]

    monkeypatch.setattr(
        "app.modules.individual_learning.cv_extractor.pypdf.PdfReader",
        lambda *_args, **_kwargs: _BoundaryReader(),
    )

    text = extract_cv_text(
        filename="cv.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.7",
    )

    assert len(text.split()) == MAX_CV_PDF_PAGES


def test_extract_cv_text_rejects_docx_over_archive_entry_limit() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "<document />")
        for index in range(MAX_DOCX_ARCHIVE_ENTRIES):
            archive.writestr(f"word/extra-{index}.xml", "<extra />")

    with pytest.raises(ValueError, match="DOCX CV exceeds safe archive limits"):
        extract_cv_text(
            filename="cv.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            data=buffer.getvalue(),
        )


def test_extract_cv_text_accepts_docx_at_archive_entry_limit() -> None:
    cv_text = " ".join(f"skill-{index}" for index in range(20))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                'wordprocessingml/2006/main">'
                f"<w:body><w:p><w:r><w:t>{cv_text}</w:t></w:r></w:p>"
                "</w:body></w:document>"
            ),
        )
        for index in range(MAX_DOCX_ARCHIVE_ENTRIES - 1):
            archive.writestr(f"word/extra-{index}.xml", "<extra />")

    text = extract_cv_text(
        filename="cv.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        data=buffer.getvalue(),
    )

    assert text == cv_text


def test_extract_cv_text_rejects_docx_uncompressed_expansion_limit() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            b"x" * (MAX_DOCX_UNCOMPRESSED_BYTES + 1),
        )

    with pytest.raises(ValueError, match="DOCX CV exceeds safe archive limits"):
        extract_cv_text(
            filename="cv.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            data=buffer.getvalue(),
        )


def test_extract_cv_text_rejects_docx_text_over_character_limit() -> None:
    with pytest.raises(ValueError, match="CV text exceeds the character limit"):
        extract_cv_text(
            filename="cv.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            data=_docx_bytes("x" * (MAX_CV_TEXT_CHARS + 1)),
        )


def test_structured_cv_extractor_uses_cv_profile_schema_and_validates_output() -> None:
    captured: dict[str, object] = {}

    class FakeLLM:
        def with_structured_output(self, schema, *, method: str):
            captured["schema"] = schema
            captured["method"] = method
            return RunnableLambda(self._respond)

        @staticmethod
        def _respond(prompt):
            captured["prompt"] = prompt.to_string()
            return {
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
    assert "Never use -1" in captured["prompt"]
    assert "use 0 when confidence is unknown" in captured["prompt"]
    assert extractor.model_provider == "test-provider"
    assert extractor.model_name == "test-model"


def test_structured_cv_extractor_normalizes_provider_confidence_values() -> None:
    class FakeLLM:
        def with_structured_output(self, _schema, *, method: str):
            assert method == "function_calling"
            return RunnableLambda(
                lambda _prompt: {
                    "summary": "Backend engineer",
                    "skills": [
                        {"name": "Negative sentinel", "confidence": -1},
                        {"name": "Too high", "confidence": 1.5},
                        {"name": "Low confidence", "confidence": 0.2},
                        {"name": "Unknown confidence", "confidence": "unknown"},
                    ],
                    "confidence_summary": {
                        "negative": -0.3,
                        "too_high": 2,
                        "not_a_number": float("nan"),
                        "positive_infinity": float("inf"),
                        "negative_infinity": float("-inf"),
                        "low": 0.1,
                        "unknown": None,
                    },
                }
            )

    extractor = StructuredCVProfileExtractor(
        llm_factory=lambda: FakeLLM(),
        model_provider="test-provider",
        model_name="test-model",
    )

    result = extractor.extract("CV text with provider confidence sentinels")

    assert [skill.confidence for skill in result.skills] == [0.0, 1.0, 0.2, 0.0]
    assert result.confidence_summary == {
        "negative": 0.0,
        "too_high": 1.0,
        "not_a_number": 0.0,
        "positive_infinity": 0.0,
        "negative_infinity": 0.0,
        "low": 0.1,
        "unknown": 0.0,
    }


@pytest.mark.parametrize(
    "invalid_output",
    [
        {"summary": {"unexpected": "object"}},
        {
            "summary": "Backend engineer",
            "skills": [{"name": {"unexpected": "object"}, "confidence": 0.8}],
        },
    ],
)
def test_structured_cv_extractor_rejects_invalid_non_confidence_fields(
    invalid_output: dict[str, object],
) -> None:
    class FakeLLM:
        def with_structured_output(self, _schema, *, method: str):
            assert method == "function_calling"
            return RunnableLambda(lambda _prompt: invalid_output)

    extractor = StructuredCVProfileExtractor(
        llm_factory=lambda: FakeLLM(),
        model_provider="test-provider",
        model_name="test-model",
    )

    with pytest.raises(ValidationError):
        extractor.extract("CV text with malformed non-confidence fields")
