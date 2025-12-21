# Neo4j Integration Plan (Backend)

## Goal
Mirror the **domain state** of the FastAPI backend into a **Neo4j (cloud) knowledge graph**, while keeping **SQLite (SQLAlchemy)** as the system of record.

- Mirror everything **except authentication internals** (e.g., hashed passwords, reset tokens, JWTs).
- Users *as domain actors* (Student/Teacher) **should** exist in Neo4j.
- Keep consistent with the repo’s backend patterns: `modules/*` (routes → service → repository), shared infra in `core/` + `providers/`.

## Scope (What gets mirrored)
From existing SQL models:
- `User` → Neo4j nodes `:STUDENT` or `:TEACHER` (role-based label) using `users.id`.
- `Course` → Neo4j node `:CLASS` using `courses.id`.
- `CourseEnrollment` → Neo4j relationship `(:STUDENT)-[:ENROLLED_IN_CLASS]->(:CLASS)`.

From extraction / KG-building:
- `CHAPTER`, `THEORY`, `SKILL`, `CONCEPT`, `READING`, `VIDEO`, and their relationships.
- Extraction outputs should attach to `:CLASS` (course) and/or `:CHAPTER` depending on the ingestion strategy.

## Non-goals (for first iteration)
- Full event-sourcing or CDC.
- Exactly-once guarantees across SQL + Neo4j.
- Real-time per-query consistency between SQL and Neo4j.

The system will be **eventually consistent** with clear retry semantics.

---

## Folder / Module Plan (Backend)

### New shared infra
- `backend/app/core/neo4j.py`
  - Create and close a single **Neo4j Driver** for the app process.
  - Construct the driver with `neo4j.GraphDatabase.driver(...)`.
  - Call `driver.verify_connectivity()` at startup to fail fast.
  - Provide FastAPI dependencies for per-request/per-job **sessions** (context-managed).
  - Prefer **managed transactions** (`session.execute_read()` / `session.execute_write()`) or `driver.execute_query()`.

### Settings
Extend `backend/app/core/settings.py` with:
- `neo4j_uri: str | None`
- `neo4j_username: str | None`
- `neo4j_password: str | None`
- `neo4j_database: str = "neo4j"`

Environment variable names should follow your existing prefix:
- `LAB_TUTOR_NEO4J_URI`
- `LAB_TUTOR_NEO4J_USERNAME`
- `LAB_TUTOR_NEO4J_PASSWORD`
- `LAB_TUTOR_NEO4J_DATABASE`

Note: `backend/.env` is currently empty. In Docker, `docker-compose.yml` injects `env_file: .env` from the repo root. Decide one source of truth:
- Recommended: use repo root `.env` for docker-compose runs, keep `backend/.env` for local `uv run`.

### New domain module (graph sync)
- `backend/app/modules/graph_sync/`
  - `service.py`: idempotent upsert routines to mirror SQL actions into Neo4j
  - `cypher.py`: centralized Cypher statements (so modules don’t embed raw Cypher strings everywhere)
  - (optional) `schemas.py`: internal DTOs for graph operations

### Where to call graph sync
Keep writes in the **service layer**, not in routes or repositories.

- `backend/app/modules/courses/service.py`
  - after SQL commit for: create/update/delete course, join/leave enrollment
  - in extraction worker: after extraction completion, insert/update CHAPTER/THEORY/SKILL/CONCEPT subgraph

- `backend/app/modules/auth/` (domain-related only)
  - after user registration/update: upsert `:STUDENT` or `:TEACHER` node in graph
  - do not mirror password hashes / auth artifacts

---

## Neo4j Connection Best Practice (Driver vs Session)

- **Driver**: one per process (thread-safe, owns connection pool)
- **Session**: one per request/job (not thread-safe, lightweight)

Neo4j Python Driver 6.0 notes:
- `Driver` objects are **thread-safe**, but `driver.close()` is **not** concurrency-safe—only close during app shutdown.
- `Session` objects are lightweight, **not safe for concurrent use**, and should be short-lived.
- Prefer **managed transactions** (`execute_read` / `execute_write`) because they include retry behavior for retryable errors.

### FastAPI integration pattern
- In `backend/main.py` lifespan:
  - create driver once
  - `verify_connectivity()` to fail fast if misconfigured
  - store on `app.state.neo4j_driver`
  - close driver on shutdown

- Dependency injection:
- Dependency injection:
  - `get_neo4j_driver(request: Request) -> Driver`
  - `get_neo4j_session(...) -> Iterator[Session]` (yields, then closes)

Recommended session usage in repositories/services:
- Use `with driver.session(database=settings.neo4j_database) as session:` or yield the session via `Depends`.
- Prefer `session.execute_write(tx_fn, ...)` / `session.execute_read(tx_fn, ...)`.
- Use auto-commit (`session.run(...)`) only when you explicitly need Cypher that manages its own transactions (e.g., `CALL { ... } IN TRANSACTIONS`).

Optional convenience API:
- For very simple one-shot queries, Neo4j 6.0 provides `driver.execute_query(...)` which wraps session + managed transaction for you.

Optional causal chaining:
- If you ever need reads in separate sessions to observe previous writes across threads/tasks/hosts, use a shared `BookmarkManager` (e.g., `GraphDatabase.bookmark_manager(...)`).

This ensures every module reuses the same driver pool and still gets isolated sessions.

### URI scheme guidance (cloud)
- For Neo4j Aura/cloud, prefer `neo4j+s://...` (TLS with system CA validation).
- For local Docker/dev, `bolt://localhost:7687` is typical.
- Prefer specifying `database=` explicitly in sessions for performance and predictability.

---

## Graph Schema (Based on Provided Diagram)

### Node labels
- `:STUDENT`
- `:TEACHER`
- `:CLASS` (maps to `Course`)
- `:CHAPTER`
- `:THEORY`
- `:SKILL`
- `:CONCEPT`
- `:READING`
- `:VIDEO`
- `:METADATA`

Optional/time-series:
- `:PROGRESS` (only if you want progress history as nodes)

### Core relationships
From your diagram (names preserved where visible):
- `(:STUDENT)-[:ENROLLED_IN_CLASS]->(:CLASS)`
- `(:TEACHER)-[:TEACHES_CLASS]->(:CLASS)` **(explicitly added as requested)**
- `(:CLASS)-[:COVERS_CHAPTER]->(:CHAPTER)`
- `(:CHAPTER)-[:NEXT_CHAPTER]->(:CHAPTER)`
- `(:CHAPTER)-[:HAS_THEORY]->(:THEORY)`
- `(:THEORY)-[:NEXT_THEORY]->(:THEORY)`
- `(:THEORY)-[:HAS_SKILL]->(:SKILL)`
- `(:THEORY)-[:HAS_READING]->(:READING)`
- `(:THEORY)-[:HAS_VIDEO]->(:VIDEO)`
- `(:THEORY)-[:HAS_CONCEPT]->(:CONCEPT)`
- `(:READING)-[:COVERS_CONCEPT]->(:CONCEPT)`
- `(:VIDEO)-[:COVERS_CONCEPT]->(:CONCEPT)`

From diagram (progress/mastery):
- `(:STUDENT)-[:MASTERS_SKILL]->(:SKILL)`

Recommended modeling:
- Store *current* mastery as relationship properties on `MASTERS_SKILL`:
  - `current_mastery`, `confidence`, `predicted_next`, `trend`, `num_assessments`, `mastery_category`, `updated_at`
- Store *history* as nodes only if needed:
  - `(:STUDENT)-[:HAS_PROGRESS]->(:PROGRESS)-[:FOR_SKILL]->(:SKILL)`

Metadata:
- `(:STUDENT)-[:HAS_METADATA]->(:METADATA)`

Concept-to-concept relations:
Your diagram shows a “CONCEPT_RELATION” construct with properties like `type`, `reason`.
Recommended in Neo4j:
- model it as a relationship with properties:
  - `(:CONCEPT)-[:CONCEPT_RELATION {type, reason}]->(:CONCEPT)`

### Node properties (minimum viable)
- `STUDENT` / `TEACHER`:
  - `id` (SQL int, unique)
  - `first_name`, `last_name`
  - `created_at`
- `CLASS`:
  - `id` (SQL int, unique)
  - `title`, `description`, `created_at`
  - `extraction_status`
- `CHAPTER`:
  - `id` (string or uuid), `name`, `order`
- `THEORY`:
  - `id`, `name`, `summary`
- `SKILL`:
  - `id`, `name`
- `CONCEPT`:
  - `name` (and optionally `course_id` if you need scoping)
  - `definition`, `text_evidence`, `created_at`
- `READING` / `VIDEO`:
  - `id` or `url`, `title`

### Constraints / indexes (recommended)
Create once (admin task / startup initializer):
- Unique constraints:
  - `(:STUDENT {id})`, `(:TEACHER {id})`, `(:CLASS {id})`
  - plus `(:CHAPTER {id})`, `(:THEORY {id})`, `(:SKILL {id})` if you use stable IDs
- Indexes:
  - `CLASS(title)`
  - `CONCEPT(name)` (or composite `(course_id, name)` if concepts are course-scoped)

---

## SQL → Neo4j Sync Strategy (Best practice for FastAPI)

### Principle
SQL commit succeeds first, then Neo4j is updated.

Two viable approaches:

#### A) Synchronous (simple, stronger consistency)
- After SQL commit, run Neo4j upsert in the same request.
- If Neo4j fails, return 5xx (or 202 + retry) depending on endpoint.

Good for: small graph updates like course creation or join/leave.

#### B) Asynchronous via BackgroundTasks (recommended here)
- After SQL commit, enqueue a background task to update Neo4j.
- Persist a “sync status” in SQL (optional) and retry on failure.

Good for: extraction ingestion, large writes, cloud Neo4j latency.

Recommendation:
- Use **A** for create/update/delete course and join/leave if you want immediate graph consistency.
- Use **B** for extraction ingestion and any bulk graph work.

### Idempotency rules (critical)
All Neo4j writes must be repeatable:
- Use `MERGE` on unique keys (`id` or `(course_id, name)`)
- Set properties with `SET ... = ...`
- Create relationships with `MERGE` to avoid duplicates

---

## Concrete Implementation Steps

### Step 1 — Add Neo4j driver dependency
- Add dependency: `neo4j>=6` to `backend/pyproject.toml`.
- Implement `backend/app/core/neo4j.py`:
  - `create_driver()` using `GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password), ...)`
  - `driver.verify_connectivity()` during lifespan startup
  - `get_neo4j_session()` dependency that yields `driver.session(database=settings.neo4j_database)` and closes it
  - safe `driver.close()` on shutdown

Acceptance:
- Backend starts with Neo4j configured and logs successful connectivity.
- Backend still starts when Neo4j vars are missing (feature disabled) **or** fails fast (choose one policy and document).

### Step 2 — Add graph sync service
- Create `backend/app/modules/graph_sync/service.py` with functions like:
  - `upsert_user(user)`
  - `upsert_course(course, teacher)`
  - `link_teacher_teaches_class(teacher_id, course_id)`
  - `link_student_enrolled(student_id, course_id)`
  - `unlink_student_enrolled(student_id, course_id)`

Acceptance:
- Functions only require a Neo4j session + primitive fields/DTOs.
- All queries are idempotent (`MERGE`).

### Step 3 — Wire writes from existing services
- In `courses/service.py`:
  - after `create_course`: upsert `CLASS` and `TEACHER-TEACHES_CLASS-CLASS`
  - after `join_course`/`leave_course`: add/remove `ENROLLED_IN_CLASS`
  - after `update_course`: update `CLASS` properties
  - after `delete_course`: delete `CLASS` node and related edges (or mark as archived)

Acceptance:
- Creating a course creates/updates corresponding `CLASS` node.
- Joining/leaving updates `ENROLLED_IN_CLASS` edge.

### Step 4 — Extraction to graph ingestion (you can skip this phase for now)
- After extraction finishes, create/update:
  - `CLASS -> CHAPTER -> THEORY -> (SKILL, CONCEPT, READING, VIDEO)`
  - concept relations (`CONCEPT_RELATION`) as needed

Acceptance:
- Running extraction produces a navigable graph under the course.

### Step 5 — Observability + retries
- Add structured logging for graph sync operations.
- For background ingestion: retry with exponential backoff (simple loop + sleep) or queue system later.

Acceptance:
- Neo4j outage doesn’t corrupt SQL state; graph sync is retryable.

### Step 6 — Tests
- Unit tests: patch/mocks for graph sync service.
- Optional integration tests: run Neo4j test container.

Acceptance:
- Tests validate Cypher is called with expected params.

---


