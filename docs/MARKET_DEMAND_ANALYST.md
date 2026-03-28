# Market Demand Analyst — Architecture & Design Document

> **Module**: `backend/app/modules/marketdemandanalyst/`
> **Pattern**: LangGraph 3-agent swarm with human-in-the-loop
> **Version**: 2.0

---

## 1. Purpose

The Market Demand Analyst is a **3-agent AI system** that bridges the gap between real-world job market requirements and a university course curriculum stored in a Neo4j knowledge graph. It enables teachers to:

1. Discover what skills employers currently demand
2. Compare those skills against their existing curriculum
3. Enrich the knowledge graph with new market-driven skills and concepts

---

## 2. System Architecture

### 2.1 High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        React Frontend                               │
│   (SSE Client — renders agent text, tool calls, state updates)      │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ POST /market-demand/chat
                            │ SSE stream (event: agent_start | text_delta
                            │            | tool_start | tool_args_update
                            │            | tool_end   | state_update
                            │            | stream_end)
┌───────────────────────────▼─────────────────────────────────────────┐
│                      FastAPI SSE Router                              │
│   routes.py — deterministic thread per user, event serialization    │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                    LangGraph Swarm Runtime                           │
│                                                                      │
│  ┌──────────────┐   start_analysis_pipeline()   ┌──────────────────┐│
│  │  Supervisor   │─ ─(programmatic extraction)─ ▶│Curriculum Mapper ││
│  │ (entry point) │◀──transfer_to_supervisor──────│                  ││
│  │               │                               └──────────────────┘│
│  │               │                                                   │
│  │               │───transfer_to_concept_linker──▶┌────────────────┐│
│  │               │◀──transfer_to_supervisor───────│ Concept Linker ││
│  └──────────────┘                                └────────────────┘│
│                                                                      │
│  Shared: tool_store (module-level dict, persisted to PostgreSQL)     │
│  Checkpointing: AsyncPostgresSaver (psycopg connection pool)        │
└─────────────────────┬──────────────────┬────────────────────────────┘
                      │                  │
         ┌────────────▼──┐    ┌──────────▼───────┐
         │  Job Boards    │    │    Neo4j          │
         │  (Indeed,      │    │  Knowledge Graph  │
         │   LinkedIn)    │    │                   │
         └───────────────┘    └──────────────────┘
```

### 2.2 Module Structure

| File | Responsibility |
|------|---------------|
| `state.py` | `AgentState` TypedDict, `tool_store` (shared mutable dict), `snapshot_state()` / `restore_state()`, `pipeline_summary()` |
| `graph.py` | Builds the 3-agent LangGraph swarm via `create_swarm()`, lazy LLM init, `AsyncPostgresSaver` checkpointer |
| `prompts.py` | System prompts for each agent role (Supervisor, Curriculum Mapper, Concept Linker) |
| `tools.py` | All tool implementations (14 tools across 3 groups), Neo4j driver, LLM helpers, job scraping |
| `models.py` | `MDAThreadState` SQLAlchemy model (PostgreSQL JSONB persistence of `tool_store`) |
| `routes.py` | FastAPI SSE endpoint + state/history endpoints, per-user session management |
| `chat.py` | Terminal CLI for development/debugging (Rich-formatted output) |
| `__main__.py` | Entry point for `python -m` invocation |

### 2.3 Agent Definitions

| Agent | Role | Tools | Handoffs To |
|-------|------|-------|-------------|
| **Supervisor** 📊 | Orchestrator. Only agent that talks to the teacher. Guides through discovery and approval. | `fetch_jobs`, `select_jobs_by_group`, `start_analysis_pipeline`, `save_skills_for_insertion`, `delete_market_skills`, `show_current_state` | Curriculum Mapper (via `Command`), Concept Linker (via handoff tool) |
| **Curriculum Mapper** 🗺️ | Autonomous worker. Compares extracted skills with Neo4j knowledge graph. | `list_chapters`, `get_chapter_details`, `get_section_concepts`, `check_skills_coverage`, `get_extracted_skills`, `save_curriculum_mapping` | Supervisor (via handoff tool) |
| **Concept Linker** 🔗 | Autonomous worker. Determines concepts per skill and writes everything to Neo4j. | `extract_concepts_for_skills`, `insert_market_skills_to_neo4j` | Supervisor (via handoff tool) |

> **Note**: Skill extraction is **not** a separate agent. It runs programmatically (parallel LLM batches) inside the `start_analysis_pipeline()` tool, which then routes to Curriculum Mapper via `Command(goto="curriculum_mapper")`.

---

## 3. Agent Workflow

### 3.1 Complete Pipeline

```
                            USER (Teacher)
                                │
                     ┌──────────▼──────────┐
                     │  PHASE 1: DISCOVER   │
                     │    (Supervisor)       │
                     └──────────┬──────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
   Greet teacher          Suggest search       fetch_jobs(terms)
   (knows curriculum)      terms from           ──▶ Indeed
                           chapter topics            LinkedIn
                                │
                     ┌──────────▼──────────┐
                     │  Show grouped results │
                     │  Ask: which groups?   │
                     └──────────┬──────────┘
                                │
                     select_jobs_by_group()
                                │
                     Teacher confirms ✓
                                │
              ══════════════════╪═══════════════════
              start_analysis_pipeline()
              (programmatic extraction + Command)
              ══════════════════╪═══════════════════
                                │
                     ┌──────────▼──────────┐
                     │  PHASE 2: EXTRACT    │
                     │  (Programmatic —     │
                     │   NOT an LLM agent)  │
                     └──────────┬──────────┘
                                │
                     _run_skill_extraction()
                     (parallel LLM batches of 5
                      via ThreadPoolExecutor)
                                │
                     Command(goto="curriculum_mapper")
                                │
                     ┌──────────▼──────────┐
                     │   PHASE 3: MAP       │
                     │ (Curriculum Mapper)   │
                     └──────────┬──────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
   get_extracted_skills   list_chapters()       check_skills_coverage
   (from tool_store)      get_chapter_details   (Neo4j query)
                          get_section_concepts
                                │
                     ┌──────────▼──────────┐
                     │ save_curriculum_mapping│
                     │ covered / gap / new   │
                     └──────────┬──────────┘
                                │
              ══════════════════╪═══════════════════
              transfer_to_supervisor (handoff tool)
              ══════════════════╪═══════════════════
                                │
                     ┌──────────▼──────────┐
                     │  PHASE 4: APPROVE    │
                     │    (Supervisor)       │
                     └──────────┬──────────┘
                                │
                     Present 3 categories:
                     - Already Covered ✓
                     - Gap Skills (new)
                     - New Topics Needed
                                │
                     Teacher discusses, edits,
                     removes irrelevant skills
                                │
                     save_skills_for_insertion()
                                │
              ══════════════════╪═══════════════════
              transfer_to_concept_linker (handoff tool)
              ══════════════════╪═══════════════════
                                │
                     ┌──────────▼──────────┐
                     │   PHASE 5: PERSIST   │
                     │  (Concept Linker)     │
                     └──────────┬──────────┘
                                │
         ┌──────────────────────┼──────────────────┐
         ▼                      ▼                  ▼
   extract_concepts_for_skills  │    insert_market_skills_to_neo4j
   (LLM per skill, Neo4j read) │    (create nodes + relationships)
                                │
              ══════════════════╪═══════════════════
              transfer_to_supervisor (handoff tool)
              ══════════════════╪═══════════════════
                                │
                     ┌──────────▼──────────┐
                     │  PHASE 6: REPORT     │
                     │    (Supervisor)       │
                     └──────────┬──────────┘
                                │
                     Final summary to teacher
                     "X skills added, Y concepts
                      linked, Z new concepts"
```

### 3.2 State Transitions

```
                ┌──────────────────────────────────────┐
                │                                      │
                ▼                                      │
         ┌─────────────┐  start_analysis_pipeline()    │
────────▶│  supervisor  │──(programmatic extraction)──┐│
         │ (Phases 1,4,6)                             ││
         └──────┬───────┘                             ││
                │ ▲                                   ││
                │ │ transfer_to_supervisor             ▼│
                │ │                          ┌──────────────┐
                │ └──────────────────────────│ curriculum_  │
                │                            │ mapper       │
                │                            └──────────────┘
                │                                      │
                │ transfer_to_concept_linker            │
                │                     ┌──────────────┐ │
                └────────────────────▶│  concept_    │─┘
                                      │  linker     │  transfer_to_supervisor
                                      └──────────────┘
```

---

## 4. Data Flow & Shared State

### 4.1 `tool_store` — The Central Data Bus

All agents share a **module-level dictionary** (`tool_store`) that accumulates data as the pipeline progresses. This avoids passing large payloads through LLM context. The store is persisted to PostgreSQL via the `MDAThreadState` model after every state change.

| Key | Set By | Read By | Type | Description |
|-----|--------|---------|------|-------------|
| `fetched_jobs` | `fetch_jobs` | Supervisor, extraction | `list[dict]` | Raw job postings (title, company, description, url, site) |
| `job_groups` | `fetch_jobs` | `select_jobs_by_group` | `dict[str, list[int]]` | Normalized title → job indices mapping, sorted by count desc |
| `selected_jobs` | `select_jobs_by_group` | `_run_skill_extraction`, Concept Linker | `list[dict]` | Teacher-chosen job subset |
| `extracted_skills` | `_run_skill_extraction` | Curriculum Mapper, Concept Linker | `list[dict]` | `{name, category, frequency, pct}` |
| `total_jobs_for_extraction` | `_run_skill_extraction` | Display tools | `int` | Denominator for frequency percentages |
| `existing_graph_skills` | _(reserved)_ | _(unused)_ | `list[dict]` | Reserved for future use |
| `existing_concepts` | _(reserved)_ | _(unused)_ | `list[str]` | Reserved for future use |
| `curriculum_mapping` | `save_curriculum_mapping` | Supervisor (Phase 4), Concept Linker | `list[dict]` | `{name, status, target_chapter, priority, ...}` |
| `selected_for_insertion` | `save_skills_for_insertion` | Concept Linker | `list[dict]` | Teacher-approved final skill list |
| `skill_concepts` | `extract_concepts_for_skills` | `insert_market_skills_to_neo4j` | `dict[str, dict]` | Per-skill concept mapping with provenance |
| `insertion_results` | `insert_market_skills_to_neo4j` | Supervisor (Phase 6) | `dict` | Write statistics |

### 4.2 State Persistence

```
tool_store (in-memory)
       │
       │ snapshot_state()
       ▼
MDAThreadState (PostgreSQL JSONB)
  ┌──────────────────────────────────┐
  │ thread_id:  "mda-{user_id}"     │
  │ state_json: { ... tool_store }   │
  │ updated_at: auto-managed         │
  └──────────────────────────────────┘
       │
       │ restore_state()  (on session load)
       ▼
tool_store (restored)
```

- **`snapshot_state()`** — serializes all `STATE_KEYS` from `tool_store` to a JSON-safe dict
- **`restore_state(state_json)`** — overwrites `tool_store` from a persisted snapshot
- **`pipeline_summary()`** — builds a concise text summary of current progress (e.g., "Fetched 150 jobs in 12 groups | Selected 45 jobs | NEXT: Ask teacher which groups"); injected into every agent's system prompt dynamically
- **`_state_cache`** — in-memory dict avoids repeated PostgreSQL reads (2–3s latency)
- **Background persistence** — `asyncio.create_task(_persist_state_to_db(...))` after each tool finishes (non-blocking)

### 4.3 Data Volume Boundaries

The system is designed to keep **heavy data out of the LLM context**:

```
LLM sees:                           tool_store holds:
─────────                           ─────────────────
"10 groups, top 3                   Full 60+ job objects
 companies each"                    with descriptions

"25 top skills with                 All 100+ skills with
 frequency counts"                  full metadata

"Mapping summary:                   Complete mapping JSON
 5 covered, 8 gaps"                 per skill
```

---

## 5. Neo4j Graph Schema (Market Demand Extension)

### 5.1 Nodes Created

```
(:MARKET_SKILL {
    name:           String,     -- canonical skill name
    category:       String,     -- "language", "framework", "cloud", etc.
    frequency:      Int,        -- # of jobs mentioning this skill
    demand_pct:     Float,      -- frequency / total_jobs × 100
    priority:       String,     -- "high" | "medium" | "low"
    status:         String,     -- "gap" | "new_topic_needed"
    target_chapter: String,     -- chapter title this skill maps to
    rationale:      String,     -- teacher's reason for adding
    reasoning:      String,     -- mapper's automated reasoning
    source:         "market_demand",
    created_at:     DateTime
})

(:JOB_POSTING {
    url:           String,      -- unique identifier
    title:         String,
    company:       String,
    site:          String,      -- "indeed" | "linkedin"
    search_term:   String       -- original query that found this posting
})

(:CONCEPT {
    name:          String,      -- may be NEW (created by concept linker)
    description:   String       -- academic description
})
```

### 5.2 Relationships Created

```
(ch:BOOK_CHAPTER)-[:HAS_SKILL]->(ms:MARKET_SKILL)
    -- Maps skill to its target chapter

(ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp:JOB_POSTING)
    -- Provenance: which job postings evidenced this skill

(ms:MARKET_SKILL)-[:REQUIRES_CONCEPT]->(c:CONCEPT)
    -- Concept dependency (existing or newly created)
```

### 5.3 Extended Graph Schema Diagram

```
                    ┌──────────────────┐
                    │      BOOK        │
                    └────────┬─────────┘
                             │ HAS_CHAPTER
                    ┌────────▼─────────┐
                    │  BOOK_CHAPTER    │
                    └──┬──────────┬────┘
                       │          │
            HAS_SECTION│          │HAS_SKILL
                       │          │
              ┌────────▼──┐   ┌───▼──────────┐   ┌───────────────┐
              │BOOK_SECTION│  │ BOOK_SKILL    │   │ MARKET_SKILL  │
              └────┬───────┘  └───┬───────────┘   └──┬──────┬─────┘
                   │              │                   │      │
          MENTIONS │  REQUIRES_   │    REQUIRES_      │      │
                   │  CONCEPT     │    CONCEPT        │      │ SOURCED_FROM
              ┌────▼──────────────▼────────────────▼──┐  ┌───▼──────────┐
              │          CONCEPT                       │  │ JOB_POSTING  │
              └────────────────────────────────────────┘  └──────────────┘
```

---

## 6. SSE Transport Protocol

### 6.1 Endpoint

```
POST /market-demand/chat
Content-Type: application/json
Authorization: Bearer <jwt>

Body: { "message": "...", "thread_id": "..." }
Response: text/event-stream
```

### 6.2 Event Types

| Event | Payload | When |
|-------|---------|------|
| `agent_start` | `{agent, messageId, displayName, emoji}` | New agent takes control |
| `text_delta` | `{delta, messageId}` | Incremental LLM token |
| `text_done` | `{messageId}` | Agent finished its text block |
| `tool_start` | `{toolName, toolCallId, args, agent}` | Tool invocation begins |
| `tool_args_update` | `{toolCallId, args}` | Full accumulated args revealed |
| `tool_end` | `{toolCallId, toolName, result, status}` | Tool returns |
| `state_update` | `{stateKey, value}` | A `tool_store` key changed (triggers async persistence) |
| `stream_end` | `{}` | Conversation turn complete |

### 6.3 Agent Metadata (Shared with Frontend)

```python
AGENT_META = {
    "supervisor":        {"displayName": "Supervisor",        "emoji": "📊"},
    "curriculum_mapper": {"displayName": "Curriculum Mapper", "emoji": "🗺️"},
    "concept_linker":    {"displayName": "Concept Linker",    "emoji": "🔗"},
}
```

### 6.4 Session Isolation

Each user gets a **deterministic thread**: `f"mda-{user.id}"`.

- LangGraph checkpoint persisted to PostgreSQL via `AsyncPostgresSaver`
- `tool_store` snapshot persisted to `MDAThreadState` table (JSONB)
- In-memory `_state_cache` avoids repeated PostgreSQL reads
- Thread survives server restarts and page refreshes
- `DELETE /market-demand/history` clears both checkpoint and state (Neo4j data is preserved)

---

## 7. API Reference

### 7.1 Routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/market-demand/chat` | JWT | Stream agent conversation via SSE |
| `GET` | `/market-demand/state` | JWT | Return current `tool_store` snapshot |
| `GET` | `/market-demand/history` | JWT | Return reconstructed chat history with agent names |
| `DELETE` | `/market-demand/history` | JWT | Delete thread state + checkpoint (preserves Neo4j data) |

### 7.2 Tool Inventory

#### Supervisor Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `fetch_jobs` | `search_terms: str` (comma-separated), `location: str`, `results_per_site: int` | Grouped summary (top 10 groups) |
| `select_jobs_by_group` | `group_names: str` (numbers or names) | Selection confirmation |
| `start_analysis_pipeline` | _(none — reads from tool_store)_ | Runs extraction programmatically, then `Command(goto="curriculum_mapper")` |
| `save_skills_for_insertion` | `skills_json: str` (JSON array) | Save confirmation |
| `delete_market_skills` | `skill_names: str` (names or "all") | Deletion stats |
| `show_current_state` | _(none)_ | One-line state summary |

#### Curriculum Mapper Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `list_chapters` | _(none)_ | Chapter list with section/skill counts (BOOK_SKILL + MARKET_SKILL) |
| `get_chapter_details` | `chapter_indices: str` | Sections + existing BOOK_SKILL + MARKET_SKILL per chapter |
| `get_section_concepts` | `section_refs: str` (e.g. "1.1, 2.2") | Concepts per section with definitions |
| `check_skills_coverage` | `skill_names: str` | Coverage status (covered/partial/new/already_market_skill⚠️) |
| `get_extracted_skills` | _(none)_ | Market skills from tool_store |
| `save_curriculum_mapping` | `mapping_json: str` | Mapping save confirmation |

#### Concept Linker Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `extract_concepts_for_skills` | _(none — reads from tool_store)_ | Per-skill concept table |
| `insert_market_skills_to_neo4j` | _(none — reads from tool_store)_ | Write statistics |

---

## 8. External Services & Dependencies

### Neo4j
- **Queried by**: Curriculum Mapper (`list_chapters`, `get_chapter_details`, `check_skills_coverage`, etc.), Concept Linker (fetch chapter concepts)
- **Written by**: Concept Linker (`insert_market_skills_to_neo4j`), Supervisor (`delete_market_skills`)
- **Schema nodes**: `USER`, `TEACHER`, `CLASS`, `BOOK`, `BOOK_CHAPTER`, `BOOK_SECTION`, `CONCEPT`, `BOOK_SKILL`, `MARKET_SKILL`, `JOB_POSTING`
- **Relationships**: `TEACHES_CLASS`, `USES_BOOK`, `HAS_CHAPTER`, `HAS_SECTION`, `MENTIONS`, `HAS_SKILL`, `SOURCED_FROM`, `REQUIRES_CONCEPT`
- **Connection**: Cached driver with 5-min rotation (`_get_neo4j_driver(force_new=False)`); auto-reconnects on `SessionExpired` / auth failures

### LLM (OpenAI-compatible)
- **Used by**: All 3 agents (Supervisor, Mapper, Linker) + programmatic extraction
- **Agent LLM**: `ChatOpenAI(temperature=0, streaming=True)`, lazy-initialized and cached globally
- **Extraction LLM**: Separate `ChatOpenAI` instance with `timeout=120s` for batched inference
- **Prompt Building**: Dynamic `_make_prompt()` appends `pipeline_summary()` to system prompt; trims to last 10 messages
- **Config**: `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_API_KEY` env vars

### Job Scraping
- **Library**: `jobspy`
- **Sites**: Indeed, LinkedIn
- **Scraper**: Parallel `ThreadPoolExecutor` (`max_workers=8`)
- **Dedup**: by (title, company) case-insensitive

### PostgreSQL
- **Stores**:
  - `MDAThreadState` (`thread_id`, `state_json` JSONB, `updated_at`)
  - LangGraph checkpoints (messages, agent state) via `AsyncPostgresSaver`
- **Pool**: `AsyncConnectionPool` (min=1, max=5, idle=120s) via `psycopg`
- **Connection string**: `LAB_TUTOR_DATABASE_URL` env var

---

## 9. Key Design Insights

### No Skill Extractor Agent
Skill extraction was originally a 4th agent but is now **batched programmatically** in `_run_skill_extraction()`:
- Batches jobs into groups of 5
- Parallel LLM calls via `ThreadPoolExecutor`
- Merges synonyms (e.g., "k8s" → "Kubernetes")
- Returns JSON with `name`, `category`, `frequency`, `pct`
- Called by `start_analysis_pipeline()` which then routes with `Command(goto="curriculum_mapper")`
- This avoids the overhead of an LLM agent wrapper for a deterministic one-shot task

### Dual Persistence
State survives server restarts through two complementary systems:
- **LangGraph checkpoint** (PostgreSQL via `AsyncPostgresSaver`): message history, agent routing state
- **MDAThreadState** (PostgreSQL JSONB): `tool_store` snapshot with all pipeline data

### Dynamic Context Injection
Every LLM call gets up-to-date pipeline context without requiring tool calls:
- `pipeline_summary()` is appended to every agent's system prompt
- Shows what data exists, what step is next, counts of jobs/skills/mappings
- Example: `"Fetched 150 jobs in 12 groups | Selected 45 jobs | Extracted 38 skills | NEXT: Ask teacher which groups"`

### Lazy Initialization
Both `_COMPILED_GRAPH` and `_LLM_INSTANCE` are cached globally and created on first use, avoiding startup cost when the module is imported but unused.
