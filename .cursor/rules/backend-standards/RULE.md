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

- **Python 3 best practices (required)**:
  - Prefer idiomatic, modern Python 3 (readable, explicit, small functions, clear naming).
  - Avoid dynamic/implicit types when a precise type is known.
- **Type hints (required)**: add type annotations everywhere (functions, methods, class attributes), using modern syntax (`str | None`, `list[str]`).
- **ORM**: use SQLAlchemy 2.0 style (`Mapped`, `mapped_column`, `DeclarativeBase`).
- **Pydantic everywhere (required)**:
  - Use **Pydantic v2 models** for validation and data transport across layers (DTOs), not bare `dict`/`Any`.
  - **API boundaries** must use Pydantic models: request bodies, responses, and error payloads.
  - **Internal data contracts** should be Pydantic models too (e.g., service inputs/outputs), unless a domain entity is used directly.
  - For ORM mode use `ConfigDict(from_attributes=True)`.
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


