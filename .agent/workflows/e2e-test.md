---
description: End-to-end feature verification. Opens Chrome, exercises the UI, then checks browser console logs, backend/frontend container logs, Neo4j graph state, and Postgres records. Use after implementing a feature to confirm it works correctly across all layers.
---

# E2E Feature Test Workflow

Browser-driven testing with full-stack observability: UI → container logs → Neo4j → Postgres.

## Step 1 — Confirm services are running
// turbo
docker compose ps --format "table {{.Name}}\t{{.Status}}"
// capture: SERVICES_STATUS

> If any service is not running/healthy, abort and fix it before proceeding.

## Step 2 — Clear log buffers (fresh baseline)
// turbo
docker compose logs --tail=0 --follow backend frontend &
LOGS_PID=$!
echo "Log tailing started (PID: $LOGS_PID)"
// capture: LOGS_PID

## Step 3 — Browser agent: exercise the feature
Role: Browser Testing Specialist
Task: Open Chrome and test the feature end-to-end:

1. Navigate to `http://localhost:5173`
2. Follow the feature-specific test path provided in the task description
3. For each user action, capture:
   - What you clicked / typed / submitted
   - What the UI showed in response
   - Any visible error messages or loading states
4. Open the browser DevTools console and capture ALL console output:
   - Errors (red)
   - Warnings (yellow)
   - Info/log messages related to API calls or state changes
5. Open the Network tab and note:
   - Which API endpoints were called
   - HTTP status codes
   - Any failed requests (red)

Produce a structured report:
```
ACTIONS_TAKEN: [list of steps performed]
UI_RESULT: [what the user sees — success / error / unexpected]
CONSOLE_ERRORS: [all red console entries]
CONSOLE_LOGS: [relevant info/log entries]
API_CALLS: [endpoint → status code]
```
// capture: BROWSER_REPORT

## Step 4 — Collect container logs
// turbo
docker compose logs --tail=100 backend 2>&1
// capture: BACKEND_LOGS

// turbo
docker compose logs --tail=100 frontend 2>&1
// capture: FRONTEND_LOGS

## Step 5 — Verify Neo4j state (if feature writes to graph)
Role: Neo4j Verifier
Task: Given $BROWSER_REPORT (specifically ACTIONS_TAKEN and API_CALLS):
- Determine what Neo4j writes the feature should have produced
- Use the MCP Neo4j read tool to run Cypher queries verifying:
  - Expected nodes exist with correct properties
  - Expected relationships were created
  - No orphaned nodes or dangling relationships
- Compare actual graph state vs. expected state

Produce:
```
NEO4J_EXPECTED: [what should be in the graph]
NEO4J_ACTUAL: [what the Cypher queries returned]
NEO4J_VERDICT: PASS / FAIL / SKIP (if feature doesn't touch Neo4j)
```
// capture: NEO4J_REPORT

## Step 6 — Verify Postgres state (if feature writes to DB)
Role: Database Verifier
Task: Given $BROWSER_REPORT (specifically API_CALLS):
- Use the MCP Postgres tool to query relevant tables
- Verify that rows were created/updated/deleted as expected
- Check for any constraint violations in the backend logs
- Confirm data matches what the UI showed in $BROWSER_REPORT.UI_RESULT

Produce:
```
POSTGRES_EXPECTED: [what should be in the DB]
POSTGRES_ACTUAL: [query results]
POSTGRES_VERDICT: PASS / FAIL / SKIP
```
// capture: POSTGRES_REPORT

## Step 7 — Synthesize findings
Role: QA Lead
Task: Review all captured data:
- $BROWSER_REPORT — UI behaviour and console output
- $BACKEND_LOGS — FastAPI request logs, errors, slow requests
- $FRONTEND_LOGS — Vite dev server output
- $NEO4J_REPORT — graph state verification
- $POSTGRES_REPORT — relational DB state verification

Classify each finding:
- **BLOCKER** — feature is broken (wrong data, error shown, DB not updated)
- **WARNING** — unexpected console errors or slow requests but feature works
- **PASS** — everything behaves as expected

Final verdict:
```
OVERALL: PASS / FAIL / PARTIAL
BLOCKERS: [list]
WARNINGS: [list]
SUMMARY: [1-3 sentence human-readable result]
```

> If OVERALL is FAIL, describe the exact reproduction steps and the first error in the chain.
> If OVERALL is PASS, confirm which layers were verified and any caveats.
