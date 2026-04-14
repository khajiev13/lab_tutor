# Lab Tutor — Agent Rules (Cross-Tool)

> This file is read by Antigravity, Cursor, and Claude Code automatically.
> Antigravity-specific overrides live in GEMINI.md.

## Project Overview

Lab Tutor is a monorepo with a React 19 frontend, a FastAPI backend, a Neo4j
knowledge graph, a `knowledge_graph_builder/` Python workspace for graph
ingestion, and `neo4j_database/` infrastructure and migration support.
It hosts four AI agents (Curricular Alignment Architect, Market Demand Analyst,
Textual Resource Analyst, Video Agent) that form an end-to-end curriculum
intelligence pipeline.
The backend exposes `GET /health`, and backend tests depend on a PostgreSQL
test database.

## Tech Stack

- **Frontend**: React 19, Vite, TypeScript (strict), TailwindCSS v4, Shadcn UI
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, LangGraph
- **Databases**: PostgreSQL (relational), Neo4j (knowledge graph), vector embeddings
- **Infra**: Azure Blob Storage, Docker, uv (Python), npm (JS)

## Codex Delegation Pattern

Use a **single coordinator agent** for planning, integration, verification, and user communication.
Spawn **specialized worker agents** only when the task splits cleanly across frontend and backend boundaries.

### Coordinator Agent
- Owns task breakdown, final integration, and verification
- Decides whether to spawn workers based on file ownership and coupling
- Does not delegate the immediate blocking task if the next step depends on it
- Resolves conflicts between frontend and backend changes

### Frontend Worker
- Scope: `frontend/`
- Preferred skills: `shadcn-ui`, `vercel-react-best-practices`
- May also use: `karpathy-guidelines`
- Must follow frontend rules in this file, especially:
  - Use `@/` imports
  - Prefer feature API wrappers in `src/features/*/api.ts`; shared HTTP helpers may live in `src/services/`
  - Use `react-hook-form` + `zod` for forms
  - Use TailwindCSS v4 + `cn()` for styling
  - Run frontend verification inside the Docker containers by default; prefer `lab_tutor_frontend` for lint, build, and test commands
  - Do not install frontend dependencies on the host machine unless the user explicitly asks for that setup
- Must not edit `backend/` files unless explicitly reassigned

### Backend Worker
- Scope: `backend/`
- Preferred skills: `fastapi`, `python-service-patterns`, `postgres-patterns`
- Use when relevant: `neo4j-cypher`, `langgraph-fundamentals`, `langgraph-human-in-the-loop`, `langgraph-persistence`
- May also use: `karpathy-guidelines`
- Must follow backend rules in this file, especially:
  - Preserve or move toward onion architecture under `app/modules/<feature>/`
  - Keep DB access in repository-style modules such as `repository.py` and `neo4j_repository.py`
  - Keep business logic in `service.py`
  - Use `Depends()` for injection
  - Run backend verification inside the Docker containers by default; prefer `lab_tutor_backend` for app/test commands and `lab_tutor_postgres` for the test database
  - Do not install backend test dependencies on the host machine unless the user explicitly asks for that setup
- Must not edit `frontend/` files unless explicitly reassigned

### Delegation Rules
- Prefer one worker when the change is isolated to one side of the stack
- Spawn both workers only when the work can proceed in parallel with disjoint ownership
- Give each worker explicit file ownership in the prompt
- Name the skills to use in the worker prompt; do not assume skills are attached automatically
- Coordinator keeps ownership of cross-cutting docs, final cleanup, and verification
- If a task touches shared contracts, define the API/schema boundary first, then split implementation

### Reusable Codex Prompt Templates

Frontend worker template:

```text
You are the frontend worker for Lab Tutor.

Own only files under frontend/.
Use these skills for this task: shadcn-ui, vercel-react-best-practices, karpathy-guidelines.

Follow AGENTS.md exactly:
- all imports use @/ for src/
- prefer feature api.ts files for endpoints; shared HTTP helpers may stay in src/services/
- forms use react-hook-form + zod
- styling uses TailwindCSS v4 + cn()
- run frontend tests and verification commands inside the `lab_tutor_frontend` container by default

Do not edit backend/ files.
You are not alone in the codebase. Do not revert others' changes. Adapt to existing edits if needed.
Return:
1. Files changed
2. User-visible behavior change
3. Any follow-up needed from backend
```

Backend worker template:

```text
You are the backend worker for Lab Tutor.

Own only files under backend/.
Use these skills for this task: fastapi, python-service-patterns, postgres-patterns, karpathy-guidelines.
Add neo4j-cypher and LangGraph skills only if the task touches graph or agent workflow code.

Follow AGENTS.md exactly:
- preserve or move toward onion architecture under app/modules/<feature>/
- keep queries in repository-style modules such as repository.py and neo4j_repository.py
- keep business logic in service.py
- routes depend on services via Depends()
- SQL is the source of truth; Neo4j is the projection
- run backend tests and verification commands inside the `lab_tutor_backend` container by default

Do not edit frontend/ files.
You are not alone in the codebase. Do not revert others' changes. Adapt to existing edits if needed.
Return:
1. Files changed
2. API or schema changes
3. Verification steps run
```

Coordinator template:

```text
You are the coordinator for Lab Tutor.

Own planning, task splitting, integration, verification, and final user communication.
Spawn a frontend worker for frontend/ changes and a backend worker for backend/ changes when the work is parallelizable.
Keep file ownership disjoint. Define any shared contract before parallel work begins.
Do final verification before wrapping up.
```

## Architecture Rules

### Backend — Target Architecture for New and Refactored Modules
```
modules/<feature>/
  models.py       # SQLAlchemy 2.0 entities
  schemas.py      # Pydantic v2 DTOs
  repository.py   # Preferred home for SQL queries
  service.py      # Business logic — depends on repository
  routes.py       # FastAPI router — depends on service
```
- For new and refactored modules, keep SQL access in repository-style files and business logic in the service layer
- Legacy modules may also include helper files such as `graph.py`, `neo4j_repository.py`, `prompts.py`, or orchestrators; preserve that structure unless the task is already refactoring the area
- Always use `Depends()` for injection — never instantiate services in routes
- SQL is source of truth; Neo4j is the graph projection
- Type hints: Python 3.10+ syntax (`str | None`, `list[str]`)

### Frontend — Feature-Based Structure
- All imports use `@/` alias for `src/`
- Prefer feature-specific API wrappers in `<feature>/api.ts`; shared HTTP client and cross-feature helpers may live in `src/services/`
- Do not inline ad hoc `fetch`/`axios` calls inside components
- Forms: `react-hook-form` + `zod` only
- State: `Context` for global, local `useState` for component state
- Styling: TailwindCSS v4 + `cn()` — no inline styles

### Cypher Queries
- No nested `OPTIONAL MATCH` — use `COLLECT` instead
- Always use `MERGE` for upserts (idempotency)
- Batch writes with `UNWIND` for performance
- Check Neo4j schema via MCP tool before writing queries

## Code Quality (enforced)

- No dead code — remove unused imports, variables, commented-out blocks
- No over-engineering — solve the current problem only
- DRY — extract shared logic; three duplications → refactor
- Flat over nested — early returns and guard clauses preferred
- Every line must earn its place
- No hardcoded secrets, API keys, or tokens anywhere

## Testing

- Backend: run inside Docker by default, not on the host machine
- Start containers if needed: `docker start lab_tutor_postgres lab_tutor_backend`
- Backend full test command:
  `docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v'`
- Backend targeted test command:
  `docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_example.py'`
- Frontend: run inside Docker by default, not on the host machine
- Start frontend container if needed: `docker start lab_tutor_frontend`
- Frontend default verification:
  `docker exec lab_tutor_frontend sh -lc 'cd /app && npm run lint && npm run build'`
- Frontend targeted Vitest command:
  `docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/example/example.test.tsx'`
- Also run frontend tests in Docker when you change logic covered by Vitest or add/update frontend tests
- Tests use the real test database — no mocked DB
- Run the relevant backend/frontend checks for the area you changed before pushing any commit

## Git Conventions

- Never commit directly to `main`
- Branch naming: `feat/<name>`, `fix/<name>`, `refactor/<area>`, `chore/<topic>`
- Commit messages: imperative, descriptive, searchable
- PRs require: scope, behavior changes, verification steps

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `LAB_TUTOR_DATABASE_URL` | Yes | PostgreSQL connection |
| `LAB_TUTOR_NEO4J_URI` | No | Neo4j connection |
| `LAB_TUTOR_NEO4J_USERNAME` | No | Neo4j auth |
| `LAB_TUTOR_NEO4J_PASSWORD` | No | Neo4j auth |
| `LAB_TUTOR_NEO4J_DATABASE` | No | Neo4j database name; defaults to `neo4j` |
| `LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING` | No | Azure Blob |
| `LAB_TUTOR_AZURE_CONTAINER_NAME` | No | Azure Blob container name; defaults to `class-presentations` |
