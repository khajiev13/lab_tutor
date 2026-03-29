import fs from "node:fs";
import path from "node:path";

const elements = [];
let seed = 1;
let nonce = 1;

function add(element) {
  elements.push({
    angle: 0,
    fillStyle: "solid",
    strokeWidth: 1,
    strokeStyle: "solid",
    roughness: 0,
    opacity: 100,
    groupIds: [],
    frameId: null,
    roundness: null,
    seed: seed++,
    version: 1,
    versionNonce: nonce++,
    isDeleted: false,
    updated: 1,
    link: null,
    locked: false,
    ...element,
  });
}

function addText(id, x, y, text, opts = {}) {
  const fontSize = opts.fontSize ?? 12;
  const width =
    opts.width ??
    Math.max(
      60,
      Math.ceil(Math.max(...text.split("\n").map((line) => line.length)) * fontSize * 0.58),
    );
  const height = opts.height ?? Math.ceil(text.split("\n").length * fontSize * 1.25);

  add({
    id,
    type: "text",
    x,
    y,
    width,
    height,
    strokeColor: opts.strokeColor ?? "#1f2937",
    backgroundColor: "transparent",
    boundElements: null,
    text,
    fontSize,
    fontFamily: 1,
    textAlign: opts.textAlign ?? "center",
    verticalAlign: opts.verticalAlign ?? "middle",
    containerId: opts.containerId ?? null,
    originalText: text,
    lineHeight: 1.25,
  });
}

function rect(id, x, y, width, height, text = "", opts = {}) {
  add({
    id,
    type: "rectangle",
    x,
    y,
    width,
    height,
    strokeColor: opts.strokeColor ?? "#334155",
    backgroundColor: opts.backgroundColor ?? "#ffffff",
    strokeWidth: opts.strokeWidth ?? 2,
    strokeStyle: opts.strokeStyle ?? "solid",
    roundness: { type: 3 },
    boundElements: text ? [{ type: "text", id: `${id}-text` }] : null,
  });

  if (text) {
    addText(`${id}-text`, x + 8, y + 8, text, {
      containerId: id,
      width: width - 16,
      height: height - 16,
      fontSize: opts.fontSize ?? 10,
      strokeColor: opts.textColor ?? "#1f2937",
    });
  }
}

function arrow(id, x, y, points, opts = {}) {
  let minX = 0;
  let maxX = 0;
  let minY = 0;
  let maxY = 0;

  for (const [px, py] of points) {
    if (px < minX) minX = px;
    if (px > maxX) maxX = px;
    if (py < minY) minY = py;
    if (py > maxY) maxY = py;
  }

  add({
    id,
    type: "arrow",
    x: x + minX,
    y: y + minY,
    width: maxX - minX,
    height: maxY - minY,
    strokeColor: opts.strokeColor ?? "#64748b",
    backgroundColor: "transparent",
    strokeWidth: opts.strokeWidth ?? 2,
    strokeStyle: opts.strokeStyle ?? "solid",
    points: points.map(([px, py]) => [px - minX, py - minY]),
    lastCommittedPoint: null,
    startBinding: null,
    endBinding: null,
    startArrowhead: opts.startArrowhead ?? null,
    endArrowhead: opts.endArrowhead === false ? null : "arrow",
    elbowed: opts.elbowed ?? true,
  });
}

addText(
  "title",
  430,
  18,
  "Lab Tutor Agent Ecology for Curriculum Intelligence",
  { fontSize: 24, width: 940, strokeColor: "#0f172a" },
);
addText(
  "subtitle",
  450,
  54,
  "Current implementation state as of March 30, 2026: transcript-derived course chapters feed two central skill banks; readings and videos are curated downstream per selected skill.",
  { fontSize: 11, width: 900, strokeColor: "#475569" },
);

rect("group-top", 40, 96, 1720, 170, "", {
  strokeColor: "#94a3b8",
  backgroundColor: "#f8fafc",
  strokeStyle: "dashed",
  strokeWidth: 1,
});
addText("group-top-label", 58, 102, "Teacher-Curated Curriculum Backbone", {
  fontSize: 13,
  width: 280,
  strokeColor: "#334155",
  textAlign: "left",
});

rect(
  "teacher-docs",
  86,
  140,
  250,
  92,
  "Teacher course documents\nslides, transcripts, notes\nsource files in Azure Blob",
  {
    strokeColor: "#475569",
    backgroundColor: "#f8fafc",
    fontSize: 11,
    textColor: "#334155",
  },
);
rect(
  "doc-extract",
  404,
  132,
  330,
  110,
  "Document Extraction + Curriculum Planning\nparse teacher files\nextract topic, summary, concepts\nbuild course chapters + objectives",
  {
    strokeColor: "#2563eb",
    backgroundColor: "#dbeafe",
    fontSize: 11,
    textColor: "#1d4ed8",
  },
);
rect(
  "chapter-backbone",
  818,
  124,
  390,
  126,
  "Course Chapter Backbone\nCOURSE_CHAPTER nodes\nchapter titles, descriptions, learning objectives\nlinked teacher transcript documents",
  {
    strokeColor: "#1d4ed8",
    backgroundColor: "#eff6ff",
    strokeWidth: 3,
    fontSize: 12,
    textColor: "#1e3a8a",
  },
);
rect(
  "infra-strip",
  1296,
  146,
  404,
  80,
  "Persistent layer\nNeo4j knowledge graph + PostgreSQL checkpoints/status + Azure Blob PDFs",
  {
    strokeColor: "#64748b",
    backgroundColor: "#f8fafc",
    fontSize: 11,
    textColor: "#334155",
  },
);
arrow("a-top-1", 336, 186, [[0, 0], [68, 0]]);
arrow("a-top-2", 734, 186, [[0, 0], [84, 0]], { strokeColor: "#2563eb" });
arrow("a-top-3", 1208, 186, [[0, 0], [88, 0]]);

rect("group-left", 40, 308, 520, 492, "", {
  strokeColor: "#93c5fd",
  backgroundColor: "#f8fbff",
  strokeStyle: "dashed",
  strokeWidth: 1,
});
addText("group-left-label", 58, 314, "Curricular Alignment Architect", {
  fontSize: 13,
  width: 260,
  strokeColor: "#1d4ed8",
  textAlign: "left",
});
addText("group-left-sub", 58, 334, "Multi-phase LangGraph workflow", {
  fontSize: 10,
  width: 220,
  strokeColor: "#60a5fa",
  textAlign: "left",
});
rect(
  "caa-1",
  78,
  374,
  198,
  76,
  "1. Discover books\nLLM generates 10–12 queries\nparallel Google Books + Tavily\ndeduplicate titles",
  {
    strokeColor: "#2563eb",
    backgroundColor: "#dbeafe",
    fontSize: 10,
    textColor: "#1d4ed8",
  },
);
rect(
  "caa-2",
  78,
  470,
  198,
  82,
  "2. Research + score\nReAct evidence gathering\nweighted merit rubric\nrank candidate textbooks",
  {
    strokeColor: "#2563eb",
    backgroundColor: "#dbeafe",
    fontSize: 10,
    textColor: "#1d4ed8",
  },
);
rect("caa-hitl", 78, 572, 198, 62, "3. Teacher review\nselect up to 5 books", {
  strokeColor: "#ea580c",
  backgroundColor: "#fff7ed",
  strokeStyle: "dashed",
  fontSize: 10,
  textColor: "#9a3412",
});
rect(
  "caa-4",
  78,
  654,
  198,
  82,
  "4. Download + validate PDFs\nsearch mirrors\nretry failed links\nstore approved files",
  {
    strokeColor: "#2563eb",
    backgroundColor: "#dbeafe",
    fontSize: 10,
    textColor: "#1d4ed8",
  },
);
rect(
  "caa-5",
  312,
  392,
  206,
  82,
  "5. Chunking analysis\nextract chapters\nparagraph chunking\nembeddings + concept scoring",
  {
    strokeColor: "#2563eb",
    backgroundColor: "#dbeafe",
    fontSize: 10,
    textColor: "#1d4ed8",
  },
);
rect(
  "caa-6",
  312,
  492,
  206,
  92,
  "6. Chapter skill extraction\nLLM extracts BOOK_SKILLs\njudge + one revision pass\nwrite skills and concepts",
  {
    strokeColor: "#2563eb",
    backgroundColor: "#dbeafe",
    fontSize: 10,
    textColor: "#1d4ed8",
  },
);
rect(
  "caa-7",
  312,
  606,
  206,
  86,
  "7. Book-skill mapping\ncompare book skills against\nCOURSE_CHAPTER targets\npersist MAPPED_TO edges",
  {
    strokeColor: "#2563eb",
    backgroundColor: "#dbeafe",
    fontSize: 10,
    textColor: "#1d4ed8",
  },
);
addText(
  "caa-note",
  84,
  752,
  "Human checkpoint is implemented at book review; course-chapter mapping runs after transcript chapters already exist.",
  {
    fontSize: 10,
    width: 430,
    strokeColor: "#475569",
    textAlign: "left",
  },
);
arrow("caa-a1", 177, 450, [[0, 0], [0, 20]], { strokeColor: "#2563eb" });
arrow("caa-a2", 177, 552, [[0, 0], [0, 20]], {
  strokeColor: "#ea580c",
  strokeStyle: "dashed",
});
arrow("caa-a3", 177, 634, [[0, 0], [0, 20]], { strokeColor: "#2563eb" });
arrow("caa-a4", 276, 413, [[0, 0], [36, 0]], { strokeColor: "#2563eb" });
arrow("caa-a5", 415, 474, [[0, 0], [0, 18]], { strokeColor: "#2563eb" });
arrow("caa-a6", 415, 584, [[0, 0], [0, 22]], { strokeColor: "#2563eb" });
arrow("caa-top-link", 930, 250, [[0, 0], [-312, 0], [-312, 98]], {
  strokeColor: "#2563eb",
});
arrow("caa-top-link-2", 1012, 250, [[0, 0], [-290, 0], [-290, 356], [-494, 356]], {
  strokeColor: "#60a5fa",
  strokeStyle: "dashed",
});

rect("group-center", 600, 286, 600, 574, "", {
  strokeColor: "#cbd5e1",
  backgroundColor: "#fffef7",
  strokeStyle: "dashed",
  strokeWidth: 1,
});
addText("group-center-label", 618, 292, "Shared Curriculum Skill Layer", {
  fontSize: 13,
  width: 260,
  strokeColor: "#92400e",
  textAlign: "left",
});
addText(
  "group-center-sub",
  618,
  312,
  "Two middle banks used across teacher and student workflows",
  {
    fontSize: 10,
    width: 330,
    strokeColor: "#b45309",
    textAlign: "left",
  },
);
rect(
  "center-top",
  706,
  340,
  388,
  72,
  "Course chapters are the alignment target\nBoth skill banks are anchored to this chapter structure.",
  {
    strokeColor: "#64748b",
    backgroundColor: "#f8fafc",
    fontSize: 11,
    textColor: "#334155",
  },
);
rect(
  "book-bank",
  662,
  454,
  232,
  240,
  "Book Skill Bank\nchapter-scoped BOOK_SKILL nodes\nname + description\nlinked concepts\nteacher-facing tab in Curriculum page",
  {
    strokeColor: "#ca8a04",
    backgroundColor: "#fef3c7",
    strokeWidth: 3,
    fontSize: 12,
    textColor: "#854d0e",
  },
);
rect(
  "market-bank",
  910,
  454,
  232,
  240,
  "Market Skill Bank\nJOB_POSTING-grouped MARKET_SKILL nodes\nstatus: covered / gap / new topic\npriority + demand %\nteacher-facing tab in Curriculum page",
  {
    strokeColor: "#dc2626",
    backgroundColor: "#fee2e2",
    strokeWidth: 3,
    fontSize: 12,
    textColor: "#991b1b",
  },
);
rect(
  "center-select",
  704,
  744,
  392,
  82,
  "Selected skills from both banks\nstudent chooses book skills and/or market skills\njob-posting interest can auto-select related market skills",
  {
    strokeColor: "#0f766e",
    backgroundColor: "#ccfbf1",
    strokeWidth: 2,
    fontSize: 11,
    textColor: "#115e59",
  },
);
addText(
  "center-footnote",
  660,
  844,
  "Curriculum UI shows transcript chapters, book skill bank, market skill bank, and an agent changelog sourced from Neo4j.",
  {
    fontSize: 10,
    width: 500,
    strokeColor: "#475569",
  },
);
arrow("center-top-down-1", 900, 412, [[0, 0], [-122, 0], [-122, 42]], {
  strokeColor: "#ca8a04",
});
arrow("center-top-down-2", 900, 412, [[0, 0], [126, 0], [126, 42]], {
  strokeColor: "#dc2626",
});
arrow("center-b1", 778, 694, [[0, 0], [0, 50], [122, 50]], {
  strokeColor: "#0f766e",
});
arrow("center-b2", 1026, 694, [[0, 0], [0, 50], [-126, 50]], {
  strokeColor: "#0f766e",
});

rect("group-right", 1240, 308, 520, 492, "", {
  strokeColor: "#86efac",
  backgroundColor: "#fbfffb",
  strokeStyle: "dashed",
  strokeWidth: 1,
});
addText("group-right-label", 1258, 314, "Market Demand Analyst", {
  fontSize: 13,
  width: 240,
  strokeColor: "#15803d",
  textAlign: "left",
});
addText("group-right-sub", 1258, 334, "5-agent swarm + extraction subgraph", {
  fontSize: 10,
  width: 240,
  strokeColor: "#4ade80",
  textAlign: "left",
});
rect("job-boards", 1498, 346, 218, 58, "Indeed + LinkedIn\nparallel job scraping", {
  strokeColor: "#64748b",
  backgroundColor: "#f8fafc",
  fontSize: 10,
  textColor: "#334155",
});
rect(
  "mda-1",
  1280,
  420,
  204,
  74,
  "1. Supervisor + Skill Finder\npropose search terms\nfetch jobs\ngroup postings by role",
  {
    strokeColor: "#16a34a",
    backgroundColor: "#dcfce7",
    fontSize: 10,
    textColor: "#166534",
  },
);
rect("mda-hitl-1", 1280, 514, 204, 60, "2. Teacher picks\nrelevant job groups", {
  strokeColor: "#ea580c",
  backgroundColor: "#fff7ed",
  strokeStyle: "dashed",
  fontSize: 10,
  textColor: "#9a3412",
});
rect(
  "mda-3",
  1280,
  594,
  204,
  84,
  "3. Skill extractor subgraph\nfan out per job\ndeduplicate + merge synonyms\ncompute demand frequency",
  {
    strokeColor: "#16a34a",
    backgroundColor: "#dcfce7",
    fontSize: 10,
    textColor: "#166534",
  },
);
rect("mda-hitl-2", 1280, 698, 204, 60, "4. Teacher curates\nwhich skills to keep", {
  strokeColor: "#ea580c",
  backgroundColor: "#fff7ed",
  strokeStyle: "dashed",
  fontSize: 10,
  textColor: "#9a3412",
});
rect(
  "mda-5",
  1514,
  430,
  206,
  76,
  "5. Curriculum Mapper\ncompare curated skills against\nCOURSE_CHAPTER coverage\nassign gap / new topic / covered",
  {
    strokeColor: "#16a34a",
    backgroundColor: "#dcfce7",
    fontSize: 10,
    textColor: "#166534",
  },
);
rect(
  "mda-6",
  1514,
  532,
  206,
  76,
  "6. Skill Cleaner\nremove redundancy against\nexisting Book Skill Bank\nprepare final insert set",
  {
    strokeColor: "#16a34a",
    backgroundColor: "#dcfce7",
    fontSize: 10,
    textColor: "#166534",
  },
);
rect(
  "mda-7",
  1514,
  634,
  206,
  92,
  "7. Concept Linker + insert\nextract required concepts\nwrite MARKET_SKILL, JOB_POSTING\nand chapter links to Neo4j",
  {
    strokeColor: "#16a34a",
    backgroundColor: "#dcfce7",
    fontSize: 10,
    textColor: "#166534",
  },
);
addText(
  "mda-note",
  1280,
  758,
  "State is checkpointed per thread; the teacher UI streams agent text, tool calls, pipeline stages, and insertion results.",
  {
    fontSize: 10,
    width: 430,
    strokeColor: "#475569",
    textAlign: "left",
  },
);
arrow("mda-ext", 1498, 404, [[0, 0], [-116, 0], [0, 16]]);
arrow("mda-a1", 1382, 494, [[0, 0], [0, 20]], {
  strokeColor: "#ea580c",
  strokeStyle: "dashed",
});
arrow("mda-a2", 1382, 574, [[0, 0], [0, 20]], { strokeColor: "#16a34a" });
arrow("mda-a3", 1382, 678, [[0, 0], [0, 20]], {
  strokeColor: "#ea580c",
  strokeStyle: "dashed",
});
arrow("mda-a4", 1484, 451, [[0, 0], [30, 0]], { strokeColor: "#16a34a" });
arrow("mda-a5", 1617, 506, [[0, 0], [0, 26]], { strokeColor: "#16a34a" });
arrow("mda-a6", 1617, 608, [[0, 0], [0, 26]], { strokeColor: "#16a34a" });
arrow("mda-top-link", 1012, 250, [[0, 0], [340, 0], [340, 170]], {
  strokeColor: "#16a34a",
});

arrow("cross-caa-bank", 518, 649, [[0, 0], [144, 0]], {
  strokeColor: "#ca8a04",
  strokeWidth: 3,
});
arrow("cross-bank-clean", 894, 574, [[0, 0], [200, 0], [200, 0], [620, 0]], {
  strokeColor: "#b45309",
  strokeStyle: "dashed",
});
addText("cross-bank-clean-label", 1070, 548, "clean against book skills", {
  fontSize: 9,
  width: 160,
  strokeColor: "#92400e",
});
arrow("cross-mda-bank", 1514, 680, [[0, 0], [-372, 0]], {
  strokeColor: "#dc2626",
  strokeWidth: 3,
});

rect("group-bottom", 320, 890, 1160, 186, "", {
  strokeColor: "#99f6e4",
  backgroundColor: "#f0fdfa",
  strokeStyle: "dashed",
  strokeWidth: 1,
});
addText("group-bottom-label", 338, 896, "Resource Curation Layer", {
  fontSize: 13,
  width: 220,
  strokeColor: "#0f766e",
  textAlign: "left",
});
addText(
  "group-bottom-sub",
  338,
  916,
  "Implemented today inside the Student Learning Path graph, downstream of selected skills",
  {
    fontSize: 10,
    width: 420,
    strokeColor: "#14b8a6",
    textAlign: "left",
  },
);
rect(
  "slp-orch",
  762,
  948,
  276,
  92,
  "Student Learning Path orchestrator\nload selected skills\ncheck which resources already exist\nfan out one worker per missing skill",
  {
    strokeColor: "#0f766e",
    backgroundColor: "#ccfbf1",
    strokeWidth: 3,
    fontSize: 11,
    textColor: "#115e59",
  },
);
rect(
  "tra",
  398,
  946,
  286,
  98,
  "Textual Resource Analyst\nquery generation\nweb search + embedding filter\nLLM scoring + coverage selection\nwrite top-3 readings per skill",
  {
    strokeColor: "#0f766e",
    backgroundColor: "#ecfeff",
    fontSize: 11,
    textColor: "#155e75",
  },
);
rect(
  "vce",
  1116,
  946,
  286,
  98,
  "Video Agent\nYouTube-focused queries\nsearch + embedding filter\nLLM scoring + coverage selection\nwrite top-3 videos per skill",
  {
    strokeColor: "#ea580c",
    backgroundColor: "#ffedd5",
    fontSize: 11,
    textColor: "#9a3412",
  },
);
rect(
  "resource-out",
  692,
  1048,
  416,
  40,
  "Outputs: readings and videos attached back to skill nodes and surfaced in the student learning path UI",
  {
    strokeColor: "#64748b",
    backgroundColor: "#f8fafc",
    fontSize: 10,
    textColor: "#334155",
  },
);
arrow("bottom-from-center", 900, 826, [[0, 0], [0, 122]], {
  strokeColor: "#0f766e",
});
arrow("slp-to-tra", 762, 994, [[0, 0], [-78, 0]], {
  strokeColor: "#0f766e",
});
arrow("slp-to-vce", 1038, 994, [[0, 0], [78, 0]], {
  strokeColor: "#ea580c",
});
arrow("tra-out", 541, 1044, [[0, 0], [151, 24]], { strokeColor: "#0f766e" });
arrow("vce-out", 1259, 1044, [[0, 0], [-151, 24]], { strokeColor: "#ea580c" });

rect(
  "legend",
  1508,
  910,
  216,
  148,
  "Legend\nsolid border = implemented flow\ndashed orange = human approval\ndashed slate = grouping / dependency\ncenter banks = shared skill memory",
  {
    strokeColor: "#94a3b8",
    backgroundColor: "#ffffff",
    fontSize: 10,
    textColor: "#475569",
  },
);

const diagram = {
  type: "excalidraw",
  version: 2,
  source: "claude-code-excalidraw-skill",
  elements,
  appState: {
    gridSize: 20,
    viewBackgroundColor: "#fffdf8",
  },
  files: {},
};

const outputPath = path.resolve(
  process.cwd(),
  "docs/diagrams/conference_agent_ecology.excalidraw",
);

fs.writeFileSync(outputPath, `${JSON.stringify(diagram, null, 2)}\n`, "utf8");
console.log(`Wrote ${outputPath}`);
