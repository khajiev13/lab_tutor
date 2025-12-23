---
description: "Git workflow requirements (branch naming, commit hygiene, PR description checklist)."
alwaysApply: true
---

# Git Workflow (Required) — migrated from Copilot instructions

## 🌿 Branching

- Always work on a **feature-scoped branch** (never commit directly to `main`).
- Use a consistent branch naming scheme:
  - `feat/<feature-name>` (new feature)
  - `fix/<bug-name>` (bug fix)
  - `refactor/<area>` (refactor/no behavior change intended)
  - `chore/<topic>` (tooling, docs, dependency bumps)
- Keep branches focused: **one logical feature per branch**.

## 🧾 Commits (AI-readable)

- Prefer **small, coherent commits** that match the feature scope.
- Commit messages must be descriptive and searchable:
  - Good: `Integrate Neo4j projection alongside SQL (dual-write) + health checks`
  - Avoid: `update`, `fix`, `wip`
- When a change impacts architecture or runtime behavior, include in the commit body:
  - **What changed** (files/modules)
  - **Why** (design reason)
  - **How to verify** (tests/commands)

## 🧩 Pull requests

PR description must be detailed enough that a future developer (or AI agent) can reconstruct intent.

Include:

- **Scope**: what feature/module is affected
- **Behavior changes**: endpoints, data model, migration notes
- **Neo4j/SQL consistency**: dual-write/rollback behavior if relevant
- **Config**: new env vars required/optional
- **Verification**: tests run (`uv run pytest`, `npm test`, etc.)


