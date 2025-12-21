from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileDispatchResult:
    kind: str  # "txt" | "ppt" | "other"
    content_type: str | None


def infer_file_kind(*, filename: str, content_type: str | None) -> FileDispatchResult:
    name = (filename or "").lower().strip()
    ct = (content_type or "").lower().strip() or None

    if name.endswith(".txt") or ct == "text/plain":
        return FileDispatchResult(kind="txt", content_type=ct)

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


def handle_ppt_bytes(data: bytes) -> None:
    """Placeholder for PPT/PPTX OCR pipeline.

    For now we just validate we can access bytes.
    """
    _ = data


def handle_other_bytes(data: bytes) -> None:
    """Placeholder for other formats."""
    _ = data
