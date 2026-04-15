from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import subprocess
import tempfile
import time
from pathlib import Path


elements: list[dict] = []
elements_by_id: dict[str, dict] = {}
files: dict[str, dict] = {}
seed = 1000
nonce = 5000


BLACK = "#111111"
DARK = "#2f2f2f"
MID = "#5f5f5f"
LIGHT = "#9a9a9a"
WHITE = "#ffffff"
PALE = "#f7f7f7"
TINT_BLUE = "#f6f8fb"
TINT_WARM = "#fcfaf4"
TINT_GREEN = "#f5fbf6"
TINT_LILAC = "#f7f5fb"
TINT_ROSE = "#fff6f4"
TINT_SAND = "#fcf7ee"
MONO = 3

ANCHORS = {
    "top": [0.5, 0],
    "bottom": [0.5, 1],
    "left": [0, 0.5],
    "right": [1, 0.5],
}


def add(element: dict) -> None:
    global seed, nonce
    merged = {
        "angle": 0,
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": seed,
        "version": 1,
        "versionNonce": nonce,
        "isDeleted": False,
        "updated": 1,
        "link": None,
        "locked": False,
        **element,
    }
    elements.append(merged)
    if merged.get("id"):
        elements_by_id[merged["id"]] = merged
    seed += 1
    nonce += 1


def text_metrics(text: str, font_size: int) -> tuple[int, int]:
    lines = text.split("\n")
    longest = max((len(line) for line in lines), default=1)
    width = max(80, int(longest * font_size * 0.62))
    height = max(font_size + 4, int(len(lines) * font_size * 1.25))
    return width, height


def text_baseline(font_size: int) -> int:
    return max(8, int(round(font_size * 0.875)))


def ensure_bound_element(host_id: str, bound_type: str, target_id: str) -> None:
    host = elements_by_id[host_id]
    if host.get("boundElements") is None:
        host["boundElements"] = []
    existing = {(item["type"], item["id"]) for item in host["boundElements"]}
    if (bound_type, target_id) not in existing:
        host["boundElements"].append({"type": bound_type, "id": target_id})


def add_text(id_: str, x: int, y: int, text: str, **opts) -> None:
    font_size = opts.get("fontSize", 12)
    width, height = text_metrics(text, font_size)
    add(
        {
            "id": id_,
            "type": "text",
            "x": x,
            "y": y,
            "width": opts.get("width", width),
            "height": opts.get("height", height),
            "strokeColor": opts.get("strokeColor", DARK),
            "backgroundColor": "transparent",
            "boundElements": None,
            "text": text,
            "fontSize": font_size,
            "fontFamily": opts.get("fontFamily", MONO),
            "textAlign": opts.get("textAlign", "center"),
            "verticalAlign": opts.get("verticalAlign", "middle"),
            "baseline": opts.get("baseline", text_baseline(font_size)),
            "containerId": opts.get("containerId"),
            "originalText": text,
            "lineHeight": 1.25,
        }
    )


def add_bound_text(container_id: str, text: str, **opts) -> None:
    container = elements_by_id[container_id]
    padding_x = opts.get("paddingX", 12)
    padding_y = opts.get("paddingY", 10)
    text_width = container["width"] - padding_x * 2
    text_height_limit = container["height"] - padding_y * 2
    requested_font_size = opts.get("fontSize", 12)
    min_font_size = opts.get("minFontSize", 10)
    font_size = requested_font_size
    text_height = text_metrics(text, font_size)[1]

    while font_size > min_font_size:
        measured_width, measured_height = text_metrics(text, font_size)
        if measured_width <= text_width and measured_height <= text_height_limit:
            text_height = measured_height
            break
        font_size -= 1
        text_height = text_metrics(text, font_size)[1]

    text_height = min(text_height, text_height_limit)
    add_text(
        f"{container_id}-text",
        container["x"] + padding_x,
        int(container["y"] + (container["height"] - text_height) / 2),
        text,
        containerId=container_id,
        width=text_width,
        height=text_height,
        fontSize=font_size,
        strokeColor=opts.get("strokeColor", DARK),
        fontFamily=opts.get("fontFamily", MONO),
        textAlign=opts.get("textAlign", "center"),
    )


def rect(id_: str, x: int, y: int, width: int, height: int, text: str = "", **opts) -> None:
    add(
        {
            "id": id_,
            "type": "rectangle",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "strokeColor": opts.get("strokeColor", DARK),
            "backgroundColor": opts.get("backgroundColor", WHITE),
            "strokeWidth": opts.get("strokeWidth", 2),
            "strokeStyle": opts.get("strokeStyle", "solid"),
            "roundness": {"type": opts.get("roundnessType", 3)},
            "boundElements": [{"type": "text", "id": f"{id_}-text"}] if text else None,
        }
    )
    if text:
        add_bound_text(
            id_,
            text,
            fontSize=opts.get("fontSize", 12),
            strokeColor=opts.get("textColor", DARK),
            fontFamily=opts.get("fontFamily", MONO),
            textAlign=opts.get("textAlign", "center"),
        )


def resolve_anchor(anchor: str | tuple[float, float] | list[float]) -> list[float]:
    if isinstance(anchor, str):
        return list(ANCHORS[anchor])
    return [float(anchor[0]), float(anchor[1])]


def anchor_coords(element_id: str, anchor: str | tuple[float, float] | list[float]) -> list[int]:
    element = elements_by_id[element_id]
    rel_x, rel_y = resolve_anchor(anchor)
    return [
        int(round(element["x"] + element["width"] * rel_x)),
        int(round(element["y"] + element["height"] * rel_y)),
    ]


def connect(
    id_: str,
    start: tuple[str, str | tuple[float, float] | list[float]],
    end: tuple[str, str | tuple[float, float] | list[float]],
    via: list[tuple[int, int]] | None = None,
    **opts,
) -> None:
    start_id, start_anchor = start
    end_id, end_anchor = end
    points = [anchor_coords(start_id, start_anchor)]
    points.extend([[vx, vy] for vx, vy in (via or [])])
    points.append(anchor_coords(end_id, end_anchor))

    min_x = min(px for px, _ in points)
    max_x = max(px for px, _ in points)
    min_y = min(py for _, py in points)
    max_y = max(py for _, py in points)

    add(
        {
            "id": id_,
            "type": "arrow",
            "x": min_x,
            "y": min_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
            "strokeColor": opts.get("strokeColor", MID),
            "backgroundColor": "transparent",
            "strokeWidth": opts.get("strokeWidth", 2),
            "strokeStyle": opts.get("strokeStyle", "solid"),
            "points": [[px - min_x, py - min_y] for px, py in points],
            "lastCommittedPoint": None,
            "startBinding": {
                "elementId": start_id,
                "focus": 0,
                "gap": opts.get("startGap", 1),
                "fixedPoint": resolve_anchor(start_anchor),
            },
            "endBinding": {
                "elementId": end_id,
                "focus": 0,
                "gap": opts.get("endGap", 1),
                "fixedPoint": resolve_anchor(end_anchor),
            },
            "startArrowhead": opts.get("startArrowhead"),
            "endArrowhead": None if opts.get("endArrowhead") is False else "arrow",
            "elbowed": opts.get("elbowed", True),
        }
    )
    ensure_bound_element(start_id, "arrow", id_)
    ensure_bound_element(end_id, "arrow", id_)


def label(id_: str, x: int, y: int, text: str, **opts) -> None:
    add_text(
        id_,
        x,
        y,
        text,
        fontSize=opts.get("fontSize", 12),
        width=opts.get("width", 180),
        strokeColor=opts.get("strokeColor", MID),
        textAlign=opts.get("textAlign", "center"),
    )


def panel(
    id_: str,
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    subtitle: str,
    background_color: str = "transparent",
) -> None:
    rect(
        id_,
        x,
        y,
        width,
        height,
        "",
        strokeColor=LIGHT,
        backgroundColor=background_color,
        strokeStyle="dashed",
        strokeWidth=1,
    )
    add_text(
        f"{id_}-title",
        x + 18,
        y + 12,
        title,
        fontSize=22,
        width=width - 36,
        strokeColor=BLACK,
        textAlign="left",
    )
    add_text(
        f"{id_}-subtitle",
        x + 18,
        y + 36,
        subtitle,
        fontSize=14,
        width=width - 36,
        strokeColor=MID,
        textAlign="left",
    )


def cluster(
    id_: str,
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    subtitle: str = "",
    *,
    background_color: str = TINT_BLUE,
    stroke_color: str = LIGHT,
    stroke_style: str = "solid",
) -> None:
    rect(
        id_,
        x,
        y,
        width,
        height,
        "",
        strokeColor=stroke_color,
        backgroundColor=background_color,
        strokeStyle=stroke_style,
        strokeWidth=1,
    )
    add_text(
        f"{id_}-title",
        x + 16,
        y + 12,
        title,
        fontSize=13,
        width=width - 32,
        strokeColor=BLACK,
        textAlign="left",
    )
    if subtitle:
        add_text(
            f"{id_}-subtitle",
            x + 16,
            y + 30,
            subtitle,
            fontSize=11,
            width=width - 32,
            strokeColor=MID,
            textAlign="left",
        )


def load_schema_png_bytes(source: Path) -> bytes:
    gray_profile = Path("/System/Library/ColorSync/Profiles/Generic Gray Profile.icc")
    if gray_profile.exists():
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            result = subprocess.run(
                [
                    "sips",
                    "--matchTo",
                    str(gray_profile),
                    str(source),
                    "--out",
                    str(tmp_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and tmp_path.exists():
                return tmp_path.read_bytes()
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
    return source.read_bytes()


def register_embedded_image(source: Path) -> tuple[str, str]:
    image_bytes = load_schema_png_bytes(source)
    file_id = hashlib.sha1(image_bytes).hexdigest()
    mime_type = mimetypes.guess_type(source.name)[0] or "image/png"
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    ts = int(time.time() * 1000)
    files[file_id] = {
        "mimeType": mime_type,
        "id": file_id,
        "dataURL": data_url,
        "created": ts,
        "lastRetrieved": ts,
    }
    return file_id, mime_type


def image_element(id_: str, x: int, y: int, width: int, height: int, file_id: str, **opts) -> None:
    add(
        {
            "id": id_,
            "type": "image",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "strokeColor": "transparent",
            "backgroundColor": "transparent",
            "strokeWidth": opts.get("strokeWidth", 1),
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": opts.get("opacity", 72),
            "boundElements": [],
            "status": "saved",
            "fileId": file_id,
            "scale": [1, 1],
            "crop": None,
        }
    )


schema_path = Path(__file__).resolve().parents[1] / "conference_paper" / "database_schema.png"
schema_file_id, _ = register_embedded_image(schema_path)


add_text(
    "title",
    330,
    18,
    "Lab Tutor Multi-Agent Framework Around the Shared Knowledge Graph",
    fontSize=28,
    width=1700,
    strokeColor=BLACK,
)

add_text(
    "subtitle",
    300,
    54,
    "Paper-oriented grayscale view: the central image is the full graph schema, while the surrounding agents summarize the implemented enrichment logic and swarm topology.",
    fontSize=13,
    width=1760,
    strokeColor=MID,
)

add_text(
    "ops-note",
    500,
    88,
    "Outside the graph, PostgreSQL stores workflow state and checkpoints; Azure Blob stores uploaded course files and resolved book PDFs.",
    fontSize=12,
    width=1300,
    strokeColor=MID,
)

label(
    "line-legend",
    1840,
    90,
    "solid = production flow  |  dashed = subsystem / HITL / re-entry",
    width=360,
    strokeColor=MID,
    textAlign="right",
    fontSize=12,
)


# Top: Curricular Alignment Architect
panel(
    "caa-group",
    280,
    138,
    1680,
    282,
    "Curricular Alignment Architect",
    "Teacher-side textbook enrichment with explicit review before PDF acquisition and downstream skill publication.",
    background_color=TINT_WARM,
)

caa_boxes = [
    (
        "caa-1",
        340,
        228,
        280,
        118,
        "Discover\nfetch_course + queries\nsearch + dedup",
        "solid",
        2,
    ),
    (
        "caa-2",
        640,
        228,
        280,
        118,
        "Score\nscore_book (ReAct)\nweighted ranking",
        "solid",
        2,
    ),
    (
        "caa-3",
        940,
        228,
        220,
        118,
        "HITL review\nhitl_review interrupt\nteacher selects books",
        "dashed",
        2,
    ),
    (
        "caa-4",
        1180,
        228,
        330,
        118,
        "Acquire + extract\nselect + download\nextract_pdf | chunk+embed\nchapter_worker x5",
        "solid",
        2,
    ),
    (
        "caa-5",
        1530,
        228,
        370,
        118,
        "Publish skill bank\nbook_skill_mapping_graph\nBOOK_SKILL + MAPPED_TO",
        "solid",
        2,
    ),
]

for box_id, x, y, w, h, text, style, stroke_width in caa_boxes:
    rect(
        box_id,
        x,
        y,
        w,
        h,
        text,
        strokeColor=DARK,
        backgroundColor=WHITE,
        strokeStyle=style,
        strokeWidth=stroke_width,
        textColor=BLACK,
        fontSize=15,
    )

for idx in range(len(caa_boxes) - 1):
    connect(
        f"caa-flow-{idx}",
        (caa_boxes[idx][0], "right"),
        (caa_boxes[idx + 1][0], "left"),
        strokeColor=BLACK,
        strokeWidth=2,
    )


# Center: unified graph schema image
add_text(
    "kg-title",
    760,
    424,
    "Unified Neo4j Knowledge Graph",
    fontSize=24,
    width=760,
    strokeColor=BLACK,
)

add_text(
    "kg-subtitle",
    700,
    450,
    "Full schema image, muted for paper use. Visible families: course backbone | book skill bank | market skill bank | resource layer.",
    fontSize=13,
    width=880,
    strokeColor=MID,
)

image_element(
    "kg-schema-image",
    640,
    492,
    1000,
    595,
    schema_file_id,
    opacity=72,
)

label(
    "kg-note",
    720,
    1100,
    "Schema stays literal in the center; surrounding agents explain how each region is populated and reused.",
    width=840,
    strokeColor=MID,
    fontSize=13,
)


# Left: Textual Resource Analyst
panel(
    "tra-group",
    38,
    470,
    500,
    660,
    "Textual Resource Analyst",
    "Implemented service. Current production path is downstream via the Student Learning Path worker, not a standalone teacher-facing route.",
    background_color=TINT_BLUE,
)

tra_boxes = [
    (
        "tra-1",
        78,
        566,
        420,
        86,
        "Context\nselected skill\nsummary + concepts",
    ),
    (
        "tra-2",
        78,
        686,
        420,
        94,
        "Query + search\nprocess_single_skill\nqueries | search_for_skill",
    ),
    (
        "tra-3",
        78,
        814,
        420,
        94,
        "Rank + select\nembedding_filter\nscore + coverage select",
    ),
    (
        "tra-4",
        78,
        942,
        420,
        82,
        "Persist readings\nwrite_resources\nHAS_READING",
    ),
]

for box_id, x, y, w, h, text in tra_boxes:
    rect(
        box_id,
        x,
        y,
        w,
        h,
        text,
        strokeColor=DARK,
        backgroundColor=WHITE,
        textColor=BLACK,
        fontSize=15,
    )

for idx in range(len(tra_boxes) - 1):
    connect(
        f"tra-flow-{idx}",
        (tra_boxes[idx][0], "bottom"),
        (tra_boxes[idx + 1][0], "top"),
        strokeColor=BLACK,
        strokeWidth=2,
    )


# Right: Market Demand Analyst
panel(
    "mda-group",
    1738,
    430,
    590,
    760,
    "Market Demand Analyst",
    "Implemented as a 5-agent LangGraph swarm plus a non-agent extraction subgraph, with the Supervisor handling re-entry and final teacher-facing control.",
    background_color=TINT_BLUE,
)

rect(
    "mda-hitl",
    1778,
    496,
    510,
    44,
    "HITL checkpoints: search terms | job-group | skill curation",
    strokeColor=MID,
    backgroundColor=TINT_ROSE,
    strokeStyle="dashed",
    strokeWidth=2,
    textColor=DARK,
    fontSize=14,
)

rect(
    "mda-swarm",
    1778,
    570,
    506,
    526,
    "",
    strokeColor=LIGHT,
    backgroundColor=WHITE,
    strokeStyle="dashed",
    strokeWidth=1,
)

add_text(
    "mda-swarm-title",
    1792,
    578,
    "Swarm enclosure",
    fontSize=12,
    width=120,
    strokeColor=MID,
    textAlign="left",
)

rect(
    "mda-skillfinder",
    1800,
    664,
    164,
    92,
    "Skill Finder\nfetch_jobs\nselect_jobs\nstart_extraction",
    strokeColor=DARK,
    backgroundColor=WHITE,
    textColor=BLACK,
    fontSize=15,
)

add_text(
    "mda-extractor-note",
    1948,
    650,
    "child extraction subgraph",
    fontSize=10,
    width=160,
    strokeColor=MID,
)

rect(
    "mda-extractor",
    1962,
    674,
    138,
    74,
    "skill_extractor\nextract_one x jobs\nmerge + normalize",
    strokeColor=MID,
    backgroundColor=PALE,
    strokeStyle="dashed",
    textColor=DARK,
    fontSize=13,
)

rect(
    "mda-mapper",
    2100,
    664,
    164,
    92,
    "Curriculum Mapper\nlist_chapters\ndetails + coverage",
    strokeColor=DARK,
    backgroundColor=WHITE,
    textColor=BLACK,
    fontSize=15,
)

rect(
    "mda-supervisor",
    1941,
    820,
    180,
    92,
    "Supervisor\nsave/delete skills\nshow_state + handoff_*",
    strokeColor=BLACK,
    backgroundColor=TINT_BLUE,
    strokeWidth=3,
    textColor=BLACK,
    fontSize=15,
)

rect(
    "mda-linker",
    1792,
    952,
    180,
    90,
    "Concept Linker\nextract_concepts\ninsert_market_skills",
    strokeColor=DARK,
    backgroundColor=WHITE,
    textColor=BLACK,
    fontSize=15,
)

rect(
    "mda-cleaner",
    2092,
    952,
    172,
    90,
    "Skill Cleaner\nload skills\ncompare_and_clean",
    strokeColor=DARK,
    backgroundColor=WHITE,
    textColor=BLACK,
    fontSize=15,
)

rect(
    "mda-evidence",
    1850,
    1118,
    362,
    36,
    "External evidence: Indeed + LinkedIn job postings",
    strokeColor=LIGHT,
    backgroundColor=TINT_WARM,
    strokeWidth=1,
    textColor=MID,
    fontSize=12,
)

connect(
    "mda-forward-a",
    ("mda-skillfinder", "right"),
    ("mda-extractor", "left"),
    strokeColor=BLACK,
    strokeWidth=2,
)
connect(
    "mda-forward-b",
    ("mda-extractor", "right"),
    ("mda-mapper", "left"),
    strokeColor=BLACK,
    strokeWidth=2,
)
connect(
    "mda-forward-c",
    ("mda-mapper", "bottom"),
    ("mda-cleaner", "top"),
    strokeColor=BLACK,
    strokeWidth=2,
)
connect(
    "mda-forward-d",
    ("mda-cleaner", "left"),
    ("mda-linker", "right"),
    strokeColor=BLACK,
    strokeWidth=2,
)
connect(
    "mda-forward-e",
    ("mda-linker", "right"),
    ("mda-supervisor", "left"),
    via=[(1998, 997), (1998, 866)],
    strokeColor=BLACK,
    strokeWidth=2,
)

connect(
    "mda-reentry-a",
    ("mda-supervisor", [0.2, 0]),
    ("mda-skillfinder", "bottom"),
    via=[(1977, 804), (1878, 804), (1878, 756)],
    strokeColor=MID,
    strokeStyle="dashed",
    strokeWidth=2,
)
connect(
    "mda-reentry-b",
    ("mda-supervisor", [0.8, 0]),
    ("mda-mapper", "bottom"),
    via=[(2085, 804), (2186, 804), (2186, 756)],
    strokeColor=MID,
    strokeStyle="dashed",
    strokeWidth=2,
)
connect(
    "mda-reentry-c",
    ("mda-supervisor", [0.25, 1]),
    ("mda-linker", "top"),
    via=[(1986, 928), (1880, 928)],
    strokeColor=MID,
    strokeStyle="dashed",
    strokeWidth=2,
)
connect(
    "mda-reentry-d",
    ("mda-supervisor", [0.75, 1]),
    ("mda-cleaner", "top"),
    via=[(2076, 928), (2178, 928)],
    strokeColor=MID,
    strokeStyle="dashed",
    strokeWidth=2,
)

label(
    "mda-forward-label",
    1850,
    1158,
    "solid = forward chain",
    width=140,
    strokeColor=BLACK,
    fontSize=12,
)
label(
    "mda-reentry-label",
    2042,
    1158,
    "dashed = supervisor re-entry",
    width=170,
    strokeColor=MID,
    fontSize=12,
)


# Bottom: Video Agent
panel(
    "video-group",
    350,
    1238,
    1600,
    278,
    "Video Agent / Visual Content Evaluator",
    "Implemented service. Current production path is downstream via the Student Learning Path worker, using video-focused retrieval and canonical YouTube resolution.",
    background_color=TINT_WARM,
)

video_boxes = [
    (
        "video-1",
        394,
        1326,
        250,
        108,
        "Context\nselected skill\nsummary + concepts",
    ),
    (
        "video-2",
        664,
        1326,
        250,
        108,
        "Query + search\nprocess_single_skill\ngenerate + search",
    ),
    (
        "video-3",
        934,
        1326,
        250,
        108,
        "Resolve videos\nresolve_embedded_video_candidates\ncanonical YouTube",
    ),
    (
        "video-4",
        1204,
        1326,
        250,
        108,
        "Rank + select\nembedding_filter\ncoverage-max select",
    ),
    (
        "video-5",
        1474,
        1326,
        250,
        108,
        "Persist videos\nwrite_resources\nHAS_VIDEO",
    ),
]

for box_id, x, y, w, h, text in video_boxes:
    rect(
        box_id,
        x,
        y,
        w,
        h,
        text,
        strokeColor=DARK,
        backgroundColor=WHITE,
        textColor=BLACK,
        fontSize=15,
    )

for idx in range(len(video_boxes) - 1):
    connect(
        f"video-flow-{idx}",
        (video_boxes[idx][0], "right"),
        (video_boxes[idx + 1][0], "left"),
        strokeColor=BLACK,
        strokeWidth=2,
    )


# Cross-panel connections
connect(
    "kg-to-caa",
    ("kg-schema-image", [0.48, 0]),
    ("caa-1", "bottom"),
    via=[(1120, 432), (480, 432)],
    strokeColor=MID,
    strokeWidth=2,
)
label(
    "kg-to-caa-label",
    900,
    398,
    "reads course chapters + concepts",
    width=180,
    strokeColor=MID,
    fontSize=12,
)

connect(
    "caa-to-kg",
    ("caa-5", "bottom"),
    ("kg-schema-image", [0.66, 0]),
    via=[(1715, 438), (1300, 438)],
    strokeColor=BLACK,
    strokeWidth=3,
)
label(
    "caa-to-kg-label",
    1420,
    340,
    "writes book-side structure + skill bank",
    width=220,
    strokeColor=BLACK,
    fontSize=12,
)

connect(
    "kg-to-mda",
    ("kg-schema-image", [1, 0.42]),
    ("mda-skillfinder", "left"),
    via=[(1740, 742), (1740, 679)],
    strokeColor=MID,
    strokeWidth=2,
)
label(
    "kg-to-mda-label",
    1680,
    636,
    "reads chapters,\nconcepts,\nexisting skills",
    width=110,
    strokeColor=MID,
    fontSize=12,
)

connect(
    "mda-to-kg",
    ("mda-linker", "left"),
    ("kg-schema-image", [1, 0.71]),
    via=[(1754, 1009), (1754, 915)],
    strokeColor=BLACK,
    strokeWidth=3,
)
label(
    "mda-to-kg-label",
    1634,
    914,
    "writes MARKET_SKILL,\nJOB_POSTING,\nMAPPED_TO",
    width=140,
    strokeColor=BLACK,
    fontSize=12,
)

connect(
    "kg-to-tra",
    ("kg-schema-image", [0, 0.44]),
    ("tra-1", "right"),
    via=[(560, 754), (560, 609)],
    strokeColor=MID,
    strokeWidth=2,
)
label(
    "kg-to-tra-label",
    430,
    700,
    "selected skill context",
    width=140,
    strokeColor=MID,
    fontSize=12,
)

connect(
    "tra-to-kg",
    ("tra-4", "right"),
    ("kg-schema-image", [0, 0.76]),
    via=[(568, 983), (568, 944)],
    strokeColor=BLACK,
    strokeWidth=3,
)
label(
    "tra-to-kg-label",
    430,
    1000,
    "HAS_READING",
    width=100,
    strokeColor=BLACK,
    fontSize=12,
)

connect(
    "kg-to-video",
    ("kg-schema-image", [0.5, 1]),
    ("video-1", "top"),
    via=[(1140, 1183), (519, 1183)],
    strokeColor=MID,
    strokeWidth=2,
)
label(
    "kg-to-video-label",
    908,
    1138,
    "selected skill context",
    width=150,
    strokeColor=MID,
    fontSize=12,
)

connect(
    "video-to-kg",
    ("video-5", "top"),
    ("kg-schema-image", [0.5, 1]),
    via=[(1599, 1186)],
    strokeColor=BLACK,
    strokeWidth=3,
)
label(
    "video-to-kg-label",
    1494,
    1188,
    "HAS_VIDEO",
    width=90,
    strokeColor=BLACK,
    fontSize=12,
)


diagram = {
    "type": "excalidraw",
    "version": 2,
    "source": "codex-generate_agents_diagram",
    "elements": elements,
    "appState": {
        "gridSize": None,
        "viewBackgroundColor": WHITE,
    },
    "files": files,
}


out_path = Path(__file__).with_name("agents_diagram.excalidraw")
out_path.write_text(json.dumps(diagram, indent=2), encoding="utf-8")
print(f"Wrote {out_path}")
