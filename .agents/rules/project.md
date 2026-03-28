---
trigger: always_on
---

# GitHub Copilot Instructions for Lab Tutor

## 🏗 Project Architecture
- **Monorepo Structure**:
  - `frontend/`: React 19 + Vite + TailwindCSS v4 + Shadcn UI (Always check mcp server for the most up to date components and styling conventions or check out the docs.)
  - `backend/`: FastAPI + SQLAlchemy + Pydantic v2 (Modular Onion Architecture)
  - `knowledge_graph_builder/`: Python scripts for Neo4j data ingestion
  - `neo4j_database/`: Neo4j Docker configuration
- **Databases**:
  - **Neo4j**: Stores the *graph view* for currently integrated features (Users, Courses, Enrollments).
  - **PostgreSQL**: Stores relational data (Auth, Courses, Enrollments) via SQLAlchemy. For integrated features, some writes are mirrored to Neo4j. This is running in the cloud but we have local postgresql for testing only.

###Agents
1. Curricular Alignment Architect. Discovers candidate textbooks from the web, evaluates them against the course objectives, and — after instructor approval — downloads and analyzes selected books at the chapter level, extracting the concrete skills each chapter can teach.
2. Market Demand Analyst: Collects real job postings, extracts the skills employers demand, and aligns each one against the curriculum skills identified by the first agent — classifying every market skill as already covered, partially covered, or entirely missing.
3. Textual Resource Analyst: Takes every identified skill — from both textbook analysis and market-demand analysis — and curates the best online learning materials (tutorials, documentation, articles) to teach each one.
4. Video Agent: Complements the Textual Resource Analyst by finding the best educational video content for each identified skill — searching platforms such as YouTube and online course providers, then ranking candidates on relevance, recency, pedagogical quality, and source authority.
Together, these agents form an end-to-end pipeline: textbook analysis builds the skill vocabulary → market analysis aligns it with industry reality → text and video resource curation finds the best way to teach each skill.



### Graph Schema
- Check neo4j mcp server about the graph schema and how to query it.


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
- **Testing**: `LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v` (requires a local PostgreSQL instance). Always run tests before pushing commits.
- **Linting/Formatting**: `uv run ruff check .` and `uv run ruff format .`
- **Database Migrations**: Uses `Base.metadata.create_all(bind=engine)` in `lifespan` (no Alembic yet).
- **Health Check**: `GET /health` returns overall status and per-dependency checks (`sql`, `neo4j`, `azure_blob`).

### Knowledge Graph (`/knowledge_graph_builder`)
- **Ingestion**: `python scripts/ingest_ready_data.py`
- **Dependencies**: Managed via `uv` (`pyproject.toml`) if there is a new dependency use `uv add <dependency>`. Do not hardcode the dependency in the script.

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
- **SQL**: `LAB_TUTOR_DATABASE_URL` (required, PostgreSQL URL)
- **Neo4j (optional, enables driver)**:
  - `LAB_TUTOR_NEO4J_URI`
  - `LAB_TUTOR_NEO4J_USERNAME`
  - `LAB_TUTOR_NEO4J_PASSWORD`
  - `LAB_TUTOR_NEO4J_DATABASE` (default: `neo4j`)
- **Azure Blob (optional)**:
  - `LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING`
  - `LAB_TUTOR_AZURE_CONTAINER_NAME` (default: `class-presentations`)


## 🧹 Code Quality Principles

- **Less code is better code.** Prefer concise, readable solutions over verbose ones.
- **Don't over-engineer.** Solve the current problem, not hypothetical future ones.
- **No dead code.** Remove unused imports, variables, functions, and commented-out blocks.
- **DRY (Don't Repeat Yourself).** Extract shared logic into reusable functions/components.
- **Single Responsibility.** Each function, class, or module should do one thing well.
- **Meaningful names.** Use clear, descriptive names so comments become unnecessary.
- **Follow established patterns.** Match the conventions already in the codebase before inventing new ones.
- **Avoid premature abstraction.** Duplicate twice before abstracting; three strikes and you refactor.
- **Flat over nested.** Prefer early returns and guard clauses to deeply nested conditionals.
- **Every line must earn its place.** If a line doesn't add clarity or functionality, delete it.
- **Tests are documentation.** Write tests that clearly demonstrate expected behavior and edge cases.
- **Cypher Queries.** Always follow the best practices and latest cypher, no nesting OPTIONAL MATCH and use COLLECT instead for example.


## Skills for AI Agents
- **You have a list of skills and always use the correct skill for the task. Think about which skill is most appropriate for the context.** When writing fastapi routes, use the `fastapi` skill. For React components, use the `react` skill.
