---
description: "Backend standards for FastAPI modules (onion architecture, typing, DI, SQLAlchemy, Pydantic)."
alwaysApply: false
globs:
  - "backend/**"
  - "knowledge_graph_builder/**"
---

# Backend Standards (FastAPI / Python) — migrated from Copilot instructions

## 🧱 Architecture (Modular Onion)

- **Group by feature** under `backend/app/modules/` (e.g., `auth`, `courses`).
- **Layers**:
  - **Domain**: `models.py` (SQLAlchemy entities) and `schemas.py` (Pydantic DTOs)
  - **Repository**: `repository.py` (data access). Encapsulate all DB queries here.
  - **Service**: `service.py` (business logic). Depends on Repository.
  - **API**: `routes.py` (controllers). Depends on Service.
- **Core & providers**:
  - `core/`: shared components (`database.py`, `settings.py`)
  - `providers/`: infrastructure services (e.g., `storage.py` for Azure Blob)
- **Routing**: register module routers in `main.py`.

## 🧩 Conventions

- **Type hints**: use modern syntax (`str | None`, `list[str]`).
- **ORM**: use SQLAlchemy 2.0 style (`Mapped`, `mapped_column`, `DeclarativeBase`).
- **Validation**: use Pydantic v2 models (`ConfigDict(from_attributes=True)` for ORM mode).
- **Dependency injection**:
  - Use `Depends()` to inject Services into Routes
  - Inject Repositories into Services (don’t query DB directly from routes)

## ✅ End-of-implementation checks (must match CI)

When you change anything under `backend/`, **do not finish** until these pass locally (same steps as `.github/workflows/backend.yml`):

- **Install deps (when `uv.lock` changes or deps feel stale)**: `uv sync --group dev`
- **Lint**: `uv run ruff check .`
- **Formatting check**: `uv run ruff format --check .`
- **Tests**: `uv run pytest -v`

Also:

- **Write/update tests** when behavior changes:
  - Add/extend **pytest** tests in `backend/tests/` (prefer covering the new/changed endpoints and service logic).
  - Cover happy path + at least one failure/edge case for new logic.


