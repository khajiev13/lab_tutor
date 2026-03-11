# Market Demand Analyst — Architecture & Design Document

> **Module**: `backend/app/modules/marketdemandanalyst/`
> **Pattern**: LangGraph multi-agent swarm with human-in-the-loop
> **Version**: 1.0

---

## 1. Purpose

The Market Demand Analyst is a **4-agent AI system** that bridges the gap between real-world job market requirements and a university course curriculum stored in a Neo4j knowledge graph. It enables teachers to:

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
                            │            | tool_start | tool_end
                            │            | state_update | stream_end)
┌───────────────────────────▼─────────────────────────────────────────┐
│                      FastAPI SSE Router                              │
│   routes.py — per-session graph, event serialization                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                    LangGraph Swarm Runtime                           │
│                                                                      │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │ Job Analyst   │───▶│ Skill Extractor  │───▶│Curriculum Mapper │   │
│  │ (entry point) │◀───│                  │    │                  │   │
│  │               │◀───┤                  │    │                  │   │
│  │               │    └──────────────────┘    └────────┬─────────┘   │
│  │               │◀────────────────────────────────────┘             │
│  │               │                                                   │
│  │               │───▶┌──────────────────┐                          │
│  │               │◀───│ Concept Linker   │                          │
│  └──────────────┘    └──────────────────┘                          │
│                                                                      │
│  Shared: tool_store (module-level dict)                              │
│  Checkpointing: MemorySaver (per thread_id)                         │
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
| `state.py` | `AgentState` TypedDict + `tool_store` (shared mutable dict) |
| `graph.py` | Builds the 4-agent LangGraph swarm with handoff tools |
| `prompts.py` | System prompts for each agent role |
| `tools.py` | All tool implementations (14 tools), Neo4j driver, LLM helpers |
| `routes.py` | FastAPI SSE endpoint, per-session graph management |
| `chat.py` | Terminal CLI for development/debugging |
| `__main__.py` | Entry point for `python -m` invocation |

### 2.3 Agent Definitions

| Agent | Role | Tools | Handoffs To |
|-------|------|-------|-------------|
| **Job Analyst** 📊 | Orchestrator. Guides teacher through discovery and approval. | `fetch_jobs`, `select_jobs_by_group`, `save_skills_for_insertion`, `delete_market_skills`, `show_current_state` | Skill Extractor, Concept Linker |
| **Skill Extractor** 🧠 | Parallel LLM extraction of skills from job descriptions. | `extract_skills_llm` | Curriculum Mapper, Job Analyst |
| **Curriculum Mapper** 🗺️ | Compares extracted skills with Neo4j knowledge graph. | `list_chapters`, `get_chapter_details`, `get_section_concepts`, `check_skills_coverage`, `get_extracted_skills`, `save_curriculum_mapping` | Job Analyst |
| **Concept Linker** 🔗 | Determines concepts per skill. Writes everything to Neo4j. | `extract_concepts_for_skills`, `insert_market_skills_to_neo4j` | Job Analyst |

---

## 3. Agent Workflow

### 3.1 Complete Pipeline

```
                            USER (Teacher)
                                │
                     ┌──────────▼──────────┐
                     │   PHASE 1: DISCOVER  │
                     │   (Job Analyst)       │
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
              HANDOFF: transfer_to_skill_extractor
              ══════════════════╪═══════════════════
                                │
                     ┌──────────▼──────────┐
                     │   PHASE 2: EXTRACT   │
                     │  (Skill Extractor)    │
                     └──────────┬──────────┘
                                │
                     extract_skills_llm()
                     (parallel batches of 5)
                                │
                     Present skill summary
                                │
              ══════════════════╪═══════════════════
              HANDOFF: transfer_to_curriculum_mapper
              ══════════════════╪═══════════════════
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
              HANDOFF: transfer_to_job_analyst
              ══════════════════╪═══════════════════
                                │
                     ┌──────────▼──────────┐
                     │  PHASE 4: APPROVE    │
                     │  (Job Analyst)        │
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
              HANDOFF: transfer_to_concept_linker
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
              HANDOFF: transfer_to_job_analyst
              ══════════════════╪═══════════════════
                                │
                     ┌──────────▼──────────┐
                     │  PHASE 6: REPORT     │
                     │  (Job Analyst)        │
                     └──────────┬──────────┘
                                │
                     Final summary to teacher
                     "X skills added, Y concepts
                      linked, Z new concepts"
```

### 3.2 State Transitions

```
            ┌─────────────────────────────────────┐
            │                                     │
            ▼                                     │
     ┌─────────────┐   confirm    ┌────────────┐  │
────▶│ job_analyst  │────────────▶│  skill_     │  │
     │ (Phase 1)    │             │  extractor  │  │
     └──────┬───────┘             └─────┬──────┘  │
            │ ▲                         │         │
            │ │ mapping done            │ skills  │
            │ │                         │ done    │
            │ │  ┌──────────────┐       │         │
            │ └──│ curriculum_  │◀──────┘         │
            │    │ mapper       │                  │
            │    └──────────────┘                  │
            │                                     │
            │ approved    ┌──────────────┐        │
            └────────────▶│  concept_    │────────┘
                          │  linker     │  insertion done
                          └──────────────┘
```

---

## 4. Data Flow & Shared State

### 4.1 `tool_store` — The Central Data Bus

All agents share a **module-level dictionary** (`tool_store`) that accumulates data as the pipeline progresses. This avoids passing large payloads through LLM context.

| Key | Set By | Read By | Type | Description |
|-----|--------|---------|------|-------------|
| `fetched_jobs` | `fetch_jobs` | Skill Extractor, Concept Linker | `list[dict]` | Raw job postings (title, company, description, url, site) |
| `job_groups` | `fetch_jobs` | `select_jobs_by_group` | `dict[str, list[int]]` | Normalized title → job indices mapping |
| `selected_jobs` | `select_jobs_by_group` | `extract_skills_llm`, Concept Linker | `list[dict]` | Teacher-chosen job subset |
| `extracted_skills` | `extract_skills_llm` | Curriculum Mapper, Concept Linker | `list[dict]` | `{name, category, frequency, pct}` |
| `total_jobs_for_extraction` | `extract_skills_llm` | Display tools | `int` | Denominator for frequency percentages |
| `curriculum_mapping` | `save_curriculum_mapping` | Job Analyst (Phase 2), Concept Linker | `list[dict]` | `{name, status, target_chapter, priority, ...}` |
| `selected_for_insertion` | `save_skills_for_insertion` | Concept Linker | `list[dict]` | Teacher-approved final skill list |
| `skill_concepts` | `extract_concepts_for_skills` | `insert_market_skills_to_neo4j` | `dict[str, dict]` | Per-skill concept mapping with provenance |
| `insertion_results` | `insert_market_skills_to_neo4j` | Job Analyst (Phase 6) | `dict` | Write statistics |

### 4.2 Data Volume Boundaries

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
| `tool_end` | `{toolCallId, toolName, result, status}` | Tool returns |
| `state_update` | `{stateKey, value}` | A `tool_store` key changed |
| `stream_end` | `{}` | Conversation turn complete |

### 6.3 Session Isolation

Each `thread_id` gets:
- Its own compiled LangGraph instance (separate message history)
- Its own `MemorySaver` checkpoint (survives multi-turn conversations)
- Shared `tool_store` is reset at session start to prevent stale data leakage

---

## 7. API Reference

### 7.1 Routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/market-demand/chat` | JWT | Stream agent conversation via SSE |
| `GET` | `/market-demand/state` | JWT | Return current `tool_store` snapshot |

### 7.2 Tool Inventory

#### Job Analyst Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `fetch_jobs` | `search_terms: str` (comma-separated), `location: str`, `results_per_site: int` | Grouped summary (top 10 groups) |
| `select_jobs_by_group` | `group_names: str` (numbers or names) | Selection confirmation |
| `save_skills_for_insertion` | `skills_json: str` (JSON array) | Save confirmation |
| `delete_market_skills` | `skill_names: str` (names or "all") | Deletion stats |
| `show_current_state` | _(none)_ | One-line state summary |

#### Skill Extractor Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `extract_skills_llm` | _(none — reads from tool_store)_ | Aggregated skill frequencies |

#### Curriculum Mapper Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `list_chapters` | _(none)_ | Chapter list with section/skill counts |
| `get_chapter_details` | `chapter_indices: str` | Sections + existing skills per chapter |
| `get_section_concepts` | `section_refs: str` (e.g. "1.1, 2.2") | Concepts per section with definitions |
| `check_skills_coverage` | `skill_names: str` | Coverage status (covered/partial/new) |
| `get_extracted_skills` | _(none)_ | Market skills from tool_store |
| `save_curriculum_mapping` | `mapping_json: str` | Mapping save confirmation |

#### Concept Linker Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `extract_concepts_for_skills` | _(none — reads from tool_store)_ | Per-skill concept table |
| `insert_market_skills_to_neo4j` | _(none — reads from tool_store)_ | Write statistics |
