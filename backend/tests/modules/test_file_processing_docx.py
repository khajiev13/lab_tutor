import io
import zipfile

import pytest

from app.modules.courses.file_processing import handle_docx_bytes, infer_file_kind


def _make_minimal_docx_bytes(text: str) -> bytes:
    # Minimal WordprocessingML payload (just enough for our parser):
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def test_infer_file_kind_docx():
    assert infer_file_kind(filename="lecture.docx", content_type=None).kind == "docx"


def test_handle_docx_bytes_extracts_text():
    data = _make_minimal_docx_bytes("Hello DOCX")
    assert handle_docx_bytes(data) == "Hello DOCX"


def test_handle_docx_bytes_invalid_raises():
    with pytest.raises(ValueError):
        handle_docx_bytes(b"not-a-zip")
