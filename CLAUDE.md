# Lab Tutor — Claude Code Project Instructions

## Project Architecture
- **Monorepo Structure**:
  - `frontend/`: React 19 + Vite + TailwindCSS v4 + Shadcn UI
  - `backend/`: FastAPI + SQLAlchemy + Pydantic v2 (Modular Onion Architecture)
  - `knowledge_graph_builder/`: Python scripts for Neo4j data ingestion
  - `neo4j_database/`: Neo4j Docker configuration
- **Databases**:
  - **Neo4j**: Graph view for integrated features (Users, Courses, Enrollments). Check neo4j MCP server for schema.
  - **PostgreSQL**: Relational data (Auth, Courses, Enrollments) via SQLAlchemy. Cloud instance + local for testing.

## Development Workflows

### Frontend (`/frontend`)
- Package Manager: `npm`
- Dev Server: `npm run dev`
- Build: `npm run build`
- Linting: `npm run lint` (ESLint Flat Config)
- Styling: TailwindCSS v4 with `cn()` utility
- Components: Shadcn UI in `@/components/ui`. Use `npx shadcn@latest add [component]`. Use shadcn MCP tool for up-to-date components.

### Backend (`/backend`)
- Package Manager: `uv` (Python 3.12+)
- Run Server: `uv run fastapi dev main.py`
- Testing: `LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v`
- Linting/Formatting: `uv run ruff check .` and `uv run ruff format .`
- Database Migrations: `Base.metadata.create_all(bind=engine)` in `lifespan` (no Alembic yet)
- Health Check: `GET /health`

### Knowledge Graph (`/knowledge_graph_builder`)
- Ingestion: `python scripts/ingest_ready_data.py`
- Dependencies: `uv add <dependency>` — do not hardcode

## Coding Conventions

### Frontend (React/TypeScript)
- Imports: `@/` alias for `src/`
- Forms: `react-hook-form` with `zod` resolvers
- State: `Context` for global state (e.g., `AuthContext`)
- API: `axios` instances from `@/services/api`
- TypeScript `strict: true` — handle `null`/`undefined` explicitly

### Backend (Python/FastAPI)
- Modular Onion Architecture. Group by feature in `modules/`
- Layers: Domain (`models.py`, `schemas.py`) → Repository (`repository.py`) → Service (`service.py`) → API (`routes.py`)
- Core & Providers: `core/` for shared components, `providers/` for infrastructure
- Type hints: Python 3.10+ syntax (`str | None`, `list[str]`)
- ORM: SQLAlchemy 2.0 style (`Mapped`, `mapped_column`, `DeclarativeBase`)
- Validation: Pydantic v2 (`ConfigDict(from_attributes=True)`)
- Dependency Injection: `Depends()` to inject Services into Routes, Repos into Services

## Integration Points
- CORS: Backend allows `localhost:5173`, `localhost:5174`, `localhost:3000`
- Auth: JWT-based. Frontend stores token; Backend validates via `OAuth2PasswordBearer`
- Docker: `docker-compose up -d` for Neo4j and Backend

## Git Workflow
- Always work on feature-scoped branches (never commit directly to `main`)
- Branch naming: `feat/<name>`, `fix/<name>`, `refactor/<area>`, `chore/<topic>`
- Small, coherent commits with descriptive messages
- PR descriptions must include scope, behavior changes, config, and verification steps

## Runtime Configuration (Backend)
- SQL: `LAB_TUTOR_DATABASE_URL` (required)
- Neo4j (optional): `LAB_TUTOR_NEO4J_URI`, `LAB_TUTOR_NEO4J_USERNAME`, `LAB_TUTOR_NEO4J_PASSWORD`, `LAB_TUTOR_NEO4J_DATABASE`
- Azure Blob (optional): `LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING`, `LAB_TUTOR_AZURE_CONTAINER_NAME`

## Code Quality
- Less code is better code
- Don't over-engineer — solve the current problem
- No dead code — remove unused imports, variables, functions
- DRY — extract shared logic
- Single Responsibility
- Meaningful names
- Follow established patterns in the codebase
- Flat over nested — prefer early returns and guard clauses
- Every line must earn its place

## Custom Slash Commands
Use `/project:fastapi`, `/project:shadcn-ui`, `/project:react-best-practices`, `/project:composition-patterns`, `/project:langgraph-docs`, `/project:alipos-api`, `/project:pdf` for skill-specific guidance. Plan commands available for implementation plans.
