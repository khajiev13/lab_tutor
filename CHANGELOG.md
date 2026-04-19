# Changelog

All notable changes to Lab Tutor are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — 2026-04-17

### Added

#### Backend

- **`backend/app/modules/cognitive_diagnosis/`** — New FastAPI module
  - `GET /diagnosis/arcd-twin/{course_id}` — ARCD twin snapshot for authenticated student
  - `GET /diagnosis/student-events/{course_id}` — List learning events
  - `POST /diagnosis/student-events/{course_id}` — Record a learning event
  - `POST /diagnosis/adaptive-exercise/{course_id}` — Generate adaptive exercise
  - `GET /diagnosis/interaction-stats/{course_id}` — Interaction summary
  - `POST /diagnosis/engagement-signal/{course_id}` — Log engagement signal
  - Pydantic v2 schemas: `StudentEventCreate`, `ExerciseRequest`, `PortfolioResponse`, …
  - Neo4j repository with `UPSERT_MASTERED`, `UPSERT_MASTERY_BATCH`, `CREATE_ATTEMPTED`,
    `UPSERT_ENGAGES_WITH_*`, `GET_STUDENT_TWIN`, `GET_SKILL_PREREQS`, `GET_SKILL_LIST`
  - Service layer: `CognitiveDiagnosisService`

- **`backend/app/modules/teacher_digital_twin/`** — New FastAPI module
  - `GET /teacher-twin/{course_id}/skill-difficulty`
  - `GET /teacher-twin/{course_id}/skill-popularity`
  - `GET /teacher-twin/{course_id}/class-mastery`
  - `GET /teacher-twin/{course_id}/student-groups`
  - `POST /teacher-twin/{course_id}/what-if`
  - `POST /teacher-twin/{course_id}/simulate-skill`
  - `POST /teacher-twin/{course_id}/simulate-skills`
  - `GET /teacher-twin/{course_id}/student/{student_id}/portfolio`
  - `GET /teacher-twin/{course_id}/student/{student_id}/twin`
  - Pydantic v2 schemas: `SkillDifficultyResponse`, `ClassMasteryResponse`,
    `WhatIfRequest/Response`, `MultiSkillSimulationRequest/Response`, …
  - Neo4j repository with 9 optimised read queries
  - Service layer: `TeacherDigitalTwinService` (K-means student clustering, what-if logic)

- **Neo4j Cypher refactor** — 9 queries across both repositories updated to follow
  project best practices:
  - Replaced nested `OPTIONAL MATCH` with list comprehensions (`[... | r.prop][0]`)
  - Replaced `WITH … COLLECT()` accumulations with `COLLECT {}` subqueries (Neo4j 5+)
  - `MERGE` for all upserts; `UNWIND` for batch writes

- **Backend tests** (`backend/tests/modules/`)
  - `cognitive_diagnosis/`: `test_schemas.py`, `test_repository.py`, `test_service.py`,
    `test_routes.py` — 60+ assertions
  - `teacher_digital_twin/`: `test_schemas.py`, `test_repository.py`, `test_service.py`,
    `test_routes.py` — 60+ assertions
  - All tests use `TestClient` + JWT fixtures + mocked Neo4j driver

#### Frontend

- **`src/features/arcd-agent/api/teacher-twin.ts`** — Typed `apiFetch` wrappers for
  all Teacher Digital Twin endpoints

- **New pages**
  - `TeacherTwinPage` — Teacher dashboard (skill difficulty, popularity, class mastery)
  - `ClassOverviewPage` — Class-wide mastery heatmap
  - `ClassRosterPage` — Paginated student list
  - `StudentDrilldownPage` — Per-student portfolio + twin viewer

- **Modified pages**
  - `StudentPage` — Updated for new `StudentPortfolio` type shape
  - `JourneyPage` — Updated for `timeline`/`summary` fields

- **New/updated components**
  - `chat-tab`, `pathgen-tab`, `journey-map-tab`, `twin-viewer-tab`, `schedule-tab`,
    `unified-tab` — Aligned to new `StudentPortfolio` type

- **New contexts**
  - `TeacherDataContext` — Teacher-side course/class data with polling
  - Updates to `TwinContext`, `DataContext` for new field shapes

- **Frontend tests** (`src/features/arcd-agent/`)
  - `api/teacher-twin.test.ts` — API wrapper tests
  - `context/context.test.tsx` — `TeacherDataContext`, `DataContext`, `TwinContext`
  - `pages/pages.test.tsx` — Smoke tests for all 6 pages
  - `components/tabs.test.tsx` — Smoke tests for all 6 tab components
  - `src/test/fetchMock.ts` — Lightweight `vi.stubGlobal` fetch helper

#### Documentation

- `docs/COGNITIVE_DIAGNOSIS_AND_TEACHER_TWIN.md` — Full module reference
  (endpoints, schemas, Neo4j graph schema, env vars, test commands)
- `README.md` — Updated Module Status table, API Routes table, Testing section,
  and Documentation table

### Changed

- `backend/main.py` — Registered `cognitive_diagnosis.router` and
  `teacher_digital_twin.router`
- `README.md` — Expanded Testing section with per-module test matrix
