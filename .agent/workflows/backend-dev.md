---
description: Build or modify a FastAPI backend feature following Onion Architecture. Use for new routes, services, repositories, schemas, or models. Spawns a Neo4j agent alongside if the feature touches the graph.
---

# Backend Development Workflow

## Step 1 — Read existing structure
// parallel

### Module Reader
Task: Read the target module directory and summarize existing layers:
models.py, schemas.py, repository.py, service.py, routes.py.
Note any patterns to follow.
// capture: EXISTING_STRUCTURE

### Schema Reader
Task: Check core/settings.py for available config and providers/.
Also check main.py to see how routers are registered.
// capture: CORE_CONTEXT

## Step 2 — Plan
> Using $EXISTING_STRUCTURE and $CORE_CONTEXT, outline:
> - Which layer(s) need changes
> - New SQLAlchemy models needed (if any)
> - New Pydantic schemas (request + response)
> - Repository methods
> - Service logic
> - Route endpoints (method, path, status codes)
> WAIT FOR APPROVAL before implementing.

## Step 3 — Implement
Role: FastAPI Backend Specialist
Use the `fastapi` skill.

Follow strictly:
- SQLAlchemy 2.0: Mapped[T], mapped_column()
- Pydantic v2: ConfigDict(from_attributes=True)
- Depends() everywhere — never instantiate services in routes
- Guard clauses, early returns
- Raise HTTPException with meaningful status codes
- Register new router in main.py

// if feature writes to Neo4j
// parallel

### Backend Implementation Agent
Implement the SQL-side of the feature (models → schemas → repo → service → routes).
// capture: BACKEND_DONE

### Neo4j Agent
Run the `neo4j-cypher` workflow for all graph writes this feature needs.
// capture: NEO4J_DONE

## Step 4 — Lint and test
// turbo
cd backend && uv run ruff format . && uv run ruff check --fix .

cd backend && LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v
// retry: 1
// capture: TEST_RESULT

> If tests fail, fix before proceeding. Do not push broken code.

## Step 5 — Ship (optional)
// if TEST_RESULT is green and user wants to push
// run workflow: github-push
