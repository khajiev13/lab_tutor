# Lab Tutor — Agent Rules (Cross-Tool)

> This file is read by Antigravity, Cursor, and Claude Code automatically.
> Antigravity-specific overrides live in GEMINI.md.

## Project Overview

Lab Tutor is a monorepo: React 19 frontend + FastAPI backend + Neo4j knowledge graph.
It hosts four AI agents (Curricular Alignment Architect, Market Demand Analyst,
Textual Resource Analyst, Video Agent) that form an end-to-end curriculum intelligence pipeline.

## Tech Stack

- **Frontend**: React 19, Vite, TypeScript (strict), TailwindCSS v4, Shadcn UI
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, LangGraph
- **Databases**: PostgreSQL (relational), Neo4j (knowledge graph), vector embeddings
- **Infra**: Azure Blob Storage, Docker, uv (Python), npm (JS)

## Architecture Rules

### Backend — Onion Architecture (non-negotiable)
```
modules/<feature>/
  models.py       # SQLAlchemy 2.0 entities
  schemas.py      # Pydantic v2 DTOs
  repository.py   # All DB queries — nowhere else
  service.py      # Business logic — depends on repository
  routes.py       # FastAPI router — depends on service
```
- Always use `Depends()` for injection — never instantiate services in routes
- SQL is source of truth; Neo4j is the graph projection
- Type hints: Python 3.10+ syntax (`str | None`, `list[str]`)

### Frontend — Feature-Based Structure
- All imports use `@/` alias for `src/`
- API calls only in `<feature>/api.ts` — never inline in components
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

- Backend: `LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v`
- Frontend: `npm run lint && npm run build`
- Tests use the real test database — no mocked DB
- Always run tests before pushing any commit

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
| `LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING` | No | Azure Blob |
