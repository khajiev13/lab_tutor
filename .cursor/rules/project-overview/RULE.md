---
description: "High-level context for the Lab Tutor monorepo (architecture, databases, dev workflows, runtime config)."
alwaysApply: true
---

# Lab Tutor — Project Overview (migrated from Copilot instructions)

## 🏗 Project Architecture

- **Monorepo structure**:
  - `frontend/`: React 19 + Vite + TailwindCSS v4 + shadcn/ui
  - `backend/`: FastAPI + SQLAlchemy + Pydantic v2 (**Modular Onion Architecture**)
  - `knowledge_graph_builder/`: Python scripts for Neo4j data ingestion
  - `neo4j_database/`: Neo4j Docker configuration
- **Databases**:
  - **Neo4j**: stores the graph view for currently integrated features (Users, Courses, Enrollments)
  - **SQLite**: stores relational data (Auth, Courses, Enrollments) via SQLAlchemy  
    For integrated features, writes are mirrored to Neo4j.

## 🚀 Development Workflows

### Frontend (`/frontend`)

- **Package manager**: `npm`
- **Dev server**: `npm run dev`
- **Build**: `npm run build` (TypeScript + Vite)
- **Linting**: `npm run lint` (ESLint Flat Config)
- **Styling**: TailwindCSS v4 with `cn()` utility for class merging
- **Components**: shadcn/ui in `@/components/ui`
  - Add components with `npx shadcn@latest add [component]`

### Backend (`/backend`)

- **Package manager**: `uv` (Python 3.12+)
- **Run server**: `uv run fastapi dev main.py`
- **Testing**: `uv run pytest`
- **Linting/formatting**: `uv run ruff check .` and `uv run ruff format .`
- **DB migrations**: uses `Base.metadata.create_all(bind=engine)` in `lifespan` (no Alembic yet)
- **Health check**: `GET /health` returns overall status and per-dependency checks (`sql`, `neo4j`, `azure_blob`)

### Knowledge Graph (`/knowledge_graph_builder`)

- **Ingestion**: `python scripts/ingest_ready_data.py`
- **Dependencies**: managed via `uv` (`pyproject.toml`)

## 🔗 Integration Points

- **CORS**: backend allows `localhost:5173`, `localhost:5174`, and `localhost:3000`
- **Auth**: JWT-based authentication
  - Frontend stores token
  - Backend validates via `OAuth2PasswordBearer`
- **Docker**: use `docker-compose up -d` to start Neo4j and backend services together

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

- SQLite data is persisted in the `backend_data` Docker volume (mounted to `/app/data`)
- Neo4j data is persisted in `neo4j_data` / `neo4j_logs` / `neo4j_import` / `neo4j_plugins`


