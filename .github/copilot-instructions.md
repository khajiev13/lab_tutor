# GitHub Copilot Instructions for Lab Tutor

## 🏗 Project Architecture
- **Monorepo Structure**:
  - `frontend/`: React 19 + Vite + TailwindCSS v4 + Shadcn UI
  - `backend/`: FastAPI + SQLAlchemy + Pydantic v2 (Modular Onion Architecture)
  - `knowledge_graph_builder/`: Python scripts for Neo4j data ingestion
  - `neo4j_database/`: Neo4j Docker configuration
- **Databases**:
  - **Neo4j**: Stores the *graph view* for currently integrated features (Users, Courses, Enrollments).
  - **SQLite**: Stores relational data (Auth, Courses, Enrollments) via SQLAlchemy. For integrated features, writes are mirrored to Neo4j.

## 🧠 Neo4j (Current Integrated Scope)

### What’s Implemented (so far)
- **Auth → Neo4j**: on user register/update, a `(:USER {id})` node is upserted and role is represented via labels.
- **Courses → Neo4j**: on course create/update/delete and join/leave, a `(:CLASS {id})` node and relationships are created/removed.
- **Design rule**: keep `:USER` as the stable base label; role is expressed via additional labels.

### Graph Schema (current)
- **Nodes**:
  - `(:USER { id: int, first_name?: str, last_name?: str, email: str, created_at?: str })`
  - `(:CLASS { id: int, title: str, description?: str, created_at?: str, extraction_status?: str })`
- **Role Labels on `USER`** (derived; no `role` property stored):
  - `:STUDENT`
  - `:TEACHER`
- **Relationships**:
  - `(:USER)-[:TEACHES_CLASS]->(:CLASS)`
  - `(:USER)-[:ENROLLED_IN_CLASS]->(:CLASS)`

### Constraints / Indexes (created on backend startup when Neo4j is configured)
- `CONSTRAINT user_id_unique` on `(u:USER) REQUIRE u.id IS UNIQUE`
- `CONSTRAINT class_id_unique` on `(c:CLASS) REQUIRE c.id IS UNIQUE`
- `INDEX class_title_idx` on `(c:CLASS) ON (c.title)`

### Source of Truth
- For now: **SQL is still the system of record**, and Neo4j is a mirrored projection for graph queries and relationships.
- **Dual-write behavior** (Courses): SQL is written first, then Neo4j is updated; SQL is rolled back if the Neo4j write fails.

## 🚀 Development Workflows

### Frontend (`/frontend`)
- **Package Manager**: `npm`
- **Dev Server**: `npm run dev`
- **Build**: `npm run build` (TypeScript + Vite)
- **Linting**: `npm run lint` (ESLint Flat Config)
- **Styling**: TailwindCSS v4 with `cn()` utility for class merging.
- **Components**: Shadcn UI in `@/components/ui`. Use `npx shadcn@latest add [component]` to add new ones. Use mcp tool to list uptodate components and come up with the most beatiful way to do it.

### Backend (`/backend`)
- **Package Manager**: `uv` (Python 3.12+)
- **Run Server**: `uv run fastapi dev main.py`
- **Testing**: `uv run pytest`
- **Linting/Formatting**: `uv run ruff check .` and `uv run ruff format .`
- **Database Migrations**: Uses `Base.metadata.create_all(bind=engine)` in `lifespan` (no Alembic yet).
- **Health Check**: `GET /health` returns overall status and per-dependency checks (`sql`, `neo4j`, `azure_blob`).

### Knowledge Graph (`/knowledge_graph_builder`)
- **Ingestion**: `python scripts/ingest_ready_data.py`
- **Dependencies**: Managed via `uv` (`pyproject.toml`).

## 📝 Coding Conventions

### Frontend (React/TypeScript)
- **Imports**: Use `@/` alias for `src/` (e.g., `import { Button } from "@/components/ui/button"`).
- **Forms**: Use `react-hook-form` with `zod` resolvers.
- **State**: Use `Context` for global state (e.g., `AuthContext`).
- **API**: Use `axios` instances from `@/services/api`.
- **Strict Mode**: TypeScript `strict: true` is enabled. Handle `null`/`undefined` explicitly.

### Backend (Python/FastAPI)
- **Architecture**: Modular Onion Architecture. Group code by feature in `modules/` (e.g., `auth`, `courses`).
- **Layers**:
  - **Domain**: `models.py` (SQLAlchemy Entities) and `schemas.py` (Pydantic DTOs).
  - **Repository**: `repository.py` (Data Access). Encapsulate all DB queries here.
  - **Service**: `service.py` (Business Logic). Depends on Repository.
  - **API**: `routes.py` (Controllers). Depends on Service.
- **Core & Providers**:
  - `core/`: Shared components (`database.py`, `settings.py`).
  - `providers/`: Infrastructure services (e.g., `storage.py` for Azure Blob).
- **Type Hints**: Use modern Python 3.10+ syntax (`str | None`, `list[str]`).
- **ORM**: Use SQLAlchemy 2.0 style (`Mapped`, `mapped_column`, `DeclarativeBase`).
- **Validation**: Use Pydantic v2 models (`ConfigDict(from_attributes=True)` for ORM mode).
- **Dependency Injection**: Use `Depends()` to inject Services into Routes, and Repositories into Services.
- **Routing**: Register module routers in `main.py`.

## 🔗 Integration Points
- **CORS**: Backend is configured to allow `localhost:5173`, `localhost:5174`, and `localhost:3000`.
- **Auth**: JWT-based authentication. Frontend stores token; Backend validates via `OAuth2PasswordBearer`.
- **Docker**: Use `docker-compose up -d` to start Neo4j and Backend services together.

## 🌿 Git Workflow (Required)

### Branching
- Always work on a **feature-scoped branch** (never commit directly to `main`).
- Use a consistent branch naming scheme so the repo history is self-explanatory:
  - `feat/<feature-name>` (new feature)
  - `fix/<bug-name>` (bug fix)
  - `refactor/<area>` (refactor/no behavior change intended)
  - `chore/<topic>` (tooling, docs, dependency bumps)
- Keep branches focused: **one logical feature per branch**.

### Commits (AI-readable)
- Prefer **small, coherent commits** that match the feature scope.
- Commit messages must be descriptive and searchable:
  - Good: `Integrate Neo4j projection alongside SQL (dual-write) + health checks`
  - Avoid: `update`, `fix`, `wip`
- When a change impacts architecture or runtime behavior, include in the commit body:
  - **What changed** (files/modules)
  - **Why** (design reason)
  - **How to verify** (tests/commands)

### Pull Requests
- PR description must be detailed enough that a future developer (or AI agent) can reconstruct intent.
- Include:
  - **Scope**: what feature/module is affected
  - **Behavior changes**: endpoints, data model, migration notes
  - **Neo4j/SQL consistency**: dual-write/rollback behavior if relevant
  - **Config**: new env vars required/optional
  - **Verification**: tests run (`uv run pytest`, `npm test`, etc.)

## ⚙️ Runtime Configuration (Backend)

### Required / Optional Env Vars
- **SQL**: `LAB_TUTOR_DATABASE_URL` (defaults to `sqlite:///./data/app.db`)
- **Neo4j (optional, enables driver)**:
  - `LAB_TUTOR_NEO4J_URI`
  - `LAB_TUTOR_NEO4J_USERNAME`
  - `LAB_TUTOR_NEO4J_PASSWORD`
  - `LAB_TUTOR_NEO4J_DATABASE` (default: `neo4j`)
- **Azure Blob (optional)**:
  - `LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING`
  - `LAB_TUTOR_AZURE_CONTAINER_NAME` (default: `class-presentations`)

### Docker Volumes (persistence)
- SQLite data is persisted in the `backend_data` Docker volume (mounted to `/app/data`).
- Neo4j data is persisted in `neo4j_data` / `neo4j_logs` / `neo4j_import` / `neo4j_plugins`.
