# Cognitive Diagnosis & Teacher Digital Twin

Two complementary modules that give students real-time adaptive learning feedback
and give teachers class-level analytics and what-if simulation tools.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Cognitive Diagnosis (`/diagnosis`)](#cognitive-diagnosis)
   - [Endpoints](#cognitive-diagnosis-endpoints)
   - [Key Schemas](#cognitive-diagnosis-schemas)
3. [Teacher Digital Twin (`/teacher-twin`)](#teacher-digital-twin)
   - [Endpoints](#teacher-digital-twin-endpoints)
   - [Key Schemas](#teacher-digital-twin-schemas)
4. [Neo4j Graph Schema](#neo4j-graph-schema)
5. [Environment Variables](#environment-variables)
6. [Running Tests](#running-tests)

---

## Architecture Overview

```
FastAPI Router  →  Service (business logic)  →  Repository (Cypher queries)  →  Neo4j
                                            ↘  PostgreSQL (user / course data)
```

Both modules follow the Modular Onion Architecture:

```
modules/<feature>/
  models.py       — SQLAlchemy 2.0 entities (if any)
  schemas.py      — Pydantic v2 request/response DTOs
  repository.py   — Neo4j Cypher queries (LiteralString constants)
  service.py      — Business logic
  routes.py       — FastAPI router (JWT + role enforcement)
```

---

## Cognitive Diagnosis

Provides per-student ARCD twin data: skill mastery snapshots, learning events,
adaptive exercises, and interaction logging.

**Auth**: All endpoints require a valid `STUDENT` JWT (`Bearer <token>`).

### Cognitive Diagnosis Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/diagnosis/arcd-twin/{course_id}` | Full ARCD twin snapshot for the authenticated student |
| `GET` | `/diagnosis/student-events/{course_id}` | List the student's recent learning events |
| `POST` | `/diagnosis/student-events/{course_id}` | Record a new learning event |
| `POST` | `/diagnosis/adaptive-exercise/{course_id}` | Generate an adaptive exercise |
| `GET` | `/diagnosis/interaction-stats/{course_id}` | Interaction/engagement summary |
| `POST` | `/diagnosis/engagement-signal/{course_id}` | Log an engagement signal (click, read, watch) |

> **Note**: The docstring in `routes.py` lists legacy path drafts. The live routes
> above reflect the actual registered paths.

### Cognitive Diagnosis Schemas

**Request**

| Schema | Fields |
|--------|--------|
| `StudentEventCreate` | `event_type`, `skill_name`, `score`, `time_spent_sec` |
| `ExerciseRequest` | `skill_name`, `difficulty` (optional) |
| `LogInteractionRequest` | `question_id`, `is_correct`, `time_spent_sec` |
| `LogEngagementRequest` | `resource_id`, `resource_type`, `progress`, `duration_sec` |

**Response**

| Schema | Fields |
|--------|--------|
| `LearningPathDiagnosisResponse` | `user_id`, `course_id`, `skills` (mastery list) |
| `StudentEventResponse` | `id`, `user_id`, `course_id`, `event_type`, `created_at`, … |
| `StudentEventsListResponse` | `events: list[StudentEventResponse]` |
| `ExerciseResponse` | `question`, `skill_name`, `difficulty`, `hint` |
| `PortfolioResponse` | `user_id`, `course_id`, `skills`, `mastered_count`, `struggling_count`, … |

---

## Teacher Digital Twin

Gives teachers class-level mastery analytics, student grouping, and what-if
simulation tools.

**Auth**: All endpoints require a valid `TEACHER` JWT (`Bearer <token>`).

### Teacher Digital Twin Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/teacher-twin/{course_id}/skill-difficulty` | Perceived difficulty per skill (avg mastery inversion) |
| `GET` | `/teacher-twin/{course_id}/skill-popularity` | How many students selected each skill |
| `GET` | `/teacher-twin/{course_id}/class-mastery` | Per-student mastery overview |
| `GET` | `/teacher-twin/{course_id}/student-groups` | K-means clustering of students by mastery profile |
| `POST` | `/teacher-twin/{course_id}/what-if` | What-if: simulate boosting a skill for all students |
| `POST` | `/teacher-twin/{course_id}/simulate-skill` | Simulate a single-skill intervention |
| `POST` | `/teacher-twin/{course_id}/simulate-skills` | Simulate multi-skill intervention |
| `GET` | `/teacher-twin/{course_id}/student/{student_id}/portfolio` | Individual student's learning portfolio |
| `GET` | `/teacher-twin/{course_id}/student/{student_id}/twin` | Individual student's full digital twin |

### Teacher Digital Twin Schemas

**Request**

| Schema | Fields |
|--------|--------|
| `WhatIfRequest` | `skill_name`, `boost_amount` (0–1) |
| `SkillSimulationRequest` | `skill_name`, `target_mastery` |
| `MultiSkillSimulationRequest` | `skills: list[SkillSimulationRequest]` |

**Response**

| Schema | Fields |
|--------|--------|
| `SkillDifficultyResponse` | `skills: list[{skill_name, student_count, avg_mastery, perceived_difficulty}]` |
| `SkillPopularityResponse` | `skills: list[{skill_name, selection_count, percentage}]`, `total_students` |
| `ClassMasteryResponse` | `students: list[StudentMasteryRow]`, `course_id` |
| `StudentGroupsResponse` | `groups: list[StudentGroup]`, `n_groups` |
| `WhatIfResponse` | `original`, `simulated`, `delta`, `skill_name` |
| `SkillSimulationResponse` | `mode`, `skill_name`, `affected_students`, `avg_delta` |
| `MultiSkillSimulationResponse` | `mode`, `skill_results: list[...]` |

---

## Neo4j Graph Schema

### Nodes

| Label | Key Properties | Description |
|-------|---------------|-------------|
| `USER:STUDENT` | `id` (int) | Enrolled student |
| `USER:TEACHER` | `id` (int) | Course teacher |
| `SKILL` / `BOOK_SKILL` / `MARKET_SKILL` | `name` (str) | Skill nodes |
| `CLASS` | `id` (int) | A course/class |
| `QUESTION` | `id` (str/int) | Adaptive exercise question |
| `READING_RESOURCE` | `id` | Reading material |
| `VIDEO_RESOURCE` | `id` | Video material |

### Relationships

| Relationship | From → To | Key Properties |
|-------------|-----------|----------------|
| `ENROLLED_IN_CLASS` | `USER:STUDENT` → `CLASS` | — |
| `SELECTED_SKILL` | `USER:STUDENT` → `SKILL/*` | — |
| `MASTERED` | `USER:STUDENT` → `SKILL/*` | `mastery` (0–1), `status`, `decay`, `attempt_count`, `correct_count`, `updated_at_ts` |
| `ATTEMPTED` | `USER:STUDENT` → `QUESTION` | `is_correct`, `timestamp_sec`, `attempt_number`, `time_spent_sec` |
| `ENGAGES_WITH` | `USER:STUDENT` → `READING_RESOURCE\|VIDEO_RESOURCE` | `progress`, `duration_sec`, `event_type`, `started_at` |
| `PREREQUISITE_OF` | `SKILL` → `SKILL` | `weight` |

### Cypher Best Practices Applied

All Cypher in both repositories follows the project's `neo4j-cypher` skill:

- **No nested `OPTIONAL MATCH`** — replaced with list comprehensions:
  `[(u)-[r:MASTERED]->(s) | r.mastery][0]`
- **`COLLECT {}` subqueries** for collecting related nodes without a `WITH` explosion
- **`MERGE` for upserts** to ensure idempotency
- **`UNWIND`** for batch writes
- **`ORDER BY` before aggregation** where deterministic ordering is needed

---

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `LAB_TUTOR_DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `LAB_TUTOR_NEO4J_URI` | Yes (for these modules) | — | `bolt://` or `neo4j://` URI |
| `LAB_TUTOR_NEO4J_USERNAME` | Yes (for these modules) | — | Neo4j username |
| `LAB_TUTOR_NEO4J_PASSWORD` | Yes (for these modules) | — | Neo4j password |
| `LAB_TUTOR_NEO4J_DATABASE` | No | `neo4j` | Neo4j database name |

> Both modules will respond with **503 Service Unavailable** if Neo4j is not
> configured at startup.

---

## Running Tests

```bash
# 1. Ensure the test database exists
docker exec lab_tutor_postgres psql -U labtutor -c 'CREATE DATABASE lab_tutor_test;'

# 2. Run only these two modules
LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@localhost:5433/lab_tutor_test" \
  uv run pytest -v \
    tests/modules/cognitive_diagnosis \
    tests/modules/teacher_digital_twin

# 3. Full suite
LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@localhost:5433/lab_tutor_test" \
  uv run pytest -v
```

### Test Structure

```
backend/tests/modules/
├── cognitive_diagnosis/
│   ├── test_schemas.py      # Pydantic DTO round-trips
│   ├── test_repository.py   # Cypher constant + session.run() verification
│   ├── test_service.py      # Business-logic unit tests (mock Neo4j driver)
│   └── test_routes.py       # HTTP integration tests (TestClient + JWT + mock Neo4j)
└── teacher_digital_twin/
    ├── test_schemas.py
    ├── test_repository.py
    ├── test_service.py
    └── test_routes.py
```

Neo4j is **mocked** in all tests using `app.dependency_overrides[get_neo4j_driver]`
with a `MagicMock` that simulates `session.run()` returning an iterable result
with `.single()` and `.consume()` support. PostgreSQL uses the real `lab_tutor_test`
database via the `db_session` fixture in `conftest.py`.
