---
description: Build a new full-stack feature end-to-end. Spawns backend and frontend specialists in parallel, then runs tests and ships. Use when adding a new route, UI page, or module that touches both layers.
---

# New Feature Workflow (Multi-Agent)

Parallel backend + frontend implementation with a final test-and-ship phase.

## Step 1 — Plan the feature
> Identify: which backend module, which frontend feature, which DB entities are involved.
> Output a task breakdown before spawning agents.

## Step 2 — Spawn specialists in parallel
// parallel

### Backend Agent
Role: FastAPI Backend Specialist
Task: Implement the backend side of the feature following Onion Architecture:
- models.py (SQLAlchemy 2.0 entities if needed)
- schemas.py (Pydantic v2 request/response DTOs)
- repository.py (all DB queries)
- service.py (business logic)
- routes.py (FastAPI router, register in main.py)
Use the `fastapi` skill. No mocked dependencies.
// capture: BACKEND_DONE

### Frontend Agent
Role: React Frontend Specialist
Task: Implement the frontend side of the feature:
- <feature>/api.ts (typed axios calls to new endpoints)
- Components using shadcn/ui (check MCP tool first)
- react-hook-form + zod for any forms
- @/ imports only, cn() for classes
Use the `shadcn-ui` skill.
// capture: FRONTEND_DONE

## Step 3 — Neo4j writes (if needed)
// if BACKEND_DONE includes graph writes
Role: Neo4j Specialist
Task: Write and validate all Cypher queries for this feature.
Use the `neo4j-cypher` skill. Check schema via MCP first. No nested OPTIONAL MATCH.
// retry: 2

## Step 4 — Run full test suite
// turbo
cd backend && LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v
// capture: TEST_RESULT

// turbo
cd frontend && npm run lint && npm run build

> If tests fail, spawn a fix agent targeting the specific failure before proceeding.

## Step 5 — Ship via github-push workflow
// run workflow: github-push
