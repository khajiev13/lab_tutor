---
trigger: always_on
---

# Lab Tutor — Supplementary Agent Rules

## Agent Spawning Guidelines (Unlimited Plan)

When a task clearly spans multiple domains, always prefer parallel agents over sequential:

| Task type | Recommended team |
|---|---|
| Full-stack feature | backend-specialist + frontend-specialist (parallel) |
| Code review before PR | security + architecture + performance + tests (parallel) |
| Bug with unknown cause | 3 hypothesis investigators (parallel) + cross-examiner |
| AI agent development | schema-reader + codebase-reader (parallel) → implementer |
| Push to GitHub | test-runner → lint-checker (parallel) → git-agent |

Never spawn more agents than there are independent workstreams.
5-6 tasks per agent is the sweet spot. More tasks = more context switching = worse output.

## File Ownership (avoid conflicts)

When multiple agents work in parallel, assign exclusive file ownership:
- Backend agent: `backend/app/modules/<feature>/`
- Frontend agent: `frontend/src/features/<feature>/`
- Neo4j agent: `knowledge_graph_builder/scripts/`
- Test agent: `backend/tests/`

No two agents should edit the same file simultaneously.

## Quality Gate (enforced before any git push)

All of these must be green:
```
backend: uv run ruff check .          → 0 errors
backend: uv run pytest -v             → all pass
frontend: npm run lint                → 0 errors
frontend: npm run build               → success
```

If any gate fails, stop. Fix. Re-run the gate. Never push broken code.

## LangSmith Tracing

All LangGraph agent runs should be traceable. Ensure:
- `LANGCHAIN_TRACING_V2=true` is set
- `LANGCHAIN_PROJECT` is set to `lab-tutor`
- Use `mcp__langsmith__fetch_runs` to debug agent traces when needed

## Neo4j Safety

Before any Cypher write:
1. Check current schema via `mcp__neo4j-database__get_neo4j_schema`
2. Test the query as a read first (replace MERGE/CREATE with MATCH)
3. Use MERGE, not CREATE, for node upserts
4. Batch all writes with UNWIND when processing lists
