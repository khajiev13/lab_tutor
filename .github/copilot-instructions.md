# GitHub Copilot Instructions for Lab Tutor

## 🏗 Project Architecture
- **Monorepo Structure**:
  - `frontend/`: React 19 + Vite + TailwindCSS v4 + Shadcn UI
  - `backend/`: FastAPI + SQLAlchemy + Pydantic v2 (Modular Onion Architecture)
  - `knowledge_graph_builder/`: Python scripts for Neo4j data ingestion
  - `neo4j_database/`: Neo4j Docker configuration
- **Databases**:
  - **Neo4j**: Stores the knowledge graph (Concepts, Topics, Relationships).
  - **SQLite**: Stores relational data (Users, Courses, Enrollments) via SQLAlchemy.

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
