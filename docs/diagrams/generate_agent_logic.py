import json

seed_counter = 2000
index_counter = 0

def next_seed():
    global seed_counter
    seed_counter += 10
    return seed_counter

def next_index():
    global index_counter
    index_counter += 1
    return f"b{index_counter:03d}"

def rect(id, x, y, w, h, bg, stroke, roughness=0, fill="solid", group=None, roundness={"type": 3}):
    return {
        "type": "rectangle", "id": id, "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": bg, "fillStyle": fill,
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": roughness,
        "opacity": 100, "angle": 0, "seed": next_seed(), "version": 1,
        "versionNonce": next_seed(), "isDeleted": False,
        "groupIds": [group] if group else [], "boundElements": [],
        "link": None, "locked": False, "roundness": roundness,
        "frameId": None, "index": next_index()
    }

def text(id, x, y, w, h, txt, size=16, family=1, color="#1e1e1e", align="left", valign="top", container=None, group=None):
    return {
        "type": "text", "id": id, "x": x, "y": y, "width": w, "height": h,
        "text": txt, "originalText": txt, "fontSize": size, "fontFamily": family, # 1: Virgil, 2: Helvetica, 3: Cascadia
        "textAlign": align, "verticalAlign": valign,
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "angle": 0,
        "seed": next_seed(), "version": 1, "versionNonce": next_seed(),
        "isDeleted": False, "groupIds": [group] if group else [],
        "boundElements": None, "link": None, "locked": False,
        "containerId": container, "lineHeight": 1.25, "frameId": None, "index": next_index()
    }

def arrow(id, x, y, dx, dy, color="#1e1e1e", width=2, roughness=1, end_arrow="arrow"):
    return {
        "type": "arrow", "id": id, "x": x, "y": y,
        "width": abs(dx), "height": abs(dy),
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": width, "strokeStyle": "solid",
        "roughness": roughness, "opacity": 100, "angle": 0,
        "seed": next_seed(), "version": 1, "versionNonce": next_seed(),
        "isDeleted": False, "groupIds": [], "boundElements": None,
        "link": None, "locked": False,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": end_arrow,
        "points": [[0, 0], [dx, dy]], "frameId": None, "index": next_index()
    }

def process_box(id_prefix, x, y, w, h, title_text, logic_text, bg, stroke):
    els = []
    # Main container
    els.append(rect(f"{id_prefix}_r", x, y, w, h, bg, stroke, roughness=0))
    # Title
    els.append(text(f"{id_prefix}_t1", x + 10, y + 10, w - 20, 24, title_text, size=18, family=2, color=stroke, align="center"))
    # Logic / Text
    els.append(text(f"{id_prefix}_t2", x + 15, y + 45, w - 30, h - 55, logic_text, size=14, family=2, color="#334155", align="left"))
    # Divider line
    els.append(arrow(f"{id_prefix}_div", x + 10, y + 38, w - 20, 0, color=stroke, width=1, roughness=0, end_arrow=None))
    return els

elements = []

# ═══════════════════════════════════════════════════════════════
# TITLE
# ═══════════════════════════════════════════════════════════════
elements.append(text("main_title", 350, 20, 700, 40, "System Architecture: Agent Logic & Data Flow", size=32, family=2, color="#0f172a", align="center"))

# ═══════════════════════════════════════════════════════════════
# COLUMNS BACKGROUNDS (Optional, keeping clean on white is often better)
# ═══════════════════════════════════════════════════════════════
# Column labels
elements.append(text("col1_label", 100, 80, 200, 30, "System Inputs", size=20, family=3, color="#475569", align="center"))
elements.append(text("col2_label", 590, 80, 300, 30, "Multi-Agent Engine (Logic)", size=20, family=3, color="#1e40af", align="center"))
elements.append(text("col3_label", 1080, 80, 200, 30, "System Outputs (Graph)", size=20, family=3, color="#92400e", align="center"))

# ═══════════════════════════════════════════════════════════════
# COLUMN 1: INPUTS
# ═══════════════════════════════════════════════════════════════
x1 = 60
# Transcripts
elements.append(rect("in_trans_r", x1, 140, 260, 60, "#f1f5f9", "#475569", roughness=1))
elements.append(text("in_trans_t", x1+10, 160, 240, 20, "Teacher Syllabi & Transcripts", size=16, family=2, color="#1e293b", align="center"))

# Textbooks
elements.append(rect("in_books_r", x1, 300, 260, 60, "#dcfce7", "#047857", roughness=1))
elements.append(text("in_books_t", x1+10, 320, 240, 20, "Digital Textbooks (PDF/EPUB)", size=16, family=2, color="#064e3b", align="center"))

# Job Postings
elements.append(rect("in_jobs_r", x1, 460, 260, 60, "#ffedd5", "#c2410c", roughness=1))
elements.append(text("in_jobs_t", x1+10, 480, 240, 20, "Live Job Postings", size=16, family=2, color="#7c2d12", align="center"))

# ═══════════════════════════════════════════════════════════════
# COLUMN 2: AGENTS
# ═══════════════════════════════════════════════════════════════
x2 = 440
w2 = 560
h2 = 100

# Architect
elements.extend(process_box("ag_arch", x2, 120, w2, h2,
    title_text="Curricular Alignment Architect",
    logic_text="Logic: Information extraction (IE). Parses unstructured text to synthesize course concepts.\nOutput: Builds structural 'COURSE_CHAPTER' scaffold.",
    bg="#f8fafc", stroke="#334155"
))

# Textual Resource Analyst
elements.extend(process_box("ag_text", x2, 280, w2, h2,
    title_text="Textual Resource Analyst",
    logic_text="Logic: Multi-document QA. Extracts actionable skills from textbooks,\ngrades relevance, and maps to specific chapters.\nOutput: 'BOOK_SKILL' nodes connected to 'COURSE_CHAPTER'.",
    bg="#f0fdf4", stroke="#166534"
))

# Market Demand Analyst
elements.extend(process_box("ag_mkt", x2, 440, w2, h2,
    title_text="Market Demand Analyst",
    logic_text="Logic: Entity normalization & gap detection. Extracts industry competencies,\naligns with curriculum, and categorizes (Covered/Missing).\nOutput: 'MARKET_SKILL' nodes connected to 'COURSE_CHAPTER'.",
    bg="#fff7ed", stroke="#9a3412"
))

# Visual Content Evaluator
elements.extend(process_box("ag_vis", x2, 600, w2, h2,
    title_text="Visual Content Evaluator",
    logic_text="Logic: Recommender agent. Curates external multimedia resources for identified\nskill gaps (targeting 'Missing' MARKET_SKILLs).\nOutput: External Resource nodes for student learning.",
    bg="#eff6ff", stroke="#1e40af"
))


# ═══════════════════════════════════════════════════════════════
# ARROWS: INPUTS -> AGENTS
# ═══════════════════════════════════════════════════════════════
elements.append(arrow("a_in_1", x1+260, 170, x2 - (x1+260), 0, color="#64748b")) # trans -> arch
elements.append(arrow("a_in_2", x1+260, 330, x2 - (x1+260), 0, color="#166534")) # book -> text
elements.append(arrow("a_in_3", x1+260, 490, x2 - (x1+260), 0, color="#9a3412")) # jobs -> mkt

# Scaffold dependency arrows (Architect -> Others)
elements.append(arrow("a_dep_1", x2+280, 220, 0, 60, color="#cbd5e1", roughness=0))
elements.append(arrow("a_dep_2", x2-40, 170, 0, 160, color="#cbd5e1", roughness=0))
elements.append(arrow("a_dep_2a", x2-40, 330, 40, 0, color="#cbd5e1", roughness=0))
elements.append(arrow("a_dep_3", x2-40, 330, 0, 160, color="#cbd5e1", roughness=0))
elements.append(arrow("a_dep_3a", x2-40, 490, 40, 0, color="#cbd5e1", roughness=0))
elements.append(arrow("a_dep_lbl", x2-35, 230, 10, 10, color="transparent", end_arrow=None))
elements.append(text("t_dep", x2-140, 380, 100, 20, "Uses Scaffold\nas Anchor", size=12, family=2, color="#64748b"))


# ═══════════════════════════════════════════════════════════════
# COLUMN 3: OUTPUTS (Knowledge Graph)
# ═══════════════════════════════════════════════════════════════
x3 = 1060

elements.append(rect("kg_container", x3 - 20, 120, 340, 420, "#fffbeb", "#d97706", roughness=0, roundness={"type": 3}))
elements.append(text("kg_title", x3, 130, 300, 20, "Unified Knowledge Graph", size=18, family=3, color="#b45309", align="center"))

# Course Chapter Node
elements.append(rect("node_cc", x3+20, 180, 260, 50, "#e2e8f0", "#475569", roundness={"type": 2}))
elements.append(text("node_cc_t", x3+30, 195, 240, 20, "(Node) COURSE_CHAPTER", size=14, family=3, color="#1e293b", align="center"))

# Book Skill Node
elements.append(rect("node_bs", x3+20, 300, 260, 50, "#d1fae5", "#059669", roundness={"type": 2}))
elements.append(text("node_bs_t", x3+30, 315, 240, 20, "(Node) BOOK_SKILL", size=14, family=3, color="#064e3b", align="center"))

# Market Skill Node
elements.append(rect("node_ms", x3+20, 420, 260, 50, "#ffedd5", "#ea580c", roundness={"type": 2}))
elements.append(text("node_ms_t", x3+30, 435, 240, 20, "(Node) MARKET_SKILL", size=14, family=3, color="#7c2d12", align="center"))

# Graph Edges
elements.append(arrow("edge_1", x3+150, 300, 0, -70, color="#059669", roughness=0))
elements.append(text("edge_1_t", x3+155, 250, 80, 20, "MAPPED_TO", size=10, family=3, color="#059669"))

elements.append(arrow("edge_2", x3+150, 420, -100, -190, color="#ea580c", roughness=0))
elements.append(text("edge_2_t", x3+30, 250, 80, 20, "MAPPED_TO", size=10, family=3, color="#ea580c"))


# ═══════════════════════════════════════════════════════════════
# ARROWS: AGENTS -> OUTPUTS
# ═══════════════════════════════════════════════════════════════
elements.append(arrow("a_out_1", x2+w2, 170, x3 - (x2+w2) + 20, 20, color="#475569", roughness=0)) # arch -> CC
elements.append(arrow("a_out_2", x2+w2, 330, x3 - (x2+w2) + 20, 0, color="#059669", roughness=0)) # text -> BS
elements.append(arrow("a_out_3", x2+w2, 490, x3 - (x2+w2) + 20, -40, color="#ea580c", roughness=0)) # mkt -> MS


# ═══════════════════════════════════════════════════════════════
# DOWNSTREAM OUTPUT
# ═══════════════════════════════════════════════════════════════
elements.append(arrow("a_final_1", x2+w2, 650, 100, 0, color="#2563eb", width=3, roughness=0))
elements.append(arrow("a_final_2", x3 + 150, 540, 0, 80, color="#d97706", width=3, roughness=0))

elements.append(text("t_union", x3 - 90, 605, 30, 30, "+", size=40, family=2, color="#64748b"))

elements.append(rect("final_path", x3 - 20, 620, 340, 60, "#dbeafe", "#1e40af", roughness=0, roundness={"type": 3}))
elements.append(text("final_path_t", x3-10, 630, 320, 40, "Personalized Student\nLearning Path", size=18, family=2, color="#1e3a5f", align="center"))

# ═══════════════════════════════════════════════════════════════
# OUTPUT AND SAVE
# ═══════════════════════════════════════════════════════════════
diagram = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
    "files": {}
}

out_path = "/Users/khajievroma/Projects/lab_tutor/docs/diagrams/conference_agent_ecology.excalidraw"
with open(out_path, "w") as f:
    json.dump(diagram, f, indent=2)

print(f"Generated {len(elements)} elements → {out_path}")
