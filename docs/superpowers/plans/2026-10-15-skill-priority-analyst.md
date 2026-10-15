# Skill Priority Analyst Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development, preserving the previously selected execution method, or superpowers:executing-plans if subagents are unavailable. Steps use checkbox (`- [ ]`) syntax for tracking. Follow AGENTS.md ownership: one coordinator; backend and frontend workers only across clear boundaries; a fresh final review and fixes before completion.

**Goal:** Add understandable O*NET importance and clearly labeled AI estimates to the existing teacher skill checklist.

**Architecture:** Insert one bounded `skill_priority_analyst` node after canonical extraction/merging. Reuse the O*NET catalog, review API, execution lease, selection controller and evidence dialog; store assessments separately from teacher decisions. Application code validates evidence and calculates averages; the model interprets meaning and estimates missing scores.

**Tech Stack:** Existing Python 3.12, FastAPI, Pydantic v2, SQLAlchemy/PostgreSQL and LangGraph; React 19, TypeScript and Tailwind/shadcn. No new dependencies, public endpoints, graph database writes or dashboard.

**Spec:** [Approved Skill Priority Analyst design](../specs/2026-10-15-skill-priority-analyst-design.html). Approved by the user on 15 October 2026. Read the specification and its exact prompts before implementing.

**Status:** Plan ready for review; no implementation task has started. Worktree `/Users/khajievroma/.codex/worktrees/teacher-evidence-workspace/lab_tutor`, branch `feat/teacher-evidence-workspace`, inspected code/spec base `0943bf4`.

## Global Constraints

- “No new confirmation, source selector, occupation picker, chart, score slider or agent conversation is added.” Keep the four teacher decisions and category/individual selection behavior.
- “Preserve existing categories, candidate IDs, original labels, posting links, evidence passages, teacher selections and exclusions.” Every selectable skill remains job-backed.
- “No regular expression, title alias table or lexical shortcut may decide semantic equivalence.” Existing lexical search may retrieve records; the analyst judges meaning.
- “Retrieve official values unchanged”; only reported, finite IM values in 1–5 qualify. Estimates are integers 1–5, stored separately. Missing is null, never zero. LV, sample frequency and mastery do not enter importance.
- “A category containing estimates is labeled Estimated”; partial coverage is explicit. Use equal weight per distinct occupation, then per unique complete candidate. Unknown positions stay fixed; checkbox changes never reorder rows.
- “A 60-second total assessment deadline including occupation resolution”; at most two model calls in flight, eight candidate/occupation pairs per batch, request timeout `min(20, remaining_seconds)`, provider retries disabled. Account for every pair, including unfinished work.
- “Refresh and ordinary read APIs never trigger inference.” Pin the release, cache terminal results including degraded ones, reject late/stale writes, preserve ownership and existing execution leases.
- “Priority failure alone neither restarts extraction nor adds a required evidence-consent checkpoint.” Do not weaken the separate job-evidence or publication guards.
- “Never increment candidate/selection/publication revisions solely for adding guidance.” SQL is authoritative; no new Neo4j projection or changes to student APIs, resources, paths or quizzes.
- Keep the feature off until behavioral and estimate-quality checks pass. Estimates need at least 20 evaluation cases, three occupations, five weak controls, zero fabricated references/mislabeled estimates, at least 80% of scored estimates within one point and at least 80% of weak controls abstaining.
- Run app checks in Docker against this worktree, using a real isolated PostgreSQL test database. No host app-dependency installation. Use headless browsers; test 1280×720 and 1440×900 plus mobile/keyboard usability.

## Review Focus

1. A posting is purged, the analysis changes, or the lease ends while AI is running: discard stale results and redact explanations, without restoring removed evidence (Tasks 1, 3, 4).
2. Refresh/disconnect during a slow or malformed batch: finish or recover within the assessment deadline, preserve completed results and avoid endless restoration/repeated inference (Tasks 3, 4).
3. A multilingual skill has several roles, duplicated descriptors or only a broad technology match: no highest-score picking, duplicate weighting or official-looking inferred rating (Tasks 2, 3).
4. A score refresh arrives while the teacher has dirty selections or is on another page: retain choices, exclusions, focus and row order (Task 5).
5. A jobs-only run, empty catalog, legacy conversation or unsupported source combination: guidance stays optional and never changes source configuration, adds a teacher stage or admits reference-only skills (Tasks 3, 4, 6).

## File map and ownership

All paths below are relative to the worktree. `B` means `backend/app/modules/marketdemandanalyst`; `O` means `backend/app/modules/occupation_reference`; `F` means `frontend/src/features/market-demand`. These are notation, not shell variables. New production modules are only `B/priority.py` and `B/priority_service.py`; extend existing files for wiring and display.

| Step | Owner | Files and responsibility |
| --- | --- | --- |
| 1. Save assessments | Backend | Modify `B/models.py`, `B/schemas.py`, `B/repository.py`, `backend/main.py`; create `backend/tests/market_priority_fixtures.py`, `backend/tests/modules/test_market_priority_storage.py`. |
| 2. Calculate guidance | Backend | Create `B/priority.py`, `backend/tests/modules/test_market_priority_policy.py`; extend Step 1 test fixtures. Pure validation, means and ordering. |
| 3. Run the analyst | Backend | Create `B/priority_service.py`, `backend/tests/modules/test_market_priority_service.py`; modify `B/prompts.py`, `O/repository.py`, `backend/app/core/settings.py`. |
| 4. Connect the workflow | Backend | Modify `B/graph.py`, `B/extractor.py`, `B/state.py`, `B/workspace_chat.py`, `B/routes.py`, `B/review_service.py`, `B/tools.py`, `B/repository.py`; create `backend/tests/modules/test_market_priority_flow.py`; extend existing thread-state/evidence tests where appropriate. |
| 5. Keep the UI compact | Frontend | Modify `F/types.ts`, `F/selection.ts`, `F/hooks/useAgentStream.ts`, `F/hooks/useSkillReviewController.ts`, `F/pages/MarketDemandPage.tsx`, `F/components/SkillSelectionCard.tsx`, `F/components/SkillEvidencePanel.tsx`; create `F/__tests__/SkillSelectionCard.test.tsx`; extend selection, stream, controller, evidence and page tests. |
| 6. Prove it with real data | Coordinator | Create `backend/tests/acceptance/skill_priority_evaluation.py`, `backend/tests/modules/test_market_priority_evaluation.py`, `backend/tests/fixtures/skill_priority/evaluation.json`; extend `backend/tests/acceptance/teacher_workspace_server.py` and `frontend/e2e/teacher-evidence-workspace.cjs`; write a sanitized HTML acceptance report under `output/teacher-evidence-workspace/skill-priority/`. |

Order: 1 → 2 → 3 → 4 → 5 → 6. Frontend work may start after Step 1 freezes the DTOs, using fixtures; the coordinator owns final integration. Do not parallelize tasks that edit the same backend files or share the test database.

## Verification setup

The current `lab_tutor_backend` and `lab_tutor_frontend` containers mount the primary checkout, not this worktree. Do not run their app checks and report those as verification of this feature.

Before Step 1's first test, create or reuse isolated containers named `lab_tutor_priority_backend`, `lab_tutor_priority_frontend` and `lab_tutor_priority_postgres`, using the existing Dockerfiles/Compose service definitions. Mount this worktree's backend/frontend at `/app`, retain container-only dependency volumes, build the backend with `UV_SYNC_ARGS=--group dev --frozen`, and use a separate PostgreSQL volume/network. Keep any Compose override under ignored `.superpowers/operations/2026-10-15-skill-priority/`; load existing private environment files without printing credentials, then explicitly override database settings to the isolated instance. Verify the `/app` mounts and database host/name before testing. Do not restart or remount the primary containers.

The isolated PostgreSQL instance needs `lab_tutor_test`; use its normal initialization configuration. Define these command helpers in the execution shell, not in application code:

```bash
priority_btest() {
  docker exec -w /app -e LAB_TUTOR_DATABASE_URL='postgresql://labtutor:labtutor@lab_tutor_priority_postgres:5432/lab_tutor_test' lab_tutor_priority_backend /app/.venv/bin/python -m pytest -v "$@"
}
priority_ftest() {
  docker exec -w /app lab_tutor_priority_frontend npm test -- --run "$@"
}
```

For every red/green cycle, confirm failure is the missing/wrong behavior, not database setup or import-path failure. Run backend suites serially because their fixtures reset the test database. Run Ruff after each backend edit and frontend lint/build after frontend edits. The test commands below are to be executed during implementation; they have not been run for this plan.

## Shared contract

Define these Pydantic DTOs in `B/schemas.py` in Step 1; mirror only public DTOs in `F/types.ts` in Step 5. Use `extra='forbid'` and strict numeric validation on model outputs. Preserve the exact prompt output fields from the approved spec.

| Type | Required shape |
| --- | --- |
| `PriorityScope` | `run_id: UUID`, `course_id: int`, `teacher_id: int`, `expected_candidate_revision: int`. |
| `PriorityContext` | `group_id: str`, `soc_code: str \| None`, `occupation_title: str \| None`, `posting_ids: list[UUID]`, `rationale: str`, `inferred: bool`, `unavailable_reason: str \| None`. |
| `PriorityPair` | `candidate_id: UUID`, `context_key: str`, `soc_code: str \| None`. Use the SOC code as the mapped key; an unmapped group uses `unmapped:<group_id>`. |
| `PriorityDecision` | Model fields: `candidate_id`, `soc_code`, `basis` (`onet`, `ai_estimate`, `unavailable`), `direct_reference_id`, integer `estimate` or null, `associations`, `supporting_evidence_ids`, `explanation`, `limitations`, `unavailable_reason`. |
| `PriorityResult` | Validated decision plus `context_key`, server-populated `official_value` or null and `value` or null. Retain reference IDs and limitations. Never accept official numbers supplied by the model. |
| `CandidatePriority` | `value: float \| None`, basis (`onet`, `onet_aggregate`, `ai_estimate`, `unavailable`), `complete: bool`, `expected_contexts: int`, `scored_contexts: int`, `display_order: int`. |
| `CategoryPriority` | `value: float \| None`, basis (`derived`, `ai_estimate`, `unavailable`), `complete: bool`, `eligible_count`, `scored_count`, `onet_count`, `estimated_count`, `partial_count`, `unavailable_count`, `display_order`. |
| `PrioritySummarySet` | `candidates: dict[str, CandidatePriority]`, `categories: dict[str, CategoryPriority]`. Keys are canonical IDs. |
| `PriorityAssessment` | `assessment_id`, `run_id`, `candidate_revision`, `input_fingerprint`, `schema_version=1`, `policy_version='1'`, `prompt_version='1'`, `model_id`, `release`, timestamps, status (`running`, `ready`, `partial`, `unavailable`, `stale`), contexts, results, summaries, expected/completed pair counts, bounded error reasons. |

`SkillReview.priority_assessment`, `SkillCandidate.priority` and `SkillCategory.priority` are optional, default null. Source configuration and existing selection request bodies are unchanged. `PriorityAssessment` stores reference IDs, not full posting descriptions. The server supplies labels, release URLs and attribution from the validated reference catalog.

## Task 1: Save assessments without touching teacher choices

**Deliverable:** Owned, revision-checked assessment persistence; old analyses still load.

**Files:** Step 1 file-map row. Add the model column beside `MarketAnalysisRun.candidate_manifest`; extend the existing startup upgrade mechanism in `backend/main.py` rather than introducing a migration framework.

**Interfaces:**
- Produce the Shared Contract DTOs.
- `MarketReviewRepository.load_priority_inputs(scope: PriorityScope) -> dict[str, Any]`: require the active owned run and expected revision. Return keys `candidates` (detached `SkillCandidate` DTOs), `categories` (`SkillCategory` DTOs), `groups` (group ID, label and snapshot-ID membership), `passages` (ID-keyed snapshot/offset/text records), `posting_hashes` (snapshot ID to content hash), `configured_release`, `prior_assessment`, and `thread_id`. Use the current owned thread snapshot, not client-supplied job IDs. The service closes this read transaction before external work.
- `MarketReviewRepository.save_priority_assessment(scope: PriorityScope, assessment: PriorityAssessment, *, expected_assessment_id: UUID | None) -> None`: compare-and-set under the run row lock; enforce active run/revision and current source hashes; flush without changing teacher/manifest revisions. Service owns commit/rollback and active lease checks.
- `backend/main.py:_ensure_market_priority_assessment(conn: Connection) -> None`: idempotent nullable JSONB addition, called by `_ensure_sql_schema_upgrades()`.
- Test helper `seed_priority_case(db_session, client, headers, *, skill_count: int = 5)` in `backend/tests/market_priority_fixtures.py`: build on `seed_review`, with real saved passages, groups, owned scope, reference rows and a baseline of teacher choices/revisions. Return named fields used by the tests; do not mock SQL.

- [ ] **1. Write failing storage tests.** Cover absent/null legacy assessments, foreign ownership, inactive run, stale candidate revision, competing assessment IDs and idempotent upgrade on an old-shaped table in an isolated test schema. Snapshot all selected/excluded IDs and three revision numbers before writing.

```python
def test_assessment_preserves_teacher_decisions(case):
    case.repo.save_priority_assessment(
        case.scope, case.assessment, expected_assessment_id=None
    )
    case.repo.commit()
    assert case.reload().priority_assessment["assessment_id"] == str(case.assessment.assessment_id)
    assert case.teacher_decisions() == case.before
```

The `case` fixture wraps `seed_priority_case` and exposes `reload()` and `teacher_decisions()` using a fresh SQL session.

- [ ] **2. Run red:** `priority_btest tests/modules/test_market_priority_storage.py`. Expected: new storage/schema behavior fails before implementation.
- [ ] **3. Implement the column, DTOs and repository interfaces.** Derive stable group IDs from saved membership, not semantic title normalization. Allocate request-local passage IDs from validated snapshot/offset records; provider tags alone do not satisfy the estimate's job-passage requirement.
- [ ] **4. Run green:** repeat the storage suite; also run `priority_btest tests/modules/test_market_skill_review.py tests/test_main.py`. Expected: all pass, old rows and ownership protections preserved.
- [ ] **5. Commit only Step 1 files:** `git commit -m "Add durable skill priority assessments"` after explicit file staging and staged-diff review.

## Task 2: Validate scores and calculate simple summaries

**Deliverable:** Reproducible averages and honest labels, independent of the model.

**Files:** Create `B/priority.py`, `backend/tests/modules/test_market_priority_policy.py`; extend the Step 1 fixtures.

**Interfaces:**
- `validate_priority_decisions(decisions: list[PriorityDecision], *, pairs: list[PriorityPair], references: list[OnetEvidence], passages: dict[str, dict[str, Any]], candidates: list[SkillCandidate]) -> list[PriorityResult]`.
- `build_priority_summaries(candidates: list[SkillCandidate], categories: list[SkillCategory], contexts: list[PriorityContext], results: list[PriorityResult]) -> PrioritySummarySet`.
- `priority_input_fingerprint(inputs: dict[str, Any], contexts: list[PriorityContext], *, release: str | None, model_id: str, prompt_version: str, policy_version: str) -> str`.

- [ ] **1. Write failing policy tests.** Use direct official 4.5/3.5 values, one estimate 4 and two unavailable members. Cover duplicate SOCs, duplicate candidates, mixed direct/estimated roles, partial roles, one-member/empty categories, out-of-range/boolean/NaN values, foreign references/passages, conflicting duplicate decisions and IM versus LV.

```python
def test_partial_category_mean_does_not_zero_fill(policy_case):
    result = build_priority_summaries(**policy_case)
    category = result.categories["data"]
    assert category.value == 4.0
    assert category.scored_count == 3 and category.eligible_count == 5
    assert category.estimated_count == 1
    assert category.basis == "ai_estimate" and not category.complete
```

Define `policy_case` in this test module using Step 1 DTOs. Add `test_unknown_positions_remain_fixed`: input order `[unknown, low, partial, high]` must become `[unknown, high, partial, low]`. `test_checkbox_changes_do_not_change_fingerprint` must keep the hash unchanged; passage/category/group/model/policy changes must change it.

- [ ] **2. Run red:** `priority_btest tests/modules/test_market_priority_policy.py`. Expected: required arithmetic/validation behavior fails.
- [ ] **3. Implement the three pure functions.** Validate exact pair coverage and replace rejected/missing decisions with unavailable outcomes. Retrieve official numbers from the provided validated catalog only. Compute means over unique keys, round display/sort values to one decimal using decimal half-up rounding, and sort only completely assessed entries into their previous slots. Break ties by distinct supporting posting count, then existing order. Use full stored precision for averaging. Fingerprints exclude checkbox choices and contain no raw credentials.
- [ ] **4. Run green:** policy and storage suites together. Expected: invalid evidence cannot produce a score; estimates and partial coverage remain distinguishable; duplicates never increase importance.
- [ ] **5. Commit:** `git commit -m "Calculate evidence-backed skill priority summaries"` with only Step 2 files staged.

## Task 3: Build the bounded analyst

**Deliverable:** All eligible skills receive a score or an explicit unavailable reason within the deadline.

**Files:** Step 3 file-map row. Add `market_skill_priority_enabled: bool = False` with environment name `LAB_TUTOR_MARKET_SKILL_PRIORITY_ENABLED` to existing settings. Copy the two approved prompts exactly from the spec; no new general-purpose agent framework.

**Interfaces:**
- `OccupationReferenceRepository.list_priority_occupations(version: str) -> list[OccupationChoice]`: full ordered imported catalog, no keyword filtering or hidden row cap. Reuse `get_occupations` and `get_evidence` for selected descriptions/descriptor rows.
- `SkillPriorityService(session_factory=SessionLocal, llm_factory=_get_extraction_llm)` and `async assess(scope: PriorityScope, lease: ThreadLease) -> PriorityAssessment` in `B/priority_service.py`. The existing factory already uses zero retries; call its async interface with a per-request timeout and callbacks disabled.
- `get_skill_priority_service() -> SkillPriorityService` for graph-side construction. No new route requires injection.

- [ ] **1. Write failing service tests with a controlled model transport and real SQL.** Include at least 24 candidates; two different SOCs plus two groups mapping to the same SOC; non-English job wording; an empty catalog; an incompatible occupation description; unavailable IM; a tag without a verified passage; and a jobs-only configuration. Reuse the exact accepted prompts in test payload inspection.

```python
async def test_deadline_keeps_results_and_accounts_for_every_pair(service_case):
    result = await service_case.service.assess(service_case.scope, service_case.lease)
    assert len(result.results) == service_case.expected_pairs
    assert result.status == "partial"
    assert service_case.model.maximum_in_flight <= 2
    assert max(service_case.model.scoring_batch_sizes) <= 8
    assert service_case.model.maximum_timeout <= 20
    assert service_case.elapsed_seconds <= 60
```

Use an injected/fake monotonic clock or patched clock for timing tests; do not sleep 60 seconds. Add `test_same_terminal_assessment_makes_no_model_calls`, `test_late_completion_cannot_overwrite_new_assessment`, `test_purge_during_inference_discards_result`, and `test_empty_candidates_make_no_model_call`.

- [ ] **2. Run red:** `priority_btest tests/modules/test_market_priority_service.py`. Expected: orchestration and deadline contracts fail.
- [ ] **3. Implement `assess`.** Read and detach owned inputs, pin/reuse the release, choose then validate occupation contexts, build one pair per candidate/distinct relevant SOC plus unmapped-group outcomes, then score batches. Never hold a SQL transaction across model calls. Use one 60-second monotonic budget covering context resolution and scoring, an async semaphore of two, batch size eight and bounded provider calls. No silent first-N cap; oversized/incomplete scans are unavailable. Each estimate requires a valid rated O*NET anchor and a verified relevant job passage. Do not copy a broad score to every technology.
- [ ] **4. Persist and recover correctly.** Save the running envelope, completed batches and terminal result through Step 1 CAS under the same live lease. Recheck source hashes/ownership and the existing lease connection's ownership before each write; an in-memory active flag alone cannot authorize a write after its SQL session loses the lock. The service may finalize partial results after its model-work deadline, but cannot accept late model completions. Store the original deadline; resume does not reset it. Pin existing contexts for cache comparison; never call the model to discover whether a cached result is reusable. Cache partial/unavailable outcomes too. Disabled feature leaves storage and calls untouched.
- [ ] **5. Run green:** service, policy and storage suites. Expected: terminal result for every pair, no stale writes, no transaction held during model transport, no source-configuration change.
- [ ] **6. Commit:** `git commit -m "Add bounded O*NET skill priority analyst"` with only Step 3 files staged.

## Task 4: Connect extraction, review and recovery

**Deliverable:** The analyst runs once before skill review and failure still returns a usable checklist.

**Files:** Step 4 file-map row. Extend the existing stream and state machinery; no public endpoint or replacement SSE protocol.

**Interfaces:**
- `graph.py: async skill_priority_analyst(state: SwarmState, runtime: Runtime[WorkspaceRuntimeContext]) -> Command` calls Step 3 and returns `Command(goto='skill_finder', update=...)`.
- Add `lease: ThreadLease | None = None` to `WorkspaceRuntimeContext`; inject the existing owned lease in `_sse_stream`, including ordinary workflow calls. Never serialize the lease into checkpoints or `tool_store`.
- Add a persisted minimal state key `skill_priority_status` with `assessment_id`, `status`, `deadline_at`, and `message`; use existing `state_update` events. Running copy is exactly `Assessing skill importance…`. The node emits start/terminal progress through the existing `langgraph.config.get_stream_writer()` pattern; changing state alone cannot stream progress during a silent model call.
- After commit, set existing `skill_review_change_id` to the assessment ID so `skill_review_changed` refreshes guidance without changing candidate/selection/publication revisions.
- `SkillReviewService.review_from_run` adds the matching current assessment and summary DTOs; stale/disabled results have no sortable score. `get_skills_by_category` returns this same validated guidance.

- [ ] **1. Write failing graph/route tests.** Exercise the real compiled routing with controlled external model calls. Assert ordered visits to extractor, analyst and Skill Finder; one `ToolMessage` per pending `start_extraction`; no curriculum handoff before teacher confirmation; and one completed stream terminal. Simulate timeout, dropped client, reload, expired running assessment, disabled feature and a legacy run without durable IDs.

```python
async def test_priority_timeout_returns_to_existing_review(flow_case):
    events = await flow_case.run_with_priority_timeout()
    assert flow_case.visited == ["skill_extractor", "skill_priority_analyst", "skill_finder"]
    assert flow_case.completed_extraction_tool_calls == 1
    assert flow_case.teacher_decisions() == flow_case.before
    assert events[-1] == {"type": "stream_end", "outcome": "completed"}
```

Define `flow_case` in the new flow test module around Step 1 real-SQL fixtures and existing stream helpers. Test `test_progress_arrives_before_delayed_model_finishes`, ordinary message-stream compatibility, `test_review_get_never_calls_model`, `test_pending_guidance_cannot_be_skipped_after_new_extraction`, and `test_removed_evidence_redacts_priority_explanation`.

- [ ] **2. Run red:** `priority_btest tests/modules/test_market_priority_flow.py`. Expected: the new handoff/progress/recovery assertions fail.
- [ ] **3. Wire the node and read path.** Change the durable extractor completion path to finish tool results then route to the analyst; preserve the legacy branch. Persist selected group membership before loading priority inputs. Add the node to graph destinations/re-entry validation. Handle restored pending status before a new skill-choice response, but never launch inference from GET/history reads. For an expired orphan attempt, return terminal unavailable guidance without re-running extraction. Do not release the outer execution lease early.
- [ ] **4. Connect progress and protect evidence.** Consume `stream_mode=['messages', 'custom']` in `_sse_stream`, normalizing the namespace/mode/data envelope with `subgraphs=True`. Translate only the analyst's allowlisted custom progress into the existing public `state_update`; preserve ordinary messages, keepalives and finalization. Emit only the short status, never model JSON or chain text; clear progress on success/failure. On source purge, clear affected rationale and invalidate the assessment. Scope advice-prompt changes to the stored new policy: retain teacher-only confirmation/publication rules, legacy source behavior and mandatory job-evidence acknowledgment rules. Priority-only omissions do not require acknowledgment.
- [ ] **5. Run green:** `priority_btest tests/modules/test_market_priority_flow.py tests/modules/test_market_demand_thread_state.py tests/modules/test_market_skill_pipeline.py tests/modules/test_market_vacancy_evidence.py tests/modules/test_market_skill_approval.py`. Expected: all pass; recovery, publication and posting retention contracts unchanged.
- [ ] **6. Commit:** `git commit -m "Run skill prioritization before teacher review"` with only Step 4 files staged.

## Task 5: Show one small score in the existing checklist

**Deliverable:** Clear importance labels and stable order, without another button or decision.

**Files:** Step 5 file-map row. The live page uses `SkillSelectionCard.tsx`, not the older `SkillChoice.tsx`; test the active component.

**Interfaces:**
- Mirror the public priority DTOs from Step 1 and add optional `AgentState.skill_priority_status`. Do not add a new teacher pipeline stage.
- `selection.ts: priorityLabel(priority: CandidatePriority | CategoryPriority | null | undefined) -> string | null` and `priorityOrder(review: SkillReview) -> {categoryIds: string[]; candidateIdsByCategory: Record<string, string[]>}`. Formatting only: backend owns scores and ordering.
- Labels: `4.2/5 · O*NET`, `4/5 · AI estimate`, `4/5 · O*NET average`, category `4/5 · Estimated`, partial category `4/5 · Estimate · Partial`, and `Not assessed` for an unavailable result. Null priority on an older/disabled run renders no new label. Explain all aggregates as Lab Tutor summaries in the evidence view.

- [ ] **1. Write failing UI tests.** Create `SkillSelectionCard.test.tsx` with 24 supported skills, a category spanning several pages, one unsupported reference-only item and saved exclusions. Test official/estimated/partial labels; source links; pending progress; and no new button or approval. Extend the controller test for a priority-only refresh with unchanged review revisions and a dirty local draft.

```tsx
it("preserves dirty choices and row order when guidance refreshes", async () => {
  const view = setupPriorityReview();
  await view.exclude("etl");
  const before = view.visibleCandidateIds();
  view.refreshPriorityOnly();
  expect(view.visibleCandidateIds()).toEqual(before);
  expect(view.controller().draft.excluded_candidate_ids).toContain("etl");
  expect(view.confirmButtonCount()).toBe(1);
});
```

Define `setupPriorityReview` locally in the new active-component test using `useSkillReviewController` and existing review fixtures. Add assertions that category selection includes off-page members and reopening/reload retains an individual exclusion. Compare available controls against the current unscored card.

- [ ] **2. Run red:** `priority_ftest src/features/market-demand/__tests__/SkillSelectionCard.test.tsx src/features/market-demand/__tests__/useSkillReviewController.test.tsx`. Expected: the label/order/refresh behavior fails.
- [ ] **3. Implement the compact display.** Render a small non-interactive label beside each scored skill/category using existing styling utilities. Add provenance, role, source value/estimate, coverage and limitations inside `SkillEvidencePanel`; retain original posting links. Capture order on the first render of a mounted review session, keyed by run and candidate revision, using the current assessment when available. A later assessment-ID change may update labels but must not move rows; a new session or candidate revision captures a new order. Do not recalculate priority after checkbox changes. When disabled/stale at entry, preserve the pre-existing ordering behavior.
- [ ] **4. Connect progress and review refresh.** Reuse `state_update` and `skill_review_changed`; the controller must accept new assessment data at unchanged selection revisions without resetting a dirty draft. Show the running copy in the existing activity area and clear it at terminal status/expired recovery. Treat the analyst as background work, not a new conversational message.
- [ ] **5. Run green:** `priority_ftest src/features/market-demand/__tests__/SkillSelectionCard.test.tsx src/features/market-demand/__tests__/selection.test.ts src/features/market-demand/__tests__/SkillEvidencePanel.test.tsx src/features/market-demand/__tests__/useSkillReviewController.test.tsx src/features/market-demand/__tests__/useAgentStream.test.tsx src/features/market-demand/__tests__/MarketDemand.test.tsx`. Then run frontend lint/build in the isolated container. Expected: all relevant behavior passes; exactly the existing teacher controls remain.
- [ ] **6. Commit:** `git commit -m "Show compact importance guidance in skill selection"` with only Step 5 files staged.

## Task 6: Validate estimates and the real teacher experience

**Deliverable:** A concise HTML acceptance report with measured results and a fresh independent review.

**Files:** Step 6 file-map row. Keep copied Big Data source material, login tokens and private manifests outside Git; report only sanitized counts/screenshots. Reuse the existing acceptance server and headless browser harness, preserving its external-model/provider guards.

**Test environments:** Keep pytest on `lab_tutor_test`. Browser fixtures require a separate `lab_tutor_workspace_acceptance` database on the isolated PostgreSQL instance and the disposable Neo4j hostname `lab_tutor_market_projection_test`, using `backend/tests/docker-compose.market-projection.yml`. Never point either harness at an application database. Live-model evaluation runs in a separate process against the isolated snapshot; the browser server continues to disable external model/provider calls. It may load validated saved evaluation results through a test-only fixture action, while controlled responses exercise timeouts and failures.

**Interfaces:**
- `skill_priority_evaluation.py: evaluate_priority_cases(case_path: Path, output_dir: Path) -> dict[str, Any]`, CLI `--cases` and `--output`. JSON output includes case count, occupation count, weak-control count, fabricated-reference count, mislabeled-estimate count, within-one-point rate, abstention rate, coverage and elapsed time. Refuse databases other than the isolated acceptance database; acquire the normal lease for each copied analysis. Use the real configured model only in this runner, with no source collection or production writes.
- In the same runner, `async assess_copied_snapshot(scope: PriorityScope, output_dir: Path) -> PriorityAssessment`, CLI `--snapshot-scope` (private JSON file, mutually exclusive with `--cases`). Reuse Step 3's service and the normal lease; record coverage/latency separately from evaluation accuracy because real-course skills have no assumed gold scores.
- Extend the acceptance harness with `WORKSPACE_SCENARIO=skill-priority`, reusing its explicit isolated URLs and private manifest. Remove the hardcoded acceptance-container name for this scenario by accepting `WORKSPACE_BACKEND_CONTAINER=lab_tutor_priority_backend`; preserve the existing default for other scenarios.

- [ ] **1. Write failing evaluation checks.** Reject fewer than 20 cases, fewer than three roles, fewer than five weak controls, leaked held-out target ratings in model input, fabricated references or wrong basis labels. Make the evaluator fail below either 80% threshold. Divide correct-within-one-point estimates by all scorable target cases, counting an abstention on such a case as not correct; divide correct abstentions by all weak controls. For 15 scored targets and five weak controls, 12 accurate estimates and four correct abstentions meet both thresholds exactly. Define reviewed target provenance in the fixture; never generate gold target scores with the agent being evaluated.
- [ ] **2. Run red:** `priority_btest tests/modules/test_market_priority_evaluation.py`. Expected: the evaluator/threshold checks fail before implementation.
- [ ] **3. Implement and run the evaluator.** Use held-out official descriptor ratings as sourced human-research targets where appropriate, plus reviewed weak controls and specific-technology examples. Keep exact target ratings out of assessment inputs. Clearly separate synthetic test transport, live-model evaluation and copied real-course results. If suitable reviewed targets are unavailable, report that limit and keep the flag disabled; do not claim calibration.
- [ ] **4. Run the copied Big Data scenario.** Copy course context/material metadata plus the saved job-backed candidates, groups and evidence into the isolated acceptance database. Reuse the saved analysis; no document re-upload or re-extraction is needed. Record current counts rather than hardcoding the historical 38 documents/60 candidates. Run the separate live-model runner on that copy and inspect every result for evidence ownership/basis. Load the validated results in the guarded browser fixture; exercise category choice/exclusion/save/reload, original links and keyboard access. Capture headless views at 1280×720, 1440×900 and a narrow mobile viewport. Verify finite timeout, no extra teacher question or main-page scrolling, and no row movement on selection. Compare pre/post live-course fingerprints read-only; live choices/publication must not change.
- [ ] **5. Run green and final checks.** Evaluation tests and all affected backend/frontend suites must pass. Execute the evaluator command and the headless `skill-priority` scenario against the isolated services; success requires the report's acceptance predicates, not merely exit zero from a build. Run:

```bash
docker exec -w /app lab_tutor_priority_backend /app/.venv/bin/ruff check .
docker exec -w /app lab_tutor_priority_backend /app/.venv/bin/ruff format --check .
docker exec -w /app lab_tutor_priority_frontend npm run lint
docker exec -w /app lab_tutor_priority_frontend npm run build
docker exec -w /app -e LAB_TUTOR_DATABASE_URL='postgresql://labtutor:labtutor@lab_tutor_priority_postgres:5432/lab_tutor_workspace_acceptance' lab_tutor_priority_backend /app/.venv/bin/python -m tests.acceptance.skill_priority_evaluation --cases tests/fixtures/skill_priority/evaluation.json --output /tmp/skill-priority-evaluation
```

Use the installed browser-testing runtime to run `frontend/e2e/teacher-evidence-workspace.cjs` with `WORKSPACE_SCENARIO=skill-priority`, `WORKSPACE_BACKEND_CONTAINER`, `WORKSPACE_UI_URL`, `WORKSPACE_API_URL`, `WORKSPACE_FIXTURE_PATH`, `WORKSPACE_SERVER_MANIFEST` and `WORKSPACE_OUTPUT_DIR` pointing to this isolated run. Do not install browser dependencies on the host. Store the exact resolved invocation in the acceptance receipt.

- [ ] **6. Request a fresh-context final review.** Supply the approved spec, code diff and acceptance evidence, not the implementer's conclusions. Ask the reviewer to try the normal teacher flow, judge simplicity and verify estimated/official labels, restoration and selection preservation. Fix actionable findings and rerun affected checks; repeat until no unresolved material findings remain. Summarize measured results and any limits in `output/teacher-evidence-workspace/skill-priority/index.html`.
- [ ] **7. Commit the final tested changes and sanitized report.** Enable the backend flag only for the validated release; document the flag-off rollback. Do not mix unreviewed source-collection changes or live-course edits into this release. Deployment uses the project's existing workflow after implementation is complete and verified.

## Plan self-review and handoff

Self-review completed against the approved specification: scope/context → Tasks 3–4; numerical rules/aggregation → Task 2; runtime → Tasks 3–4; storage/API/invalidation → Tasks 1 and 4; exact prompts → Task 3; compact UI → Task 5; estimate/Big Data acceptance and fresh review → Task 6. All five Review Focus items have explicit tests assigned above. The review corrected silent-node progress delivery, isolated database targeting and the separation of guarded browser fixtures from live-model evaluation.

The HTML companion is the user-facing plan. This Markdown is its technical source. The specification is approved; this plan still needs the user's review before implementation. Preserve the earlier subagent-driven preference with clear backend/frontend ownership, sequential dependent work, coordinator verification and a fresh final review. No source or production settings have been changed by writing this plan.
