#!/usr/bin/env python3
from __future__ import annotations

import html
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SVG_OUTPUT = ROOT / "system-architecture.svg"
PNG_OUTPUT = ROOT / "system-architecture.png"
WIDTH = 1800
HEIGHT = 1230


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def add_rect(parts: list[str], x: int, y: int, width: int, height: int, *, fill: str, stroke: str, rx: int = 28, stroke_width: int = 3) -> None:
    parts.append(
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
    )


def add_text(parts: list[str], x: int, y: int, text: str, *, size: int = 30, weight: str = "400", fill: str = "#0f172a", anchor: str = "start") -> None:
    parts.append(
        f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{esc(text)}</text>'
    )


def add_multiline_text(
    parts: list[str],
    x: int,
    y: int,
    lines: list[str],
    *,
    size: int = 24,
    weight: str = "400",
    fill: str = "#0f172a",
    anchor: str = "start",
    line_gap: int = 34,
) -> None:
    tspans: list[str] = []
    for idx, line in enumerate(lines):
        dy = "0" if idx == 0 else str(line_gap)
        tspans.append(f'<tspan x="{x}" dy="{dy}">{esc(line)}</tspan>')
    parts.append(
        f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{"".join(tspans)}</text>'
    )


def add_arrow(
    parts: list[str],
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    color: str = "#64748b",
    stroke_width: int = 6,
    bidirectional: bool = False,
) -> None:
    marker_start = ' marker-start="url(#arrow-start)"' if bidirectional else ""
    marker_end = ' marker-end="url(#arrow-end)"'
    parts.append(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
        f'stroke-width="{stroke_width}" stroke-linecap="round"{marker_start}{marker_end}/>'
    )


def add_task_box(
    parts: list[str],
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    accent_fill: str,
    border: str,
    badge: str,
    title: str,
    subtitle: str,
    lines: list[str],
) -> None:
    add_rect(parts, x, y, width, height, fill="#ffffff", stroke=border, rx=34)
    add_rect(parts, x + 26, y + 22, 140, 54, fill=accent_fill, stroke=border, rx=18, stroke_width=2)
    add_text(parts, x + 96, y + 57, badge, size=24, weight="700", fill=border, anchor="middle")
    add_text(parts, x + 30, y + 118, title, size=34, weight="700")
    add_text(parts, x + 30, y + 158, subtitle, size=24, weight="700", fill=border)
    add_multiline_text(parts, x + 30, y + 212, lines, size=24, line_gap=34)


def render_svg() -> str:
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        "<defs>",
        '<marker id="arrow-end" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">',
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/>',
        "</marker>",
        '<marker id="arrow-start" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">',
        '<path d="M 10 0 L 0 5 L 10 10 z" fill="#64748b"/>',
        "</marker>",
        "</defs>",
        '<rect width="100%" height="100%" fill="#fcfcfd"/>',
    ]

    add_text(parts, 900, 70, "Task-Level Multi-Agent Architecture", size=40, weight="700", anchor="middle")
    add_text(parts, 900, 108, "Task 1 builds the baseline scaffold, Tasks 2 and 3 enrich it independently, and Task 4 turns the enriched graph into learning support.", size=24, fill="#475569", anchor="middle")

    add_task_box(
        parts,
        x=360,
        y=150,
        width=1080,
        height=240,
        accent_fill="#dbeafe",
        border="#2563eb",
        badge="Task 1",
        title="Document Extraction",
        subtitle="Teacher-owned curriculum scaffold",
        lines=[
            "Input: teacher materials",
            "Output: course chapters, concepts, embeddings",
            "Review: concept/chapter review",
        ],
    )

    add_rect(parts, 590, 430, 620, 140, fill="#ecfeff", stroke="#0f766e", rx=34)
    add_text(parts, 900, 490, "Shared Neo4j Curriculum Graph", size=34, weight="700", fill="#0f766e", anchor="middle")
    add_text(parts, 900, 530, "Shared semantic substrate and coordination layer", size=24, fill="#115e59", anchor="middle")

    add_task_box(
        parts,
        x=80,
        y=640,
        width=720,
        height=270,
        accent_fill="#dcfce7",
        border="#15803d",
        badge="Task 2",
        title="Textbook Alignment",
        subtitle="Curricular Alignment Architect",
        lines=[
            "Input: approved books",
            "Output: mapped BOOK_SKILL layer",
            "Review: textbook approval",
        ],
    )

    add_task_box(
        parts,
        x=1000,
        y=640,
        width=720,
        height=270,
        accent_fill="#ffedd5",
        border="#c2410c",
        badge="Task 3",
        title="Market Alignment",
        subtitle="Market Demand Analyst",
        lines=[
            "Input: filtered job postings",
            "Output: mapped MARKET_SKILL layer",
            "Review: job relevance and skill curation",
        ],
    )

    add_task_box(
        parts,
        x=360,
        y=970,
        width=1080,
        height=200,
        accent_fill="#ede9fe",
        border="#6d28d9",
        badge="Task 4",
        title="Resource Curation",
        subtitle="Textual Resource Analyst + Video Agent",
        lines=[
            "Input: enriched skill set",
            "Output: readings, videos, questions",
            "Review: optional resource review",
        ],
    )

    add_arrow(parts, 900, 390, 900, 430)
    add_text(parts, 955, 420, "build baseline scaffold", size=21, fill="#475569")

    add_arrow(parts, 590, 570, 440, 640, bidirectional=True)
    add_text(parts, 420, 605, "shared read / write", size=21, fill="#475569", anchor="middle")

    add_arrow(parts, 1210, 570, 1360, 640, bidirectional=True)
    add_text(parts, 1380, 605, "shared read / write", size=21, fill="#475569", anchor="middle")

    add_arrow(parts, 900, 570, 900, 970)
    add_text(parts, 990, 790, "enriched skill bank", size=21, fill="#475569")

    add_text(parts, 900, 610, "Tasks 2 and 3 are independent enrichment paths that both map back into the same graph.", size=22, fill="#475569", anchor="middle")
    parts.append("</svg>")
    return "\n".join(parts)


def write_png(svg_path: Path, png_path: Path) -> None:
    if shutil.which("rsvg-convert"):
        subprocess.run(
            ["rsvg-convert", str(svg_path), "-o", str(png_path)],
            check=True,
        )
        return

    if shutil.which("qlmanage"):
        temp_dir = png_path.parent / ".qlmanage_tmp"
        temp_dir.mkdir(exist_ok=True)
        subprocess.run(
            ["qlmanage", "-t", "-s", "2000", "-o", str(temp_dir), str(svg_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        rendered = temp_dir / f"{svg_path.name}.png"
        if not rendered.exists():
            raise FileNotFoundError(rendered)
        png_path.write_bytes(rendered.read_bytes())
        for item in temp_dir.iterdir():
            item.unlink()
        temp_dir.rmdir()
        return

    raise RuntimeError("Neither rsvg-convert nor qlmanage is available to render the task overview figure.")


def main() -> None:
    svg = render_svg()
    SVG_OUTPUT.write_text(svg)
    write_png(SVG_OUTPUT, PNG_OUTPUT)


if __name__ == "__main__":
    main()
