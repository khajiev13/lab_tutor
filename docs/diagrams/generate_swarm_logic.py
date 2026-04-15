import json

seed_counter = 5000
index_counter = 0

def next_seed():
    global seed_counter
    seed_counter += 10
    return seed_counter

def next_index():
    global index_counter
    index_counter += 1
    return f"b{index_counter:04d}"

def rect(id, x, y, w, h, bg, stroke, roughness=0, fill="solid", roundness={"type": 3}, strokeStyle="solid", strokeWidth=2):
    return {
        "type": "rectangle", "id": id, "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": bg, "fillStyle": fill,
        "strokeWidth": strokeWidth, "strokeStyle": strokeStyle, "roughness": roughness,
        "opacity": 100, "angle": 0, "seed": next_seed(), "version": 1,
        "versionNonce": next_seed(), "isDeleted": False,
        "groupIds": [], "boundElements": [],
        "link": None, "locked": False, "roundness": roundness,
        "frameId": None, "index": next_index()
    }

def text(id, x, y, w, h, txt, size=16, family=2, color="#1e1e1e", align="center", valign="middle"):
    return {
        "type": "text", "id": id, "x": x, "y": y, "width": w, "height": h,
        "text": txt, "originalText": txt, "fontSize": size, "fontFamily": family, # 1: Virgil, 2: Helvetica, 3: Cascadia
        "textAlign": align, "verticalAlign": valign,
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "angle": 0,
        "seed": next_seed(), "version": 1, "versionNonce": next_seed(),
        "isDeleted": False, "groupIds": [],
        "boundElements": None, "link": None, "locked": False,
        "containerId": None, "lineHeight": 1.25, "frameId": None, "index": next_index()
    }

def arrow(id, x, y, dx, dy, color="#1e1e1e", width=2, roughness=0, end_arrow="arrow", style="solid"):
    return {
        "type": "arrow", "id": id, "x": x, "y": y,
        "width": abs(dx), "height": abs(dy),
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": width, "strokeStyle": style,
        "roughness": roughness, "opacity": 100, "angle": 0,
        "seed": next_seed(), "version": 1, "versionNonce": next_seed(),
        "isDeleted": False, "groupIds": [], "boundElements": None,
        "link": None, "locked": False,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": end_arrow,
        "points": [[0, 0], [dx, dy]], "frameId": None, "index": next_index()
    }

def group(elements_list):
    group_id = f"group_{next_seed()}"
    for el in elements_list:
        el["groupIds"].append(group_id)
    return elements_list

elements = []

# Title
elements.append(text("title_main", 600, 20, 800, 40, "Deep Dive: Lab Tutor Multi-Agent Logic & Swarm Topography", size=32, family=2, color="#0f172a", align="center"))

# ═══════════════════════════════════════════════════════════════
# 1. TEACHER INPUTS (Left)
# ═══════════════════════════════════════════════════════════════
elements.append(rect("b_tch", 50, 100, 200, 140, "#f8fafc", "#475569", roundness={"type": 2}))
elements.append(text("t_tch", 60, 120, 180, 20, "Teacher Actions", size=18, color="#0f172a", family=2))
elements.append(text("t_tch_sub", 60, 160, 180, 60, "Uploads Syllabi,\nTranscripts, &\nCourse Metadata", size=14, color="#475569", family=3))

elements.append(arrow("a_tch", 250, 170, 70, 0, color="#475569"))

# ═══════════════════════════════════════════════════════════════
# 2. CURRICULAR ALIGNMENT ARCHITECT (Sub-Graph / Map-Reduce Paradigm) - Bottom Center
# ═══════════════════════════════════════════════════════════════
y_ca = 620
x_ca = 320
w_ca = 880
h_ca = 220
# Background Container
elements.append(rect("ca_bg", x_ca, y_ca, w_ca, h_ca, "#f0fdf4", "#166534", strokeStyle="dashed", roundness={"type": 3}))
elements.append(text("ca_title", x_ca + 20, y_ca + 15, 350, 20, "Curricular Alignment Agent (Sub-Graph Paradigm)", size=16, color="#064e3b", family=2, align="left"))

# Nodes inside CA
# Discovery Subgraph
elements.append(rect("ca_n1", x_ca + 30, y_ca + 60, 150, 80, "#ffffff", "#15803d", roundness={"type": 2}))
elements.append(text("ca_t1", x_ca + 40, y_ca + 70, 130, 40, "Discovery\nSub-Graph", size=14, color="#15803d"))
elements.append(text("ca_d1", x_ca + 40, y_ca + 115, 130, 20, "(Map-Reduce Search)", size=10, color="#15803d", family=3))

# Scoring Subgraph
elements.append(rect("ca_n2", x_ca + 230, y_ca + 60, 150, 80, "#ffffff", "#15803d", roundness={"type": 2}))
elements.append(text("ca_t2", x_ca + 240, y_ca + 70, 130, 40, "Scoring\nSub-Graph", size=14, color="#15803d"))
elements.append(text("ca_d2", x_ca + 240, y_ca + 115, 130, 20, "(ReAct Researcher)", size=10, color="#15803d", family=3))

# HITL Review
elements.append(rect("ca_n3", x_ca + 430, y_ca + 60, 150, 80, "#fef08a", "#a16207", roundness={"type": 2}))
elements.append(text("ca_t3", x_ca + 440, y_ca + 75, 130, 40, "🧑‍🏫 HITL Node\n(Teacher Review)", size=14, color="#a16207"))
elements.append(arrow("a_tch_rev", 150, 240, x_ca + 350, y_ca - 240 + 60, color="#cbd5e1", style="dashed", roughness=1)) # Connect teacher to HITL

# Download/Chunking Subgraph
elements.append(rect("ca_n4", x_ca + 630, y_ca + 60, 200, 80, "#ffffff", "#15803d", roundness={"type": 2}))
elements.append(text("ca_t4", x_ca + 640, y_ca + 70, 180, 40, "Download & Chunking\nSub-Graphs", size=14, color="#15803d"))
elements.append(text("ca_d4", x_ca + 640, y_ca + 115, 180, 40, "(Builds COURSE_CHAPTER\n& Extracts Book Skills)", size=10, color="#15803d", family=3))

elements.append(arrow("a_ca_1", x_ca + 180, y_ca + 100, 50, 0, color="#15803d"))
elements.append(arrow("a_ca_2", x_ca + 380, y_ca + 100, 50, 0, color="#15803d"))
elements.append(arrow("a_ca_3", x_ca + 580, y_ca + 100, 50, 0, color="#a16207"))


# ═══════════════════════════════════════════════════════════════
# 3. MARKET DEMAND ANALYST (Swarm Paradigm) - Top Center
# ═══════════════════════════════════════════════════════════════
y_mda = 100
x_mda = 320
w_mda = 880
h_mda = 450
# Background Container
elements.append(rect("md_bg", x_mda, y_mda, w_mda, h_mda, "#fff7ed", "#9a3412", strokeStyle="dashed", roundness={"type": 3}))
elements.append(text("md_title", x_mda + 20, y_mda + 20, 350, 20, "Market Demand Analyst (Swarm Paradigm)", size=16, color="#9a3412", family=2, align="left"))

# Supervisor (The Hub) - Center
x_sup = x_mda + 350
y_sup = y_mda + 180
elements.append(rect("md_sup", x_sup, y_sup, 180, 80, "#fdba74", "#c2410c", roundness={"type": 2}))
elements.append(text("t_sup", x_sup + 10, y_sup + 30, 160, 20, "👑 Supervisor (Hub)", size=16, color="#7c2d12"))

# Worker 1: Skill Finder (Top Left)
x_w1 = x_mda + 100
y_w1 = y_mda + 80
elements.append(rect("md_w1", x_w1, y_w1, 160, 60, "#ffffff", "#c2410c", roundness={"type": 2}))
elements.append(text("t_w1", x_w1 + 10, y_w1 + 15, 140, 40, "1. Skill Finder\n(Fetch & Extract)", size=14, color="#9a3412"))

# Worker 2: Curriculum Mapper (Top Right)
x_w2 = x_mda + 620
y_w2 = y_mda + 80
elements.append(rect("md_w2", x_w2, y_w2, 160, 60, "#ffffff", "#c2410c", roundness={"type": 2}))
elements.append(text("t_w2", x_w2 + 10, y_w2 + 15, 140, 40, "2. Curric. Mapper\n(Map aligned skills)", size=14, color="#9a3412"))

# Worker 3: Skill Cleaner (Bottom Right)
x_w3 = x_mda + 620
y_w3 = y_mda + 320
elements.append(rect("md_w3", x_w3, y_w3, 160, 60, "#ffffff", "#c2410c", roundness={"type": 2}))
elements.append(text("t_w3", x_w3 + 10, y_w3 + 15, 140, 40, "3. Skill Cleaner\n(Deduplicate)", size=14, color="#9a3412"))

# Worker 4: Concept Linker (Bottom Left)
x_w4 = x_mda + 100
y_w4 = y_mda + 320
elements.append(rect("md_w4", x_w4, y_w4, 160, 60, "#ffffff", "#c2410c", roundness={"type": 2}))
elements.append(text("t_w4", x_w4 + 10, y_w4 + 15, 140, 40, "4. Concept Linker\n(Final DB Write)", size=14, color="#9a3412"))


# Swarm routing arrows (Supervisor Hub to Workers and back)
ar_color = "#fdba74"
# Sup -> W1
elements.append(arrow("a_h1", x_sup, y_sup + 40, -(x_sup - x_w1 - 160), -(y_sup + 40 - y_w1 - 60), color=ar_color))
# W1 -> Sup
elements.append(arrow("a_h1b", x_w1 + 160, y_w1 + 30, (x_sup - x_w1 - 160), (y_sup + 30 - y_w1 - 30), style="dashed", color=ar_color))

# Sup -> W2
elements.append(arrow("a_h2", x_sup + 180, y_sup + 40, (x_w2 - x_sup - 180), -(y_sup + 40 - y_w2 - 60), color=ar_color))
# W2 -> Sup
elements.append(arrow("a_h2b", x_w2, y_w2 + 30, -(x_w2 - x_sup - 180), (y_sup + 30 - y_w2 - 30), style="dashed", color=ar_color))

# Sup -> W3
elements.append(arrow("a_h3", x_sup + 180, y_sup + 60, (x_w3 - x_sup - 180), (y_w3 - y_sup - 60), color=ar_color))
# W3 -> Sup
elements.append(arrow("a_h3b", x_w3, y_w3 + 30, -(x_w3 - x_sup - 180), -(y_w3 + 30 - y_sup - 80), style="dashed", color=ar_color))

# Sup -> W4
elements.append(arrow("a_h4", x_sup, y_sup + 60, -(x_sup - x_w4 - 160), (y_w4 - y_sup - 60), color=ar_color))
# W4 -> Sup
elements.append(arrow("a_h4b", x_w4 + 160, y_w4 + 30, (x_sup - x_w4 - 160), -(y_w4 + 30 - y_sup - 80), style="dashed", color=ar_color))


# Notice connection from Teacher logic to MDA (trigger point)
elements.append(arrow("a_mda_start", 250, 160, 70, 0, color="#cbd5e1", style="dashed"))


# ═══════════════════════════════════════════════════════════════
# 4. KNOWLEDGE GRAPH OUTPUTS (Far Right)
# ═══════════════════════════════════════════════════════════════
x_kg = 1350
y_kg = 100
w_kg = 350
h_kg = 740

elements.append(rect("kg_bg", x_kg, y_kg, w_kg, h_kg, "#fffbeb", "#d97706", roundness={"type": 3}))
elements.append(text("t_kg_title", x_kg + 20, y_kg + 20, 310, 40, "Unified Knowledge Graph\n(Neo4j)", size=20, color="#b45309", family=3))

# Nodes inside KG
# Chapter Database Node (created by Curricular Arch)
elements.append(rect("kg_cc", x_kg + 45, y_kg + 150, 260, 60, "#f8fafc", "#475569", roundness={"type": 2}))
elements.append(text("kg_t_cc", x_kg + 55, y_kg + 165, 240, 30, "COURSE_CHAPTER", size=16, color="#0f172a", family=3))

# Market Skill Database Node (created by MDA -> Concept Linker)
elements.append(rect("kg_ms", x_kg + 45, y_kg + 350, 260, 60, "#ffedd5", "#c2410c", roundness={"type": 2}))
elements.append(text("kg_t_ms", x_kg + 55, y_kg + 365, 240, 30, "(Orange) MARKET_SKILL", size=16, color="#7c2d12", family=3))

# Book Skill Database Node (created by CA -> Chunking)
elements.append(rect("kg_bs", x_kg + 45, y_kg + 550, 260, 60, "#dcfce7", "#059669", roundness={"type": 2}))
elements.append(text("kg_t_bs", x_kg + 55, y_kg + 565, 240, 30, "(Green) BOOK_SKILL", size=16, color="#064e3b", family=3))

# Graph inner connections
elements.append(arrow("a_kg_1", x_kg + 175, y_kg + 350, 0, -140, color="#c2410c"))
elements.append(text("kg_rt1", x_kg + 185, y_kg + 260, 100, 20, "MAPPED_TO", size=12, color="#c2410c", family=3))

elements.append(arrow("a_kg_2", x_kg + 175, y_kg + 550, -100, -340, color="#059669"))
elements.append(text("kg_rt2", x_kg + 40, y_kg + 420, 100, 20, "MAPPED_TO", size=12, color="#059669", family=3))

# Arrows from Agents -> KG
# SubGraph (Chunker) -> Book Skill + Chapter
elements.append(arrow("a_wrt_ca", x_ca + w_ca, y_ca + 120, (x_kg + 45) - (x_ca + w_ca), y_kg + 580 - (y_ca + 120), color="#15803d", width=3))
elements.append(arrow("a_wrt_cc", x_ca + w_ca, y_ca + 100, (x_kg + 45) - (x_ca + w_ca), y_kg + 180 - (y_ca + 100), color="#475569", width=2))

# Swarm (Concept Linker) -> Market Skill
elements.append(arrow("a_wrt_md", x_w4 + 160, y_w4 + 50, (x_kg + 45) - (x_w4 + 160), y_kg + 380 - (y_w4 + 50), color="#c2410c", width=3))


# ═══════════════════════════════════════════════════════════════
# 5. FETCHERS & STUDENT LEARNING PATH (Bottom Right)
# ═══════════════════════════════════════════════════════════════
# Fetchers (Act on missing Market Skills & Book skills)
x_f = x_mda + 250
y_f = y_ca + h_ca + 80
elements.append(rect("f_bg", x_f, y_f, 550, 100, "#eff6ff", "#1e40af", strokeStyle="dashed", roundness={"type": 3}))
elements.append(text("f_bg_t", x_f + 20, y_f + 10, 500, 20, "Downstream Autonomous Resource Fetchers", size=14, color="#1e40af", family=2, align="left"))

elements.append(rect("f_n1", x_f + 100, y_f + 40, 150, 40, "#ffffff", "#1d4ed8", roundness={"type": 2}))
elements.append(text("f_t1", x_f + 110, y_f + 50, 130, 20, "📖 Reading Fetcher", size=14, color="#1e3a8a"))

elements.append(rect("f_n2", x_f + 300, y_f + 40, 150, 40, "#ffffff", "#1d4ed8", roundness={"type": 2}))
elements.append(text("f_t2", x_f + 310, y_f + 50, 130, 20, "🎬 Video Fetcher", size=14, color="#1e3a8a"))

# Arrow from Graph triggering Fetchers -> Student output
elements.append(arrow("a_f_trig", x_kg + 45, y_kg + 400, x_f + 550 - (x_kg + 45), (y_f + 50) - (y_kg + 400), color="#cbd5e1", style="dashed"))

# Final Student Arrow
x_st = 1350
y_st = 920

elements.append(arrow("a_final_fetch", x_f + 550, y_f + 70, (x_st + 150) - (x_f + 550), y_st - (y_f + 70), color="#2563eb", width=3))
elements.append(arrow("a_final_graph", x_kg + 175, y_kg + h_kg, 0, y_st - (y_kg + h_kg), color="#b45309", width=3))

# Resulting Student Learning Path
elements.append(rect("st_bg", x_st, y_st, 350, 100, "#f8fafc", "#0f172a", roundness={"type": 2}, strokeWidth=3))
elements.append(text("st_t", x_st + 20, y_st + 30, 310, 40, "Personalized Student\nLearning Interface", size=24, color="#0f172a", family=2))


# ═══════════════════════════════════════════════════════════════
# OUTPUT AND SAVE
# ═══════════════════════════════════════════════════════════════
diagram = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 10},
    "files": {}
}

out_path = "/Users/khajievroma/Projects/lab_tutor/docs/diagrams/swarm_logic_deep_dive.excalidraw"
with open(out_path, "w") as f:
    json.dump(diagram, f, indent=2)

print(f"Generated {len(elements)} elements → {out_path}")
