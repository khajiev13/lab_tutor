from __future__ import annotations

import io

import pypdf

from app.modules.courses.file_processing import handle_docx_bytes

PDF_CONTENT_TYPES = {"application/pdf"}
DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}


def _extract_pdf_text(data: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
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
