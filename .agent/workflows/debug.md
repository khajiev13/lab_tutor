---
description: Debug a failing test, error, or unexpected behavior using competing hypotheses. Spawns multiple investigators in parallel to avoid anchoring on one root cause. Use when you have a bug you can't immediately explain.
---

# Parallel Debug Workflow

Multiple hypotheses investigated simultaneously. The one with evidence wins.

## Step 1 — Capture the failure
// turbo
cd backend && LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v 2>&1 | tail -50
// capture: ERROR_OUTPUT

## Step 2 — Spawn hypothesis investigators in parallel
// parallel

### Investigator A — Data Layer
Role: Database Debug Specialist
Task: Given $ERROR_OUTPUT, investigate if the root cause is in the data layer:
- Repository queries returning unexpected results
- SQLAlchemy session/transaction issues
- Neo4j query returning wrong data or no data
- Missing or stale embeddings
Produce: hypothesis + supporting evidence from code
// capture: HYPOTHESIS_A

### Investigator B — Business Logic
Role: Service Layer Debug Specialist
Task: Given $ERROR_OUTPUT, investigate if the root cause is in the service layer:
- Business logic edge cases
- Missing validation before DB write
- Incorrect transformation of data
- Race condition in parallel operations
Produce: hypothesis + supporting evidence from code
// capture: HYPOTHESIS_B

### Investigator C — Integration
Role: API/Schema Debug Specialist
Task: Given $ERROR_OUTPUT, investigate if the root cause is in the integration layer:
- Pydantic validation rejecting data
- Route returning wrong status code
- Missing dependency injection
- CORS or auth issue
Produce: hypothesis + supporting evidence from code
// capture: HYPOTHESIS_C

## Step 3 — Cross-examination
Role: Senior Debugger
Task: Review $HYPOTHESIS_A, $HYPOTHESIS_B, $HYPOTHESIS_C.
Each investigator must try to DISPROVE the other two hypotheses with evidence.
The hypothesis that survives cross-examination is the root cause.
Output: confirmed root cause + exact file/line + minimal fix

## Step 4 — Apply fix
Role: Backend Specialist
Task: Apply the minimal fix identified in Step 3.
No refactoring. No extra changes. Fix only the confirmed root cause.

## Step 5 — Verify
// turbo
cd backend && LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v
// retry: 1

> If still failing, repeat from Step 2 with the new error output.
