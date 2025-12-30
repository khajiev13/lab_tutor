from __future__ import annotations

import io
import zipfile
from typing import Literal
from xml.etree import ElementTree as ET

from pydantic import BaseModel

FileKind = Literal["txt", "docx", "ppt", "other"]


class FileDispatchResult(BaseModel):
    kind: FileKind
    content_type: str | None


def infer_file_kind(*, filename: str, content_type: str | None) -> FileDispatchResult:
    name = (filename or "").lower().strip()
    ct = (content_type or "").lower().strip() or None

    if name.endswith(".txt") or ct == "text/plain":
        return FileDispatchResult(kind="txt", content_type=ct)

    if name.endswith(".docx") or ct in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        return FileDispatchResult(kind="docx", content_type=ct)

    if name.endswith((".ppt", ".pptx")) or (
        ct
        in {
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
    ):
        return FileDispatchResult(kind="ppt", content_type=ct)

    return FileDispatchResult(kind="other", content_type=ct)


def handle_txt_bytes(data: bytes) -> str:
    """Decode text bytes for an LLM pipeline. Returns decoded text."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def handle_docx_bytes(data: bytes) -> str:
    """Extract plain text from a .docx payload.

    We intentionally avoid extra dependencies (like python-docx) by reading the
    Office Open XML content directly.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml_bytes = zf.read("word/document.xml")
    except Exception as e:
        raise ValueError("Invalid docx file (cannot read word/document.xml)") from e

    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        raise ValueError("Invalid docx XML") from e

    texts: list[str] = []
    for node in root.iter():
        tag = node.tag
        if tag.endswith("}t") and node.text:
            texts.append(node.text)
        elif tag.endswith("}tab"):
            texts.append("\t")
        elif tag.endswith("}br") or tag.endswith("}cr") or tag.endswith("}p"):
            texts.append("\n")

    text = "".join(texts)
    # Normalize whitespace a bit
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()


def handle_ppt_bytes(data: bytes) -> None:
    """Placeholder for PPT/PPTX OCR pipeline.

    For now we just validate we can access bytes.
    """
    _ = data


def handle_other_bytes(data: bytes) -> None:
    """Placeholder for other formats."""
    _ = data
