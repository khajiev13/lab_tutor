# Plan: Skill Finder + Skill Cleaner Agents + `:SKILL` Label Unification

## TL;DR

1. Replace the current Supervisor-driven fetch/extract flow with a new **Skill Finder** swarm agent that owns "find and select skills": fetch jobs → teacher picks job groups → extract skills (fan-out subgraph) → LLM merge duplicates → teacher picks skills → hand off to Mapper.
2. The **Supervisor** becomes a lightweight orchestrator — converses with the teacher to produce search terms, then hands off. At the end, it writes the final skills to the database after teacher confirmation. It can re-enter any agent if the teacher changes their mind.
3. Add a shared `:SKILL` label to both `BOOK_SKILL` and `MARKET_SKILL` nodes.
4. The **Mapper** maps curated skills to chapters (no dedup responsibility).
5. A new **Skill Cleaner** agent runs after the Mapper — loads existing book skills per chapter, compares against the newly mapped market skills, and drops redundant ones so students don't learn the same thing twice. Only truly new skills survive.
6. The **Concept Linker** only processes the final cleaned skills — no wasted concept extraction.

---

## Handoff Topology (Middle Ground)

Forward chain + every agent can return to Supervisor. Supervisor can re-enter any agent.

```
          ┌──────────────────────────────────────────────────────────────┐
          │                     Supervisor (hub)                         │
          │  Can hand off to: Skill Finder, Mapper, Cleaner, Linker     │
          └──┬──────────────┬──────────────┬──────────────┬─────────────┘
             │              │              │              │
             ▼              ▼              ▼              ▼
        Skill Finder → Mapper → Skill Cleaner → Concept Linker
             │              │              │              │
             └──────────────┴──────────────┴──────────────┘
                     (all can return to Supervisor)
```

Each agent can go **forward one step** OR **back to Supervisor**. No skipping steps.
Supervisor is the only agent that can jump to any stage (for re-entry after teacher changes mind).

### Handoff tools per agent

Using `create_handoff_tool` from `langgraph_swarm`. Each description acts as a **gate** — tells the LLM the precondition for using it:

```python
# ── Handoff tools ──
handoff_to_supervisor = create_handoff_tool(
    agent_name="supervisor",
    description=(
        "Transfer back to Supervisor ONLY if the teacher wants to change direction, "
        "you encounter an error you cannot resolve, or you have completed the final "
        "step in the chain (Concept Linker). Do NOT use this if you can proceed forward."
    ),
)
handoff_to_skill_finder = create_handoff_tool(
    agent_name="skill_finder",
    description="Transfer to Skill Finder to fetch jobs and extract skills. Use ONLY after search terms are ready.",
)
handoff_to_curriculum_mapper = create_handoff_tool(
    agent_name="curriculum_mapper",
    description="Transfer to Curriculum Mapper ONLY after the teacher has confirmed their skill selection.",
)
handoff_to_skill_cleaner = create_handoff_tool(
    agent_name="skill_cleaner",
    description="Transfer to Skill Cleaner ONLY after all curated skills have been mapped to chapters.",
)
handoff_to_concept_linker = create_handoff_tool(
    agent_name="concept_linker",
    description="Transfer to Concept Linker ONLY after redundant skills have been cleaned.",
)
```

| Agent | Forward handoff | Back handoff |
|-------|----------------|--------------|
| **Supervisor** | → Skill Finder, → Mapper, → Cleaner, → Linker | (hub, no back) |
| **Skill Finder** | → Mapper | → Supervisor |
| **Curriculum Mapper** | → Skill Cleaner | → Supervisor |
| **Skill Cleaner** | → Concept Linker | → Supervisor |
| **Concept Linker** | (end of chain) | → Supervisor |

### Why not full mesh?
- 5 agents × 4 handoffs = 20 tools — too many choices for the LLM, risk of skipping steps
- Middle ground: 9 handoff tools total, clear linear path, Supervisor can re-enter any stage

---

## Pipeline Flow (Happy Path)

```
Supervisor (search terms)
  → Skill Finder (fetch → groups → extract → merge → teacher picks)
  → Mapper (map curated skills to chapters)
  → Skill Cleaner (compare per-chapter vs existing book skills, drop redundant)
  → Concept Linker (extract concepts for final clean skills only)
  → Supervisor (write to DB after teacher confirmation)
```

**Before** (current):
```
Supervisor (fetch + select groups + trigger extraction) → Extractor → Mapper (all 300+ skills) → Supervisor → Linker
```

**After** (proposed):
```
Supervisor → Skill Finder → Mapper → Skill Cleaner → Concept Linker → Supervisor (write to DB)
```

---

## Phase 1: Skill Finder Agent

### Step 1 — Move tools from Supervisor to Skill Finder

Move out of `SUPERVISOR_TOOLS` into `SKILL_FINDER_TOOLS`:
- `fetch_jobs` — scrapes Indeed/LinkedIn
- `select_jobs_by_group` — teacher picks job title groups

Add new tools:
- `start_extraction()` — triggers the extractor subgraph (replaces `start_analysis_pipeline`)
- `get_skills_by_category()` — returns merged skills grouped by category with frequency counts
- `approve_skill_selection(selection_json: str)` — saves teacher's picks to `tool_store["curated_skills"]`

### Step 2 — Write Skill Finder prompt

```
SKILL_FINDER_PROMPT = """
You are the Skill Finder. You find in-demand market skills from real job postings
and help the teacher select the most relevant ones for their curriculum.

# Process
1. Fetch jobs using the search terms provided by the Supervisor (fetch_jobs)
2. Show job groups to the teacher, let them pick relevant groups (select_jobs_by_group)
3. Start skill extraction from selected jobs (start_extraction)
4. After extraction + merge completes, show skills by category (get_skills_by_category)
5. Let the teacher select skills:
   - By specific skill names
   - By entire categories
   - By top N most frequent per category
   - Any combination
6. Save selection and hand off to Curriculum Mapper (approve_skill_selection)

# Rules
- Show category summaries first, drill into details on request
- Always show frequency data — higher frequency = more in-demand
- Be conversational but efficient — teacher's time is limited
- After teacher confirms skill selection, save and hand off immediately
- If the teacher wants to change search terms, hand back to Supervisor
"""
```

### Step 3 — Create the agent in `graph.py`

```python
skill_finder = create_react_agent(
    llm,
    tools=[*SKILL_FINDER_TOOLS, handoff_to_curriculum_mapper, handoff_to_supervisor],
    prompt=_make_prompt(SKILL_FINDER_PROMPT),
    name="skill_finder",
)
```

### Step 4 — Update Supervisor

Remove `fetch_jobs`, `select_jobs_by_group`, `start_analysis_pipeline` from `SUPERVISOR_TOOLS`.
Supervisor gets handoffs to ALL agents (hub role):

```python
supervisor = create_react_agent(
    llm,
    tools=[
        *SUPERVISOR_TOOLS,
        handoff_to_skill_finder,
        handoff_to_curriculum_mapper,
        handoff_to_skill_cleaner,
        handoff_to_concept_linker,
    ],
    prompt=_make_prompt(supervisor_prompt),
    name="supervisor",
)
```

Updated `SUPERVISOR_TOOLS` (domain tools only):
```python
SUPERVISOR_TOOLS = [
    save_skills_for_insertion,
    delete_market_skills,
    show_current_state,
]
```

### Step 5 — `start_extraction` tool (in Skill Finder)

Replaces `start_analysis_pipeline`. Routes to extractor subgraph:
```python
def start_extraction() -> Command:
    """Start parallel skill extraction from selected job groups.
    Fans out one LLM call per job, merges duplicates, then returns
    control back to Skill Finder for teacher skill selection."""
    jobs = tool_store.get("selected_jobs", [])
    if not jobs:
        return "No jobs selected yet. Use select_jobs_by_group first."
    return Command(
        goto="skill_extractor",
        graph=Command.PARENT,
        update={"active_agent": "skill_extractor"},
    )
```

### Step 6 — Update extractor subgraph routing

`merge_similar_skills` returns to `skill_finder`:
```python
return Command(goto="skill_finder", graph=Command.PARENT,
               update={"active_agent": "skill_finder"})
```

---

## Phase 2: Skill Merging (Extractor Subgraph)

### Step 7 — Add `merge_similar_skills` node

After `synthesize_skills` deduplicates by exact name and counts frequency, add a node that calls the LLM **once** with the full deduplicated skill list to:
- Cluster skills that mean the same thing (e.g. "Deploy on AWS" / "Deploy applications using AWS")
- Pick the most descriptive canonical name for each cluster
- Assign a category to each skill
- Sum frequencies across merged skills

Graph wiring:
```
fan_out → extract_one → synthesize_skills → merge_similar_skills → (Command to skill_finder)
```

### Step 8 — Define merge prompt and output schema

Output schema (`MergeResult`):
```python
class MergedSkill(BaseModel):
    name: str          # Canonical skill name
    category: str      # e.g. "Cloud", "Data Engineering", "Programming Language"
    frequency: int     # Sum of merged skill frequencies
    merged_from: list[str]  # Original skill names that were collapsed

class MergeResult(BaseModel):
    merged_skills: list[MergedSkill]
```

---

## Phase 3: Skill Cleaner Agent

### Step 9 — Define Skill Cleaner tools

| Tool | Purpose |
|------|---------|
| `load_mapped_skills()` | Read `tool_store["mapped_skills"]` — the Mapper's output: market skills assigned to chapters. |
| `load_book_skills_for_chapters(chapter_ids: str)` | Query Neo4j for existing `BOOK_SKILL` nodes linked to the given chapters. Returns per-chapter skill lists. |
| `compare_and_clean(chapter_id: str)` | For one chapter: compare mapped market skills vs existing book skills. LLM decides which market skills are redundant (too similar to an existing book skill). Returns kept/dropped lists with reasoning. |
| `finalize_cleaned_skills()` | Save the final cleaned skill list to `tool_store["final_skills"]`. Hand off to Concept Linker. |

### Step 10 — Write Skill Cleaner prompt

```
SKILL_CLEANER_PROMPT = """
You are the Skill Cleaner. You ensure students don't learn redundant skills
by comparing newly mapped market skills against existing book skills per chapter.

# Process
1. Load the mapped skills — market skills assigned to chapters by the Mapper (load_mapped_skills)
2. For each chapter that has mapped skills, load existing book skills (load_book_skills_for_chapters)
3. Compare per chapter (compare_and_clean):
   - If a market skill is too similar to an existing book skill in the same chapter, DROP it
   - "Too similar" = the student would learn essentially the same competency
   - Keep market skills that teach genuinely new competencies
4. Finalize the cleaned list and hand off to Concept Linker (finalize_cleaned_skills)

# Rules
- Work chapter by chapter for precision
- When dropping a skill, note which existing book skill it overlaps with
- Err on the side of KEEPING a skill if it's borderline — the teacher already selected it
- Be autonomous — no teacher interaction needed at this stage
- If something looks wrong, hand back to Supervisor rather than guessing
- After cleaning, hand off immediately
"""
```

### Step 11 — Create the agent in `graph.py`

```python
skill_cleaner = create_react_agent(
    llm,
    tools=[*SKILL_CLEANER_TOOLS, handoff_to_concept_linker, handoff_to_supervisor],
    prompt=_make_prompt(SKILL_CLEANER_PROMPT),
    name="skill_cleaner",
)
```

### Step 12 — Update Mapper routing

Mapper hands off to `skill_cleaner` instead of `supervisor`:

```python
curriculum_mapper = create_react_agent(
    llm,
    tools=[*CURRICULUM_MAPPER_TOOLS, handoff_to_skill_cleaner, handoff_to_supervisor],
    prompt=_make_prompt(CURRICULUM_MAPPER_PROMPT),
    name="curriculum_mapper",
)
```

Mapper stores its output in `tool_store["mapped_skills"]` — a dict of `{chapter_id: [skill_names]}`

### Step 13 — Update Concept Linker

```python
concept_linker = create_react_agent(
    llm,
    tools=[*CONCEPT_LINKER_TOOLS, handoff_to_supervisor],
    prompt=_make_prompt(CONCEPT_LINKER_PROMPT),
    name="concept_linker",
)
```

---

## Phase 4: Neo4j Schema — Add `:SKILL` Label

### Step 14 — Migration: add `:SKILL` to existing nodes
Create `neo4j_database/migrations/2026-03-12_add_skill_label.cypher`:
```cypher
MATCH (s:BOOK_SKILL) SET s:SKILL;
MATCH (s:MARKET_SKILL) SET s:SKILL;
```

### Step 15 — Add MARKET_SKILL uniqueness constraint
In `backend/app/core/neo4j.py`, add:
```python
"CREATE CONSTRAINT market_skill_name_unique IF NOT EXISTS FOR (ms:MARKET_SKILL) REQUIRE ms.name IS UNIQUE",
```

### Step 16 — Update creation queries to include `:SKILL`
- **MARKET_SKILL** in `tools.py`: `MERGE (s:MARKET_SKILL:SKILL {name: $name})`
- **BOOK_SKILL** in `curriculum_graph/repository.py`: `MERGE (sk:BOOK_SKILL:SKILL {id: $skill_id})`

---

## Phase 5: Swarm Assembly & Testing

### Step 17 — Assemble the swarm in `graph.py`

```python
workflow = create_swarm(
    [supervisor, skill_finder, curriculum_mapper, skill_cleaner, concept_linker],
    default_active_agent="supervisor",
)
workflow.add_node("skill_extractor", skill_extractor_subgraph)
```

### Step 18 — Update Supervisor for final DB write
Supervisor receives control after Concept Linker finishes. It presents the final skill list to the teacher for confirmation, then calls `save_skills_for_insertion` to write to Neo4j.

### Step 19 — Update `pipeline_summary` in `state.py`
Add `curated_skills`, `mapped_skills`, `final_skills` to `STATE_KEYS`.

### Step 20 — Test
- Unit test: `merge_similar_skills` node (mock LLM, verify clustering and frequency summing)
- Unit test: Skill Finder tools (`get_skills_by_category`, `approve_skill_selection`)
- Unit test: Skill Cleaner tools (`compare_and_clean` with mock book skills)
- Unit test: handoff topology — verify each agent can reach its forward target and Supervisor
- Integration test: full pipeline Supervisor → Skill Finder → Mapper → Cleaner → Linker → Supervisor
- Integration test: teacher "go back" — Supervisor re-enters Skill Finder mid-pipeline
- Verify `:SKILL` label migration
- Run existing test suite for regressions

---

## Architecture Summary

| Agent | Type | Role | Teacher-facing? | Domain Tools | Handoffs |
|-------|------|------|----------------|--------------|----------|
| **Supervisor** | Swarm agent | Search terms, orchestration, final DB write | Yes | save_skills_for_insertion, delete_market_skills, show_current_state | → Skill Finder, → Mapper, → Cleaner, → Linker |
| **Skill Finder** | Swarm agent (NEW) | Fetch jobs, extract, merge, teacher picks skills | Yes | fetch_jobs, select_jobs_by_group, start_extraction, get_skills_by_category, approve_skill_selection | → Mapper, → Supervisor |
| **Skill Extractor** | Subgraph (Send API) | Per-job parallel extraction + LLM merge | No | (deterministic + 1 LLM merge call, no tools) | → Skill Finder (via Command) |
| **Curriculum Mapper** | Swarm agent | Map curated skills to chapters | No | list_chapters, get_chapter_details, get_section_concepts, check_skills_coverage, get_extracted_skills, save_curriculum_mapping | → Skill Cleaner, → Supervisor |
| **Skill Cleaner** | Swarm agent (NEW) | Compare market vs book skills per chapter, drop redundant | No | load_mapped_skills, load_book_skills_for_chapters, compare_and_clean, finalize_cleaned_skills | → Concept Linker, → Supervisor |
| **Concept Linker** | Swarm agent | Extract concepts for final clean skills | No | extract_concepts_for_skills, insert_market_skills_to_neo4j | → Supervisor |

---

## Data Flow Through `tool_store`

```
tool_store["fetched_jobs"]     ← Skill Finder (fetch_jobs)
tool_store["selected_jobs"]    ← Skill Finder (select_jobs_by_group)
tool_store["extracted_skills"] ← Extractor (synthesize + merge)
tool_store["curated_skills"]   ← Skill Finder (approve_skill_selection)
tool_store["mapped_skills"]    ← Mapper (save_curriculum_mapping) — {chapter_id: [skills]}
tool_store["final_skills"]     ← Skill Cleaner (finalize_cleaned_skills) — cleaned list
tool_store["concepts"]         ← Concept Linker (extract_concepts_for_skills)
```
