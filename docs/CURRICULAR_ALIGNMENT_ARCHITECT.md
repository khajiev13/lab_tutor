# Curricular Alignment Architect — Architecture & Design Document

> **Module**: `backend/app/modules/curricularalignmentarchitect/`
> **Pattern**: Multi-phase LangGraph workflow with HITL interrupts
> **Version**: 1.0

---

## 1. Purpose

The Curricular Alignment Architect (CAA) automates the process of finding, evaluating, downloading, and analyzing textbooks for a university course. It enables teachers to:

1. Discover relevant textbooks via LLM-guided web search
2. Score each book against course-specific criteria (topic alignment, structure, scope, etc.)
3. Download selected books (PDF) or manually upload them
4. Extract chapters, sections, concepts, and skills from book content
5. Build chapter-level alignment between the course curriculum and textbook concepts

---

## 2. System Architecture

### 2.1 High-Level Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        React Frontend                            │
│   (Session wizard — discovery → scoring → review → download)     │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           │ POST /book-selection/sessions
                           │ POST /sessions/{id}/run
                           │ POST /sessions/{id}/select
                           │ POST /courses/{id}/analysis/{run}/agentic  (SSE)
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                    FastAPI Routes                                 │
│   book_selection.py, agentic_analysis.py, chapter_analysis.py    │
│   extraction_inspector.py, recommendations.py, analysis.py      │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│               BookSelectionService (Orchestrator)                 │
│   start_session → run_discovery → resume_scoring →               │
│   select_books → download → chunking pipeline                    │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│               LangGraph Workflow Engine                           │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ Main Orchestrator                                         │   │
│  │                                                           │   │
│  │  fetch_course ─▶ discover_books ─▶ score_book ─▶          │   │
│  │       │              (fan-out)      (fan-out)             │   │
│  │       │                                                   │   │
│  │       └─▶ hitl_review ─▶ download_book ─▶ END            │   │
│  │           (interrupt)     (fan-out)                        │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  Sub-graphs:                                                     │
│  ├── Discovery: generate_queries → search_and_extract → dedup   │
│  ├── Scoring:   research ⇄ tools → score  (ReAct loop, max 5)  │
│  └── Download:  search ⇄ tools → extract_urls → attempt → retry│
│                                                                   │
│  Checkpointing: AsyncPostgresSaver (psycopg connection pool)    │
└────────────────┬───────────────────┬──────────────┬──────────────┘
                 │                   │              │
    ┌────────────▼──┐    ┌──────────▼───┐   ┌──────▼──────┐
    │  PostgreSQL    │    │    Neo4j      │   │ Azure Blob  │
    │  Sessions,     │    │  BOOK,        │   │ PDF storage │
    │  CourseBook,   │    │  CHAPTER,     │   │             │
    │  Checkpoints   │    │  SECTION,     │   │             │
    │                │    │  CONCEPT,     │   │             │
    │                │    │  SKILL        │   │             │
    └────────────────┘    └──────────────┘   └─────────────┘
```

### 2.2 Module Structure

| File / Directory | Responsibility |
|-----------------|----------------|
| `models.py` | SQLAlchemy: `BookSelectionSession`, `CourseBook`, `ExtractionRun` |
| `schema.py` | Pydantic DTOs: `SessionRead`, `StartSessionRequest`, `BookCandidateRead` |
| `service.py` | `BookSelectionService` — orchestration, session management, state transitions |
| `repository.py` | SQL data access (sessions, books, extraction runs) |
| `graph.py` | Combined LangGraph workflow builder (`build_book_selection_graph()`) |
| `pdf_extraction.py` | PDF parsing utilities |
| `api_routes/` | 6 route modules combined under `/book-selection` prefix |
| `book_selection/` | Sub-workflow: discovery, scoring, download graphs |
| `chunking_analysis/` | Sub-workflow: document chunking & embedding |
| `cache/` | LRU JSON cache utilities |

### 2.3 Book Selection Sub-Graphs

#### Discovery Sub-Graph (Parallel Search)

```
START ─▶ generate_queries ──[fan_out]──▶ search_and_extract ─▶ deduplicate_books ─▶ END
              │                              (parallel per query)
              │
         LLM generates 10-12
         diverse search queries
         from course context
```

- **generate_queries** — LLM creates search queries from course title, description, documents
- **search_and_extract** — Dual search (Google Books + Tavily) per query; LLM extracts candidates
- **deduplicate_books** — Fuzzy-match titles; pick best entry per group

#### Scoring Sub-Graph (ReAct Loop)

```
START ─▶ research ──[route]──┬─▶ tools ──┐
              ▲              │           │
              └──────────────┘           │
              (loop up to 5 rounds)      │
                                         ▼
                                       score ─▶ END
```

- **research** — LLM agent with bound tools; investigates book quality
- **tools** — Execute tool calls (max 5 rounds)
- **score** — LLM generates structured `BookMeritScores` (7 criteria)

**Scoring Criteria & Default Weights:**

| Criterion | Weight | Description |
|-----------|--------|-------------|
| `C_topic` | 0.30 | Topic relevance to course |
| `C_struc` | 0.20 | Structure and organization |
| `C_scope` | 0.15 | Scope coverage |
| `C_pub` | 0.15 | Publisher reputation |
| `C_auth` | 0.10 | Author credentials |
| `C_time` | 0.10 | Currency / recency |
| `C_prac` | configurable | Practical value |

#### Download Sub-Graph (Search + Validate + Retry)

```
START ─▶ dl_search ──[route]──┬─▶ dl_tools ──┐
              ▲               │              │
              └───────────────┘              │
              (max 4 search rounds)          ▼
                                      extract_urls
                                             │
                                      attempt_download
                                        │         │
                                    success     failure
                                        │         │
                                       END    retry_feedback
                                              (max 5 retries)
```

- **dl_search** — Find download sources (Tavily, libraries, archives)
- **dl_extract_urls** — LLM extracts candidate URLs with confidence scores (1.0 = direct PDF, 0.5 = book page, etc.)
- **dl_attempt_download** — Try top URLs; validate PDF (page count, title match)
- **dl_retry_feedback** — Inject failure context; reset search budget

---

## 3. Agent Workflow — Complete Pipeline

```
                         TEACHER
                           │
              ┌────────────▼────────────┐
              │  PHASE 1: CONFIGURE     │
              │  Create session         │
              │  Set scoring weights    │
              │  Set course level       │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  PHASE 2: DISCOVER      │
              │  10-12 search queries   │
              │  → parallel web search  │
              │  → merge & deduplicate  │
              │                         │
              │  Output: candidate list │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  PHASE 3: SCORE         │
              │  Fan-out per book       │
              │  ReAct research loop    │
              │  7-criteria evaluation  │
              │  Weighted final score   │
              │                         │
              │  Output: ranked books   │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  PHASE 4: REVIEW (HITL) │
              │  Teacher reviews scores │
              │  Selects books (top 5)  │
              │  interrupt() + resume   │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  PHASE 5: DOWNLOAD      │
              │  Fan-out per book       │
              │  Search → extract URLs  │
              │  → download & validate  │
              │  → retry on failure     │
              │  OR: manual upload      │
              │                         │
              │  Store PDF → Azure Blob │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────────────┐
              │  PHASE 6: EXTRACT & ANALYZE     │
              │  Agentic extraction (SSE):      │
              │  - Chapter-level concept        │
              │    recognition                  │
              │  - Skill extraction per chapter │
              │  - Concept similarity scoring   │
              │                                 │
              │  Write to Neo4j:                │
              │    BOOK → CHAPTER → SECTION     │
              │    CONCEPT, BOOK_SKILL, MENTIONS│
              └─────────────────────────────────┘
```

### 3.1 Session Status Transitions

```
CONFIGURING ──▶ DISCOVERING ──▶ SCORING ──▶ AWAITING_REVIEW
                                                    │
                                           ┌────────▼────────┐
                                           │ Teacher selects  │
                                           └────────┬────────┘
                                                    │
                                           DOWNLOADING ──▶ COMPLETED
                                                    │
                                               (on failure)
                                                    │
                                                 FAILED
```

---

## 4. Data Models

### 4.1 SQLAlchemy Models

```python
BookSelectionSession
  ├── id: int (PK)
  ├── course_id: int (FK → courses)
  ├── thread_id: str (unique, for LangGraph checkpointing)
  ├── status: SessionStatus
  ├── weights_json: str (scoring weight configuration)
  ├── course_level: str ("bachelor" | "master" | "phd")
  ├── discovered_books_json: str (raw discovery results)
  ├── progress_scored / progress_total: int
  └── books: list[CourseBook]

CourseBook
  ├── id: int (PK)
  ├── session_id / course_id: int (FKs)
  ├── title, authors, publisher, year: str
  ├── s_final: float (weighted score)
  ├── scores_json: str (per-criterion breakdown)
  ├── selected_by_teacher: bool
  └── download_status: DownloadStatus
```

### 4.2 LangGraph State Schemas

| State | Key Fields |
|-------|-----------|
| `WorkflowState` | `course_id`, `course_context`, `weights`, `discovered_books`, `scored_books`, `top_books`, `download_results` |
| `DiscoveryState` | `course_context`, `search_queries`, `raw_books`, `discovered_books` |
| `ScoringState` | `messages`, `tool_rounds`, `book`, `weights`, `final_scores` |
| `DownloadState` | `messages`, `tool_rounds`, `book`, `candidate_urls`, `download_result`, `download_attempts`, `failed_urls` |

---

## 5. Neo4j Graph Schema

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
          ┌────────▼──┐   ┌───▼──────────┐
          │BOOK_SECTION│  │ BOOK_SKILL    │
          └────┬───────┘  └───┬───────────┘
               │              │
      MENTIONS │  REQUIRES_   │
               │  CONCEPT     │
          ┌────▼──────────────▼──┐
          │       CONCEPT        │
          └──────────────────────┘
```

---

## 6. API Reference

All endpoints under prefix `/book-selection`. Teacher role required.

### Session Management

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create book selection session |
| `GET` | `/sessions/{id}` | Get session state + progress |
| `POST` | `/sessions/{id}/run` | Start discovery + scoring |
| `POST` | `/sessions/{id}/resume` | Resume after HITL review |
| `POST` | `/sessions/{id}/rediscover` | Restart discovery |
| `GET` | `/sessions/{id}/books` | List candidate books |

### Book Selection & Download

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{id}/select` | Start download for selected books |
| `POST` | `/sessions/{id}/reselect` | Restart downloads |
| `POST` | `/sessions/{id}/books/{book_id}/upload` | Manual PDF upload |
| `POST` | `/courses/{id}/bookselection/upload` | Upload custom book |

### Analysis & Extraction

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/courses/{id}/analysis/{run}/agentic` | SSE: chapter extraction pipeline |
| `POST` | `/courses/{id}/analysis/{run}/chapter-scoring` | Compute chapter similarity |
| `GET` | `/courses/{id}/analysis/{run}/chapter-summaries` | Chapter analysis results |

### Course Books

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/courses/{id}/books` | List all books for course |
| `GET` | `/courses/{id}/session` | Get active session |
| `GET` | `/courses/{id}/selected-books` | List selected books |

---

## 7. External Dependencies

| Service | Usage |
|---------|-------|
| **PostgreSQL** | Session state, book metadata, scoring results, checkpoints |
| **Neo4j** | Course context (read), book/chapter/concept graph (write) |
| **Azure Blob Storage** | Store downloaded + uploaded PDFs |
| **OpenAI-compatible LLM** | Query generation, book extraction, scoring, concept recognition |
| **Tavily** | Web search for book discovery and download sources |
| **Google Books API** | Book metadata search |
| **LangGraph** | Workflow orchestration with fan-out, HITL interrupts, checkpointing |

---

## 8. SSE Event Types (Agentic Extraction)

| Event | Payload | When |
|-------|---------|------|
| `loading_book` | `{book_id, title}` | Preparing book for extraction |
| `book_started` | `{book_id, chapter_count, chapters}` | Extraction begins |
| `agent_status` | `{chapter, status, progress}` | Worker progress |
| `chapter_completed` | `{chapter_id, concepts, skills}` | Chapter done |
| `chapter_error` | `{chapter_id, error}` | Chapter failed |
| `book_completed` | `{book_id, stats}` | Book extraction done |
| `done` | `{summary}` | Pipeline complete |
| `error` | `{message}` | Fatal failure |
