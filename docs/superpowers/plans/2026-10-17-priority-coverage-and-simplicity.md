# Priority coverage and teacher simplicity

Approved design: `output/teacher-evidence-workspace/skill-priority/usability-review/index.html`; user explicitly requested implementation on 2026-10-17.

## Global constraints

- Preserve the original four teacher decisions, chat-first workflow, saved selections/exclusions, all original posting links, explicit publication approval, and materials readiness gate.
- No new top-level buttons, mandatory steps, automatic selection, or taxonomy/semantic merging changes.
- O*NET official ratings, context-based AI estimates, and unavailable evidence remain distinct. Never fabricate scores to inflate coverage.
- Reuse existing project components, DTOs and controller persistence. Backend owns batching/diagnostics; frontend owns presentation. No shared API/schema change planned.
- Work in existing isolated `feat/teacher-evidence-workspace` worktree. Coordinator owns git and reports; workers edit only their assigned directory.
- Run tests in `lab_tutor_priority_backend` and `lab_tutor_priority_frontend`, which mount this worktree. Real test PostgreSQL is `lab_tutor_priority_postgres`.

## Task 1: Assess the full workload within the bounded deadline

Owner: backend only. Use systematic-debugging, python-service-patterns, test-driven-development and writing-good-tests reference. Read repository AGENTS.md. No nested subagents or git commits.

Problem confirmed: 60 candidate/occupation pairs become 30 two-pair scoring calls, two actual transports at once, 20-second request limits inside one shared 60-second deadline. Complete occupation references repeat per request. Existing terminal partial assessments are cached under prompt version 4. Generic failures obscure the failure class.

Files: `backend/app/modules/marketdemandanalyst/priority_service.py`, relevant `backend/tests/modules/test_market_priority*.py`; preserve current architecture.

1. Add a failing workload-shaped 60-pair test at the external transport boundary showing the current scheduling cannot complete within its budget. Preserve actual transport concurrency including cancellation-resistant calls.
2. Batch by occupation, initially bounded at 20 pairs with bounded input/output. Copied Big Data pairs 32/15/13 become four calls. Measure real provider response latency and quality before finalizing size/timeout allocation; don't claim 60 scores merely because all requests started.
3. Keep complete descriptor definitions/ratings and verified passages. Keep strict pair identity, evidence and anchor validators, lease/CAS/purge/staleness rules. Genuine abstention stays unavailable.
4. Distinguish safe timeout, provider failure, malformed JSON, root-wrapper and schema failures without leaking provider content/secrets. Bump prompt/cache version so old terminal partial results can be reassessed automatically through the existing flow.
5. Verify cache invalidation, workload coverage, unavailable evidence, cancellation concurrency, stale/purged inputs, unchanged choices/publication; run relevant tests and Ruff in the isolated backend container.
6. Write a short report to this plan's SDD workspace with changes, commands/results and remaining live-validation caveats. No production writes. Coordinator performs bounded real-data integration verification.

## Task 2: Put the teacher's present choice and evidence first

Owner: frontend only. Use test-driven-development, existing Shadcn/Tailwind patterns and available relevant skills. Read repository AGENTS.md. No nested subagents or git commits.

Files: market-demand page, SkillSelectionCard, SkillEvidencePanel, CompactComparison and their existing helpers/tests as required.

1. Make the current actionable decision clear based on current execution/review state. Historical narration must not suggest a different next step. Keep history accessible through existing chat; do not introduce a history button. Respect pending job groups, curriculum review, busy/loading/recovery states and materials readiness.
2. Put the saved/current chosen skills first in a compact main card (five in real Big Data). Preserve all selections if more than five; use a bounded preview/summary. Full categories remain optionally browsable by reusing existing Details entry, not adding a second toolbar action. Existing category all-member selection and individual exclusions must work across all 60 candidates. Zero-selected states must still have a discoverable way to choose skills with no silent selection.
3. Original posting link and verified source passage come first in the evidence panel. Keep a short clear score and provenance label; move verbose rationale and metadata into the existing technical disclosure. Preserve full-source loading, purge behavior, accessible focus and safe links.
4. Remove repeated unavailable labels where one concise assessment coverage message suffices; do not imply that missing ratings are zero. Keep official and estimated labels honest. Optional comparison should explain identical job counts compactly rather than repeating five equal bars, with precise partial-coverage denominator.
5. Add meaningful regression tests first for current action precedence, saved/excluded preservation, full-category selection beyond preview, no extra mandatory controls, source-first reading order, and equal-count comparison. Run targeted Vitest, lint and build in `lab_tutor_priority_frontend`.
6. Write a short report to this plan's SDD workspace with behavior, commands/results and acceptance instructions. Keep API contracts unchanged.

## Task 3: Integrate, review and test with fresh context

Owner: coordinator, then independent fresh-context reviewer.

1. Review each task against these constraints and integrate only justified changes.
2. Validate real Big Data copied data through real backend/provider in isolated acceptance storage; compare candidate membership, selected/excluded IDs, posting provenance and publication before/after. Record elapsed time, requested/validated/unavailable counts and truthful reason breakdown.
3. Headless browser acceptance with real copied data at desktop and phone widths: current action, compact saved choices, browse all categories, select category then exclude individual, reload without saving, inspect original posting/source, optional comparison, readiness and stale/busy states.
4. Fresh-context agent independently tests usability and reviews changed code. Address actionable findings and recheck affected behavior; no endless full-suite reruns.
5. Deliver an HTML report with screenshots, verified outcomes and any limits. Production updates, when performed under existing deployment authorization, use exact tested code and verify deployed behavior rather than only health/build status.
