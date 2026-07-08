import io
import zipfile

import pytest

from app.modules.individual_learning.cv_extractor import extract_cv_text


def _docx_bytes(text: str) -> bytes:
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main">'
        )
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
