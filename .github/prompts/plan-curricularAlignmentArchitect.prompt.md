# Plan: Curricular Alignment Architect — Full Integration

**TL;DR**: Integrate the notebook-only book-selection workflow (`workflow_v3.ipynb`) into the production system as a first-class backend module with routes/service/repository/models, and a modern React frontend tab. The workflow uses **LangGraph checkpointing with `interrupt()`** for HITL: the agent discovers + scores books → pauses → teacher reviews rated books and selects up to 5 → agent resumes to download them → teacher uploads any failures manually. Books land in Azure Blob at `courses/{course_id}/books/` and are tracked in SQL. A new `level` column is added to the `Course` model.

---

## Steps

### A — Backend: SQL Models & Migrations

1. **Add `level` column to `Course` model** in `backend/app/modules/courses/models.py`. Add `CourseLevel` enum (`bachelor`, `master`, `phd`) with default `bachelor`. Add `level: Mapped[CourseLevel]` column.

2. **Update `CourseCreate` / `CourseRead` schemas** in `backend/app/modules/courses/schemas.py` to include `level` field. Update frontend `Course` type in `frontend/src/features/courses/types.ts` to match.

3. **Create `BookSelectionSession` and `CourseBook` SQL models** in a new `backend/app/modules/curricularalignmentarchitect/models.py`:
   - `BookSelectionSession`: `id`, `course_id` (FK), `thread_id` (unique, for LangGraph checkpoint), `status` enum (`configuring`, `discovering`, `scoring`, `awaiting_review`, `downloading`, `completed`, `failed`), `weights_json` (JSON string of the 7 weight values), `course_level`, `created_at`, `updated_at`
   - `CourseBook`: `id`, `session_id` (FK), `course_id` (FK), `title`, `authors`, `publisher`, `year`, `S_final`, `scores_json` (full 7-criteria detail + rationales), `selected_by_teacher` (bool), `download_status` enum (`pending`, `downloading`, `success`, `failed`, `manual_upload`), `download_error`, `blob_path` (nullable), `source_url`, `created_at`

4. **Import new models in** `backend/main.py` model-import section (lines 11–16) so `Base.metadata.create_all` picks them up.

### B — Backend: Repository Layer

5. **Create** `backend/app/modules/curricularalignmentarchitect/repository.py`:
   - `BookSelectionRepository(db: Session)`:
     - `create_session(course_id, thread_id, weights, level) → BookSelectionSession`
     - `get_session(session_id) → BookSelectionSession | None`
     - `get_session_by_thread(thread_id) → BookSelectionSession | None`
     - `get_latest_session(course_id) → BookSelectionSession | None`
     - `update_status(session_id, status)`
     - `upsert_books(session_id, course_id, scored_books: list[dict])` — bulk insert `CourseBook` rows from scoring results
     - `mark_selected(session_id, book_ids: list[int])` — set `selected_by_teacher=True`
     - `update_download_result(book_id, status, blob_path?, error?)`
     - `get_books(session_id) → list[CourseBook]`
     - `get_course_books(course_id) → list[CourseBook]` — all books across sessions for the course

### C — Backend: LangGraph Workflow Service

6. **Create** `backend/app/modules/curricularalignmentarchitect/workflow.py` — refactored from notebook cells into a proper module and each one of them should go into specific python files based on their functionality (e.g. prompts go into `prompts.py`, helper functions go into `utils.py`, node functions go into `nodes.py` etc.):
   - Move all Pydantic models (`SearchQueryBatch`, `DiscoveredBook`, `DiscoveredBookList`, `BookMeritScores`, `CandidateURL`, `CandidateURLList`) here.
   - Move `WorkflowState`, `DiscoveryState`, `ScoringState`, `DownloadState` TypedDicts here.
   - Move all node functions (`generate_queries`, `search_and_extract`, `deduplicate_books`, `res_agent`, `res_tools`, `score_node`, `dl_search_agent`, `dl_search_tools`, `dl_extract_urls`, `dl_attempt_download`, `fetch_course`, `discover_books`, `fan_out`, `score_book_node`, `select_top_books`).
   - Move helper functions (`_course_summary`, `_syllabus_sequence`, `_exec_tools`, `_normalize_title`, `_titles_match`, `_pick_best_entry`, `compute_finals`).
   - Move prompts (`QUERY_GENERATION_PROMPT`, `PER_QUERY_EXTRACTION_PROMPT`, `RESEARCH_PROMPT`, `SCORING_PROMPT_TEMPLATE`, `DOWNLOAD_SEARCH_PROMPT`).
   - **Key change**: Add an `interrupt()` call after `select_top_books` node — the interrupt value will contain the scored book list so the frontend can render the HITL review UI. The teacher's selection is returned via `Command(resume=selected_book_ids)`.
   - **Key change**: Replace the hardcoded `get_course_context(course_id=1)` with a parameterized version that receives `course_id` from the workflow state.
   - **Key change**: Weights become part of `WorkflowState` instead of module-level `WEIGHTS` constant — teacher provides them at session start.
   - **Key change**: `download_file_from_url` results should upload to Azure Blob (via `blob_service.upload_bytes`) instead of saving locally to `backend/data/books/`.
   - Use `settings.llm_model`, `settings.llm_base_url`, `settings.llm_api_key` from `backend/app/core/settings.py` instead of raw env vars.
   - Compile the workflow with a checkpointer: `AsyncSqliteSaver.from_conn_string("data/checkpoints.db")` (or `InMemorySaver` for dev).

7. **Create** `backend/app/modules/curricularalignmentarchitect/schemas.py` — API-facing Pydantic DTOs:
   - `WeightsConfig`: the 7 weight values (default values matching current `WEIGHTS` dict) with validation that they sum to ~1.0
   - `StartSessionRequest`: `course_level` (enum), `weights` (WeightsConfig)
   - `SessionRead`: session info + status
   - `BookCandidateRead`: book title, authors, publisher, year, S_final, all 7 criterion scores + rationales, selected, download_status
   - `SelectBooksRequest`: `book_ids: list[int]` (max 5)
   - `ManualUploadResponse`: blob_path, book_id
   - `StreamEvent`: `type` (enum: `phase_update`, `discovery_progress`, `scoring_progress`, `books_ready`, `download_progress`, `download_complete`, `error`), plus phase-specific fields

8. **Create** `backend/app/modules/curricularalignmentarchitect/service.py`:
   - `BookSelectionService(repo, neo4j_session, blob_service)`:
     - `start_session(course_id, user_id, config: StartSessionRequest) → SessionRead` — creates DB session + unique `thread_id`, returns it
     - `stream_discovery_and_scoring(session_id) → AsyncIterator[StreamEvent]` — runs the LangGraph workflow with `astream(state, config, stream_mode="updates")` until it hits the interrupt; yields SSE events for each phase; persists discovered+scored books to SQL via `repo.upsert_books`; updates session status
     - `get_session_books(session_id) → list[BookCandidateRead]` — returns scored books for review
     - `select_and_download(session_id, selected_book_ids) → AsyncIterator[StreamEvent]` — validates selection (≤5), marks selected books, resumes LangGraph via `Command(resume=selected_ids)`, streams download progress, updates `CourseBook` rows with results (blob_path or error)
     - `upload_book_manually(session_id, book_id, file: UploadFile) → ManualUploadResponse` — uploads to blob at `courses/{course_id}/books/{sanitized_title}.pdf`, updates `CourseBook` with blob_path and `manual_upload` status
     - `upload_custom_book(course_id, file: UploadFile, title, authors?) → CourseBook` — teacher uploads a book not from the agent
   - Factory: `get_book_selection_service(db, neo4j_session) → BookSelectionService`

### D — Backend: Routes

9. **Create** `backend/app/modules/curricularalignmentarchitect/routes.py`:

   | Method | Path | Purpose |
   |--------|------|---------|
   | `POST` | `/book-selection/sessions` | Create session with weights + course_level → returns `SessionRead` with `session_id` |
   | `GET` | `/book-selection/sessions/{session_id}/stream` | SSE: runs discovery+scoring, streams events, pauses at HITL interrupt |
   | `GET` | `/book-selection/sessions/{session_id}` | Get session status + metadata |
   | `GET` | `/book-selection/sessions/{session_id}/books` | Get scored book list for HITL review |
   | `POST` | `/book-selection/sessions/{session_id}/select` | Teacher picks ≤5 books → starts download phase |
   | `GET` | `/book-selection/sessions/{session_id}/download-stream` | SSE: resumes workflow, streams download progress |
   | `POST` | `/book-selection/sessions/{session_id}/books/{book_id}/upload` | Manual file upload for a failed download |
   | `POST` | `/book-selection/courses/{course_id}/books/upload` | Upload a custom book (not from agent) |
   | `GET` | `/book-selection/courses/{course_id}/books` | List all course books (across sessions) |

   All routes require `require_role(UserRole.TEACHER)`. SSE endpoints use `StreamingResponse` with the `_sse_format` pattern from `backend/app/modules/concept_normalization/routes.py`.

10. **Register router in** `backend/main.py` alongside existing routers (line ~131).

### E — Frontend: Types & API

11. **Create** `frontend/src/features/book-selection/types.ts`:
    - `WeightsConfig`, `BookCandidate` (with all 7 criteria + rationales + S_final), `BookSelectionSession`, `StreamEvent` types mirroring backend schemas

12. **Create** `frontend/src/features/book-selection/api.ts`:
    - REST functions: `createSession`, `getSession`, `getSessionBooks`, `selectBooks`, `uploadBook`, `uploadCustomBook`, `getCourseBooks`
    - SSE stream functions: `streamDiscovery(sessionId, onEvent)`, `streamDownload(sessionId, onEvent)` — reuse the fetch+ReadableStream pattern from `frontend/src/services/normalization.ts`

### F — Frontend: Components

13. **Create** `frontend/src/features/book-selection/components/WeightsConfigurator.tsx`:
    - Modern card-based UI with sliders for each of the 7 weight criteria
    - Each criterion shows its name, description (from the rubric), and a slider (0.0–1.0 in 0.05 steps)
    - Live "total" indicator that must sum to ~1.0 (with warning badge if out of range)
    - Course level selector (`Select` component with `bachelor` / `master` / `phd` options)
    - "Start Book Selection" button (disabled until valid)
    - Use Shadcn `Card`, `Slider` (need to add), `Select`, `Badge`, `Button`, `Tooltip`

14. **Create** `frontend/src/features/book-selection/components/AgentStatusPanel.tsx`:
    - Real-time status display while agent is working (streaming SSE events)
    - Shows current phase with icon: "Generating queries…", "Searching (3/12 done)…", "Scoring book 4/15…", etc.
    - Progress bar (`Progress` component) for countable phases (search queries, scoring)
    - Collapsible log of events (scrollable `ScrollArea`)
    - Phase timeline/stepper: Discovery → Scoring → Review → Download → Complete

15. **Create** `frontend/src/features/book-selection/components/BookReviewTable.tsx`:
    - HITL review UI — rendered after scoring completes
    - Sortable table with columns: rank, S_final, S+prac, C_topic, C_struc, C_scope, C_pub, C_auth, C_time, C_prac, title
    - Each row expandable to show detailed rationale for all 7 criteria (accordion style)
    - Checkbox per row for teacher selection (max 5 — counter + validation)
    - "Proceed with Selected Books" button
    - Use Shadcn `Table`, `Card`, `Badge`, `Button`, `Tooltip`, `Alert`

16. **Create** `frontend/src/features/book-selection/components/DownloadResultsPanel.tsx`:
    - Shows download status per book (success / failed / in-progress)
    - For failed books: show error reason + `FileUpload` component (reuse existing `frontend/src/components/FileUpload.tsx`) for manual upload
    - For successful books: show green check + file info

17. **Create** `frontend/src/features/book-selection/components/ManualBookUpload.tsx`:
    - Standalone section for uploading a book the teacher prefers manually (not from agent results)
    - Title, authors, file input
    - Uses the `POST /book-selection/courses/{course_id}/books/upload` endpoint

18. **Create** `frontend/src/features/book-selection/components/CourseBooksList.tsx`:
    - Shows all finalized books for the course (from all sessions + manual uploads)
    - Card grid or list with book metadata, download status badge

19. **Create** `frontend/src/features/book-selection/components/BookSelectionDashboard.tsx`:
    - **Main orchestrator component** (equivalent to `NormalizationDashboard`)
    - State machine driving which sub-component is visible:
      1. **No session / configuring**: show `WeightsConfigurator`
      2. **Discovering/Scoring**: show `AgentStatusPanel` with live SSE stream
      3. **Awaiting review**: show `BookReviewTable` (HITL)
      4. **Downloading**: show `AgentStatusPanel` (download phase) + `DownloadResultsPanel`
      5. **Completed**: show `DownloadResultsPanel` (final) + `ManualBookUpload` + `CourseBooksList`
    - On page load, checks for existing session via `getSession(latestSessionId)` and resumes the correct state

### G — Frontend: Tab Integration

20. **Add "Book Selection" tab** in `frontend/src/features/courses/pages/TeacherCourseDetail.tsx`:
    - New `TabsTrigger value="book-selection"` after the normalization tab trigger (around line 385)
    - New `TabsContent value="book-selection"` containing `<BookSelectionDashboard courseId={course.id} />` with the same extraction-finished guard as normalization
    - Import `BookSelectionDashboard` from the new feature

21. **Add Shadcn Slider component** — run `npx shadcn@latest add slider` since the WeightsConfigurator needs it and it's not currently available.

### H — Blob Storage Adjustments

22. **Modified download flow** in the workflow: instead of `download_file_from_url` saving to `backend/data/books/`, the download node should:
    - Download the file to a temp buffer (in-memory or `tempfile`)
    - Validate file type (PDF/EPUB magic bytes — reuse existing logic from `tools.py`)
    - Upload to Azure Blob via `blob_service.upload_bytes(content, f"courses/{course_id}/books/{safe_filename}.pdf")`
    - Return the blob_path
    - If blob storage unavailable, fall back to local `data/books/` as current behavior

### I — Package Dependencies

23. **Add `langgraph-checkpoint-sqlite`** to `backend/pyproject.toml` for the async SQLite checkpointer (used for HITL interrupt/resume). Verify `langgraph` version supports `interrupt()` (requires ≥ 0.2.x).

---

## Verification

- **Backend unit tests**: Add tests in `backend/tests/modules/test_book_selection.py`:
  - Test `BookSelectionRepository` CRUD operations
  - Test weights validation (sum ≈ 1.0)
  - Test session status transitions
  - Test book selection limit (≤5)
- **Integration test**: Test SSE streaming endpoint with mocked LLM responses
- **Manual test flow**:
  1. Create a course, upload materials, run extraction, run normalization
  2. Go to "Book Selection" tab → configure weights & level → start
  3. Observe agent status panel updating in real-time
  4. Review scored books table → select up to 5 → proceed
  5. Watch download progress → manually upload any failures
  6. Verify books appear in Azure Blob at correct paths
  7. Verify `course_books` SQL table has correct records
- **Run backend tests**: `cd backend && uv run pytest`
- **Run frontend build**: `cd frontend && npm run build` (TypeScript checks)
- **Run lint**: `cd backend && uv run ruff check .` and `cd frontend && npm run lint`

## Design Decisions

- **HITL via LangGraph `interrupt()`** over two-call split — single workflow with checkpoint persistence
- **AsyncSqliteSaver** for checkpointing (matches existing SQLite usage; can upgrade to Postgres later)
- **Blob path**: `courses/{course_id}/books/{filename}.pdf` — course-scoped
- **`level` on Course model** — persisted, reusable across features
- **UI as new tab** after normalization, with agent status panel for real-time feedback
- **Max 5 book selection** enforced both frontend (checkbox counter) and backend (schema validation)
