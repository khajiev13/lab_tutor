"""Utility / helper functions for the book-selection workflow."""

from __future__ import annotations

import json
import re as _re
from difflib import SequenceMatcher

from langchain_core.messages import AIMessage, ToolMessage

from .workflow_models import DEFAULT_W_PRAC, DEFAULT_WEIGHTS

# ═══════════════════════════════════════════════════════════════
# Course context helpers
# ═══════════════════════════════════════════════════════════════


def course_summary(ctx: dict, course_level: str = "bachelor") -> str:
    """One-paragraph course overview for LLM prompts."""
    c = ctx.get("course", {})
    docs = ctx.get("documents", [])
    keywords: list[str] = []
    for d in docs:
        keywords.extend(d.get("keywords", []))
    unique_kw = list(dict.fromkeys(keywords))[:40]
    return (
        f"Course: {c.get('title', '?')}\n"
        f"Academic Level: {course_level.upper()}\n"
        f"Description: {c.get('description', 'N/A')}\n"
        f"Keywords ({len(unique_kw)}): {', '.join(unique_kw)}"
    )


def syllabus_sequence(ctx: dict) -> str:
    """Numbered lecture list with source_filename + keywords."""
    docs = ctx.get("documents", [])
    if not docs:
        return "(no documents)"
    lines: list[str] = []
    for i, d in enumerate(docs, 1):
        title = d.get("title", "Untitled")
        kw = d.get("keywords", [])
        fn = d.get("source_filename", "")
        kw_str = ", ".join(str(k) for k in kw[:8])
        prefix = f"[{fn}] " if fn else ""
        lines.append(f"  {i:>2}. {prefix}{title}  →  {kw_str}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Tool execution helper
# ═══════════════════════════════════════════════════════════════


def exec_tools(ai_msg: AIMessage, tools_by_name: dict) -> list[ToolMessage]:
    """Execute tool calls from an AIMessage and return ToolMessages."""
    results: list[ToolMessage] = []
    for tc in getattr(ai_msg, "tool_calls", []):
        tool_name = tc.get("name", "")
        tool = tools_by_name.get(tool_name)
        tool_call_id = tc.get("id", tool_name)
        if tool is None:
            results.append(
                ToolMessage(
                    content=json.dumps({"ok": False, "error": f"Unknown tool: {tool_name}"}),
                    tool_call_id=tool_call_id,
                )
            )
            continue
        observation = tool.invoke(tc.get("args", {}))
        results.append(ToolMessage(content=observation, tool_call_id=tool_call_id))
    return results


# ═══════════════════════════════════════════════════════════════
# Deduplication helpers
# ═══════════════════════════════════════════════════════════════


def normalize_title(title: str) -> str:
    """Lowercase, strip edition/subtitle noise, collapse whitespace."""
    t = title.lower().strip()
    t = _re.sub(r"\(?\d+\w{0,2}\s*(edition|ed\.?)\)?", "", t)
    t = _re.sub(r"[^\w\s]", " ", t)
    t = _re.sub(r"\s+", " ", t).strip()
    return t


def titles_match(a: str, b: str, threshold: float = 0.82) -> bool:
    """Fuzzy title match using SequenceMatcher."""
    na, nb = normalize_title(a), normalize_title(b)
    if na == nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def pick_best_entry(entries: list[dict]) -> dict:
    """Among duplicate entries, keep the one with the most complete metadata."""

    def _completeness(e: dict) -> tuple:
        filled = sum(
            1
            for k in ("title", "authors", "publisher", "year", "reason")
            if e.get(k)
        )
        try:
            yr = int(e.get("year", "0"))
        except (ValueError, TypeError):
            yr = 0
        reason_len = len(e.get("reason", ""))
        return (filled, yr, reason_len)

    return max(entries, key=_completeness)


# ═══════════════════════════════════════════════════════════════
# Scoring computation
# ═══════════════════════════════════════════════════════════════


def compute_finals(
    scores: dict,
    weights: dict[str, float] | None = None,
    w_prac: float | None = None,
) -> tuple[float, float]:
    """Return (S_final, S_final_with_practicality)."""
    w = weights or DEFAULT_WEIGHTS
    wp = w_prac if w_prac is not None else DEFAULT_W_PRAC
    s_base = sum(w.get(k, 0) * scores.get(k, 0) for k in w)
    s_prac = (1 - wp) * s_base + wp * scores.get("C_prac", 0)
    return round(s_base, 4), round(s_prac, 4)
