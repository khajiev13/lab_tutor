# Lab Tutor — Antigravity Rules

> Antigravity-specific overrides. AGENTS.md contains the shared cross-tool foundation.
> Rules here take precedence over AGENTS.md when conflicts exist.

## Agent Behavior

### Development Mode
Use **Agent-Assisted** mode by default (you stay in control, AI handles safe automations).
Switch to **Agent-Driven** (Autopilot) only for well-scoped, isolated tasks like:
- Running tests and fixing lint errors
- Generating boilerplate for new modules following existing patterns
- Writing documentation

### Planning First
Always use **Planning mode** (creates roadmap before execution) for:
- Any task touching the database schema
- New agent/module creation
- Refactors that touch more than 3 files
- Anything involving Neo4j Cypher writes

Use **Fast mode** for: quick bug fixes, isolated UI changes, test runs.

## Multi-Agent Coordination

With unlimited agents, the recommended team structure for Lab Tutor features:

| Role | Responsibility |
|---|---|
| `orchestrator` | Breaks work into tasks, assigns to specialists, synthesizes |
| `backend-specialist` | FastAPI routes, services, repositories, Pydantic schemas |
| `frontend-specialist` | React components, hooks, API integration |
| `neo4j-specialist` | Cypher queries, graph schema, knowledge graph writes |
| `test-validator` | Runs tests, reports failures, verifies correctness |
| `git-agent` | Handles branch, commit, PR, and merge workflow |

For features that touch both frontend and backend, spawn `backend-specialist`
and `frontend-specialist` in parallel. `test-validator` runs after both complete.
`git-agent` runs last and only if `test-validator` reports all green.

## Artifacts

Require artifacts for:
- Any task that runs tests (attach test output)
- Any Cypher query that modifies data (attach query + row count)
- PR creation (attach PR URL + test summary)

## Skills to Load

Always load these skills before the relevant work:
- `fastapi` — before any backend route/schema work
- `shadcn-ui` — before any UI component work
- `neo4j-cypher` — before any Cypher query work
- `langgraph-docs` — before any agent/LangGraph work

## Turbo Rules

Safe to turbo (no confirmation needed):
- `uv run ruff format .` and `uv run ruff check --fix .`
- `npm run lint`
- `git status` and `git diff`

Always confirm before:
- `git push`
- `gh pr merge`
- Any Cypher `MERGE`/`CREATE` write
- `uv run pytest` (shows output, don't suppress)
