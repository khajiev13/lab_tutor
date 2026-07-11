# Neo4j Cypher Query Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every static individual-learning repository query valid Cypher 25 and restore production profile approval through the CV-skill projection stage.

**Architecture:** Keep query ownership in `neo4j_repository.py` and preserve all service and API contracts. Add parser-oriented regression assertions to the existing repository test module, make the minimal clause-boundary correction, then validate every static query with read-only `EXPLAIN` against the configured Aura instance.

**Tech Stack:** Python 3.12, Neo4j Python driver, Neo4j Aura 2025.x, Cypher 25, pytest, Ruff, Docker.

## Global Constraints

- Inspect the live schema before query validation.
- Prefix every top-level query with `CYPHER 25`.
- Use parameterized Cypher only.
- Run `EXPLAIN` before any write validation; do not execute graph writes during the audit.
- Preserve current labels, relationship directions, parameters, return values, and FastAPI behavior.
- Run backend tests and Ruff inside Docker.

---

### Task 1: Add parser-oriented regression tests

**Files:**
- Modify: `backend/tests/modules/individual_learning/test_neo4j_repository.py`

**Interfaces:**
- Consumes: static Cypher strings passed to `.run(...)` in `app.modules.individual_learning.neo4j_repository`.
- Produces: `_static_cypher_queries() -> list[str]` test helper and two regression tests enforcing the Cypher 25 prefix and the required `WITH u` clause boundary.

- [ ] **Step 1: Add the test helper and failing tests**

```python
import ast
import inspect

from app.modules.individual_learning import neo4j_repository


def _static_cypher_queries() -> list[str]:
    tree = ast.parse(inspect.getsource(neo4j_repository))
    return [
        call.args[0].value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "run"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    ]


def test_all_static_queries_declare_cypher_25() -> None:
    queries = _static_cypher_queries()

    assert queries
    assert all(query.lstrip().startswith("CYPHER 25") for query in queries)


def test_cv_skill_projection_scopes_user_before_optional_match() -> None:
    query = next(
        query
        for query in _static_cypher_queries()
        if "MERGE (u:USER" in query and "CV_SKILL" in query
    )

    normalized = " ".join(query.split())
    assert "SET u:INDIVIDUAL WITH u OPTIONAL MATCH" in normalized
```

- [ ] **Step 2: Run the two tests and verify RED**

Run:

```bash
docker run --rm --entrypoint sh \
  -v "$PWD:/workspace" \
  -e LAB_TUTOR_DATABASE_URL='postgresql://labtutor:labtutor@host.docker.internal:5433/lab_tutor_test' \
  individual-learning-full-loop-backend:latest \
  -lc 'cd /workspace/backend && /app/.venv/bin/python -m pytest -v \
    tests/modules/individual_learning/test_neo4j_repository.py::test_all_static_queries_declare_cypher_25 \
    tests/modules/individual_learning/test_neo4j_repository.py::test_cv_skill_projection_scopes_user_before_optional_match'
```

Expected: both tests fail because existing queries lack `CYPHER 25` and the CV-skill query lacks `WITH u`.

---

### Task 2: Apply the minimal Cypher correction

**Files:**
- Modify: `backend/app/modules/individual_learning/neo4j_repository.py`
- Test: `backend/tests/modules/individual_learning/test_neo4j_repository.py`

**Interfaces:**
- Consumes: the existing repository functions and their current parameters.
- Produces: the same function signatures and return values with Cypher 25-compatible query strings.

- [ ] **Step 1: Prefix every static top-level query**

Add `CYPHER 25` as the first non-whitespace token in every constant query passed to `.run(...)`:

```python
result = session.run(
    """
    CYPHER 25
    ...
    """,
    ...,
)
```

- [ ] **Step 2: Carry the user variable across the write/read boundary**

Change only the failing clause transition:

```cypher
CYPHER 25
MERGE (u:USER {id: $user_id})
SET u:INDIVIDUAL
WITH u
OPTIONAL MATCH (u)-[stale:HAS_SKILL]->(existing:SKILL:CV_SKILL)
```

- [ ] **Step 3: Run the focused tests and verify GREEN**

Run the exact Docker command from Task 1 Step 2.

Expected: both tests pass.

- [ ] **Step 4: Run the complete repository test module**

Run:

```bash
docker run --rm --entrypoint sh \
  -v "$PWD:/workspace" \
  -e LAB_TUTOR_DATABASE_URL='postgresql://labtutor:labtutor@host.docker.internal:5433/lab_tutor_test' \
  individual-learning-full-loop-backend:latest \
  -lc 'cd /workspace/backend && /app/.venv/bin/python -m pytest -v \
    tests/modules/individual_learning/test_neo4j_repository.py'
```

Expected: 13 tests pass.

- [ ] **Step 5: Commit the tested code change**

```bash
git add backend/app/modules/individual_learning/neo4j_repository.py \
  backend/tests/modules/individual_learning/test_neo4j_repository.py
git commit -m "Fix individual learning Cypher queries"
```

---

### Task 3: Validate against Aura and complete backend checks

**Files:**
- Verify: `backend/app/modules/individual_learning/neo4j_repository.py`
- Verify: `backend/tests/modules/individual_learning/test_profile_review.py`
- Verify: `backend/tests/modules/individual_learning/test_job_workflow.py`

**Interfaces:**
- Consumes: credentials from `/Users/khajievroma/Downloads/Neo4j-2682a33f-Created-2026-07-11.txt` without printing the password.
- Produces: read-only schema evidence and successful `EXPLAIN` plans for every static repository query.

- [ ] **Step 1: Inspect the live schema**

Run parameterized driver queries against database `2682a33f`:

```cypher
CYPHER 25
SHOW INDEXES YIELD name, type, labelsOrTypes, properties, state
WHERE state = 'ONLINE'
RETURN name, type, labelsOrTypes, properties, state
```

```cypher
CYPHER 25
SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties
```

Expected: `user_id_unique` exists on `USER.id`; all reported indexes are online.

- [ ] **Step 2: Run read-only `EXPLAIN` for every static query**

Use Python AST extraction to obtain each constant `.run(...)` query, provide representative parameters based on its `$parameter` names, and call the Neo4j driver with `EXPLAIN` inserted after the `CYPHER 25` prefix.

Expected: every query plans successfully; no syntax errors, `AllNodesScan`, or `CartesianProduct` operators are reported.

- [ ] **Step 3: Run workflow regression tests**

Run:

```bash
docker run --rm --entrypoint sh \
  -v "$PWD:/workspace" \
  -e LAB_TUTOR_DATABASE_URL='postgresql://labtutor:labtutor@host.docker.internal:5433/lab_tutor_test' \
  individual-learning-full-loop-backend:latest \
  -lc 'cd /workspace/backend && /app/.venv/bin/python -m pytest -v \
    tests/modules/individual_learning/test_profile_review.py \
    tests/modules/individual_learning/test_job_workflow.py'
```

Expected: all selected workflow tests pass.

- [ ] **Step 4: Run Ruff and formatting checks**

Run:

```bash
docker run --rm --entrypoint sh \
  -v "$PWD:/workspace" \
  individual-learning-full-loop-backend:latest \
  -lc 'cd /workspace/backend && /app/.venv/bin/ruff check \
    app/modules/individual_learning/neo4j_repository.py \
    tests/modules/individual_learning/test_neo4j_repository.py && \
    /app/.venv/bin/ruff format --check \
    app/modules/individual_learning/neo4j_repository.py \
    tests/modules/individual_learning/test_neo4j_repository.py'
```

Expected: both Ruff commands exit successfully with no changes required.

- [ ] **Step 5: Confirm repository cleanliness**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only the committed design, plan, production code, and test changes are present.
