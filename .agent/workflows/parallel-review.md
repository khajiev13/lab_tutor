---
description: Deep multi-agent code review. Spawns 4 specialist reviewers in parallel — security, architecture, performance, and test coverage — then synthesizes findings. Use before any major PR or release.
---

# Parallel Code Review Workflow

Four specialists review simultaneously. Synthesized report at the end.

## Step 1 — Get the diff
// turbo
git diff main...HEAD --stat
git diff main...HEAD
// capture: DIFF

## Step 2 — Spawn 4 reviewers in parallel
// parallel

### Security Reviewer
Role: Security Specialist
Task: Review the diff for:
- Hardcoded secrets, tokens, API keys
- SQL injection or Cypher injection risks
- Unvalidated user input reaching DB or shell
- CORS or auth bypass risks
- Exposed sensitive data in responses
Report as: CRITICAL / WARNING / NOTE
// capture: SECURITY_REPORT

### Architecture Reviewer
Role: Backend Architecture Specialist
Task: Review the diff for:
- Onion Architecture violations (queries outside repository, logic in routes)
- Missing Depends() injection
- Direct service/repo instantiation
- Pydantic v2 conventions (ConfigDict, from_attributes)
- Dead code or unused imports
Report as: MUST FIX / SHOULD FIX / CONSIDER
// capture: ARCH_REPORT

### Performance Reviewer
Role: Performance Specialist
Task: Review the diff for:
- N+1 query patterns in repositories
- Missing indexes on queried fields
- Unbatched Neo4j writes (should use UNWIND)
- Blocking calls in async context
- Unnecessary re-renders in React (missing memo/callback)
Report as: HIGH IMPACT / LOW IMPACT
// capture: PERF_REPORT

### Test Coverage Reviewer
Role: QA Specialist
Task: Review the diff for:
- New code paths without corresponding tests
- Tests that mock the database (forbidden)
- Missing edge case coverage
- Tests with unclear names
Report: list of uncovered paths with suggested test names
// capture: TEST_REPORT

## Step 3 — Synthesize findings
Role: Tech Lead
Task: Combine $SECURITY_REPORT, $ARCH_REPORT, $PERF_REPORT, $TEST_REPORT into:

**Must Fix** (blocks merge): security issues, broken logic, arch violations
**Should Fix**: quality issues, missing tests
**Consider**: minor improvements

Final verdict: Ship it / Fix and re-review / Major rework needed
