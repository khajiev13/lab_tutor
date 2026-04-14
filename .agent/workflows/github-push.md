---
description: Ship code to GitHub safely. Runs all tests, lints, builds, then commits, opens a PR, and merges to main. Spawn this workflow when the user says "push", "ship this", "open a PR", or "commit and push".
---

# GitHub Push Workflow

Complete gate-checked pipeline: test → lint → build → branch → commit → PR → merge.
Never skip a step. Stop and report on any failure.

## Step 1 — Inspect changes
// turbo
git status
git diff --stat

> Identify what changed. If nothing is staged or modified, report and stop.

## Step 2 — Fix backend lint and formatting
// turbo
cd backend && uv run ruff format . && uv run ruff check --fix .

## Step 3 — Run backend tests
cd backend && LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v
// capture: BACKEND_TEST_RESULT
// retry: 0

> If any test fails, STOP. Report failures clearly. Do not proceed.

## Step 4 — Test, lint, and build frontend
// parallel
cd frontend && npm run test -- --run
cd frontend && npm run lint
cd frontend && npm run build
// capture: FRONTEND_RESULT

> If lint or build fails, STOP. Report errors. Do not proceed.

## Step 5 — Determine branch name
// turbo
git branch --show-current

> If already on a feature branch (not main), stay. Otherwise create:
> - feat/<name> for new features
> - fix/<name> for bug fixes
> - refactor/<area> for refactors
> - chore/<topic> for tooling/docs

## Step 6 — Stage and commit
> Stage only relevant files. Never add .env or credential files.
// turbo
git status

> Write commit in format: <type>(<scope>): <imperative summary>
> Body: What changed, Why, How to verify.

## Step 7 — Push and open PR
git push -u origin <branch-name>
// capture: PR_URL

gh pr create --title "<commit summary>" --body "
## Summary
<bullets of what changed>

## Scope
<modules/files affected>

## Behavior changes
<endpoints, UI, data model>

## Verification
- [ ] Backend: uv run pytest -v — all pass
- [ ] Frontend: npm run test -- --run — all pass
- [ ] Frontend: npm run lint && npm run build — clean

🤖 Lab Tutor Agent"

## Step 8 — Merge to main
> Only after PR is open. Confirm with user before merging.
gh pr merge --squash --delete-branch

> Report the PR URL as the final output.
