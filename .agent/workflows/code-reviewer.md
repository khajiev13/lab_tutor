---
description: Quick focused code review of recent changes. Single agent, fast turnaround. Use before committing or when you want a second opinion on specific changes. For a deep multi-domain review before a major PR, use parallel-review instead.
---

# Code Review Workflow

## Step 1 — Get the diff
// turbo
git diff HEAD
git diff --cached
// capture: DIFF

## Step 2 — Review
Role: Senior Code Reviewer

Audit $DIFF across all four categories:

**Security**
- Hardcoded secrets, tokens, API keys
- SQL/Cypher injection risks
- Unvalidated user input
- Exposed sensitive data in responses

**Correctness**
- No bare `except:` in Python
- No `any` or `!` non-null assertions without justification in TypeScript
- All error paths handled
- No silent failures

**Architecture**
- Backend: queries only in repository.py, Depends() used, Pydantic v2 schemas
- Frontend: API calls only in api.ts, @/ imports, no inline styles
- No dead code, no unused imports

**Tests**
- New code paths have tests
- No mocked database in tests
- Test names describe behavior

## Step 3 — Report
Organize findings as:
- **Must fix** — blocks committing (security, broken logic)
- **Should fix** — architecture violations, missing tests
- **Consider** — minor improvements

Verdict: **Ship it** / **Fix and re-review** / **Major rework needed**

## Step 4 — If "Ship it"
// if verdict is Ship it and user wants to push
// run workflow: github-push
