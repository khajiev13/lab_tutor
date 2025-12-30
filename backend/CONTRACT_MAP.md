# Backend contract map (typing + Pydantic refactor tracker)

This file tracks where the backend currently violates (or partially follows) `/.cursor/rules/backend-standards/RULE.md` and what we are standardizing to.

## auth (`backend/app/modules/auth`)

- **API**: Delegates to `fastapi-users` routers; already uses Pydantic models in `schemas.py`.
- **Service**: N/A (auth handled by `fastapi-users`).
- **Neo4j repo**: `UserGraphRepository` exists but has untyped `session` and untyped tx functions.
- **Contract leaks to fix**:
  - `dependencies.py`: missing return types for DI helpers; `on_after_update(..., update_dict: dict, ...)` uses a raw dict.
  - `neo4j_repository.py`: `session` is `object`-ish; needs a typed Neo4j session protocol/type.

## courses (`backend/app/modules/courses`)

- **API**: Mostly uses `response_model=...` already.
- **Service**: `CourseService` returns ORM models (FastAPI serializes via `from_attributes`).
- **Repositories**: `CourseRepository` returns ORM models; `CourseGraphRepository` uses Neo4j.
- **Contract leaks to fix**:
  - `routes.py`: two endpoints return raw dicts without `response_model`:
    - `upload_presentations` returns `{"uploaded_files": ...}`
    - `start_extraction` returns `{"message": ..., "status": ...}`
  - `service.py`: untyped attributes (`self.repo`, `self.graph_repo`, etc.) and untyped callables (`_run_graph(fn, ...)`).
  - `repository.py`: `processed_at` parameter is untyped and should be `datetime | None`.
  - `neo4j_repository.py`: untyped `session` and tx functions.
  - `file_processing.py`: internal DTO uses `@dataclass` (`FileDispatchResult`) — will be a Pydantic model.

## document_extraction (`backend/app/modules/document_extraction`)

- **Service**: `DocumentExtractionService` orchestrates extraction + graph insert.
- **Neo4j repo**: `DocumentExtractionGraphRepository` accepts `mentions: list[MentionInput]`.
- **Contract leaks to fix**:
  - `neo4j_repository.py`: `MentionInput` is a `TypedDict` and is populated as raw dicts; will become a Pydantic model and converted via `.model_dump()`.
  - `service.py`: untyped `neo4j_session` and untyped service attributes; helper `_build_mentions` takes untyped `concepts`.
  - `schemas.py`: `errors: list[dict[str, Any]]` will become a typed Pydantic error model list.
  - `llm_extractor.py`: `raw: Any` can be narrowed (keep minimal where LangChain forces it).

## providers (`backend/app/providers`)

- **Contract leaks to fix**:
  - `storage.py`: `get_blob_info(...) -> dict` should return a Pydantic model.

## app root (`backend/main.py`)

- **Contract leaks to fix**:
  - `/` and `/health` currently return raw dicts; we will add Pydantic response models and return model instances.











