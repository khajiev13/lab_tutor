# Teacher Evidence Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give teachers a simple database-backed ECharts workspace for inspecting job evidence, discovering defensible patterns, choosing skills and discussing the current evidence with the agent.

**Architecture:** Extend the existing Market Demand Analyst feature and SQL review contracts. Keep one authoritative review, one local shortlist and one conversation/checkpointer; add a restricted contextual entry to the existing graph. The main area presents evidence and teacher decisions, with conversation on the right.

**Tech Stack:** Existing React 19, strict TypeScript, Tailwind v4, Shadcn, React Router 7, FastAPI, Pydantic v2, SQLAlchemy, LangGraph and PostgreSQL; add modular Apache ECharts. No new database or SQL migration is planned.

**Spec:** [Approved teacher evidence workspace specification](../specs/2026-10-11-teacher-evidence-workspace-design.html), commit `4552f61`; approved by the user on 12 October 2026. Read both documents before executing. The [HTML plan](2026-10-12-teacher-evidence-workspace.html) is the primary review version; this file is the execution checklist.

## What the teacher will get

Overview starts with one demand chart and at most two useful patterns. Compare reveals occupational importance/level; Data exposes exact values. Every view shares category selection and individual exclusions. Clicking evidence only focuses it; the agent explains or proposes, and the teacher saves and approves.

Work is grouped into twelve independently verifiable tasks. Tasks 1–4 establish trustworthy backend behavior; tasks 5–10 build the frontend pieces; task 11 assembles the experience; task 12 verifies the complete flow. These are implementation tasks, not twelve new product subsystems.

## Global Constraints

- “Every skill published for students still needs a stored, qualifying job-posting link and supporting evidence.” Preserve the existing final `422 missing_job_evidence` gate, exact approval digest and student APIs, paths, resources and quiz mastery.
- “PostgreSQL is authoritative.” Neo4j stays the projection. Never use prototype counts or scripted replies as production fallback.
- “Chart clicks focus the skill and evidence; they never select, save or approve it.” No model calls on click, hover or filter changes.
- “Show at most two” patterns. Demand 0–100%; IM 1–5; LV 0–7. Overview 12 rows; heatmap 12 rows/page; Data 25 rows/page; at most 5 occupations.
- Show both panes at **1,000 CSS pixels of available workspace width**, accounting for the app sidebar; chat defaults to **360px**. Smaller workspace: Workspace / Conversation with preserved state.
- Context: message ≤8,000 characters; JSON context ≤16 KiB; explicit candidates ≤20; categories ≤10; occupations ≤5; descriptor choices ≤20; reference element IDs ≤20; search ≤120 characters. Model evidence ≤24 KiB and at most two 600-character excerpts per focused candidate.
- Reject contextual source configuration; explain has no mutating tools; propose can write only an immutable recommendation. Ordinary review questions retain `intent:"explain"` after removing focus.
- “A read must not acquire a workflow lease.” Idle is a point-in-time observation, never proof of completion. Closing a stream is detachment, not server cancellation.
- Keep HTTP wrappers in feature `api.ts`, `@/` imports, Tailwind/`cn()`, react-hook-form + zod for forms. SQL in repositories, behavior in services, route injection through `Depends()`.
- Run app tests/dependency installation in Docker; real PostgreSQL tests, no mocked repositories. External model/provider boundaries may be deterministic doubles. Headless browsers only.
- No all-agent migration, new provider, weighted score, historical trend/co-occurrence analytics, run-history browser, provider-specific retry, true cancellation or scheduled crawling.

## Review Focus

These five less-obvious conditions receive explicit tests in the owning task:

1. A conversation is idle but its checkpoint still has unfinished workflow work: an evidence question must not resume that work or discard it. **Task 3.**
2. A snapshot is purged after a question: stored context metadata must not preserve source excerpts, and evidence inspection must report unavailability. **Tasks 2 and 4.**
3. Save completes after the teacher changes course or after a newer review arrives: ignore the late result; mapping/proposals use the acknowledged revision, never an old render closure. **Tasks 5 and 8.**
4. A reset fails after SQL state deletion but before checkpoint deletion: preserve recoverable input and reconcile; do not claim the former run is still active. **Tasks 8 and 11.**
5. The same competency has different evidence UUIDs in different occupations, while one candidate matches two descriptors: compare descriptor identity, preserve ambiguity, and never choose the largest rating. **Tasks 2 and 6.**

## Repository map and ownership

The coordinator owns this plan, shared contracts, task integration and final verification. A backend worker owns `backend/`; a frontend worker owns `frontend/`. Do not run two workers editing the same frontend types/page/hook, or the same backend graph/routes. Commit operations remain serialized by the coordinator.

| Area | Existing files to extend | Focused new files |
| --- | --- | --- |
| SQL review and status | `backend/app/modules/marketdemandanalyst/{schemas,repository,review_service,thread_state_service,routes}.py` | None for metadata/status |
| Context and patterns | Same repository/schema boundary | `workspace_service.py`, `workspace_patterns.py` in that module |
| Contextual execution | `graph.py`, `routes.py`, `prompts.py` | `workspace_chat.py` in that module |
| Frontend transport | `frontend/src/features/market-demand/{types,api}.ts`, `hooks/useAgentStream.ts` | None |
| Shared review and data | `selection.ts`, `components/SkillReviewPanel.tsx` | `hooks/useSkillReviewController.ts`, `workspace-data.ts`, `workspace-context.ts` |
| Evidence views | `components/SkillEvidencePanel.tsx` | `EvidenceChart.tsx`, `WorkspaceOverview.tsx`, `WorkspaceCompare.tsx`, `WorkspaceDataTable.tsx` under `components/` |
| Conversation and page | `ChatInput.tsx`, `AgentMessage.tsx`, `UserMessage.tsx`, `pages/MarketDemandPage.tsx` | `components/WorkspaceConversation.tsx`, `components/OccupationReferencePanel.tsx`, `hooks/useWorkspaceNavigationGuard.ts` |
| Navigation guard | `frontend/src/App.tsx` | No route redesign; minimal Data Router shell for supported navigation blocking |
| Verification | Existing market-demand tests and real SQL fixtures | Focused test files named per task; final acceptance harness/report |

`components/IntegrationReview.tsx` remains the approval authority in the UI; adapt props only if controller integration requires it. Remove `components/StatePanel.tsx` and its usages after replacing the legacy results sidebar. Retain unrelated Recharts usage.

## Shared contracts and execution order

All task-local files below are relative to the repository root; `B/` means `backend/app/modules/marketdemandanalyst/`, `F/` means `frontend/src/features/market-demand/`. These aliases are documentation shorthand, not new filesystem roots.

- `SkillReview.analysis_metadata?: AnalysisMetadata | null` uses the exact approved object: `country`, `job_sources`, `evidence_sources`, `onet_release`, `occupations:[{soc_code,title}]`, `created_at`, `updated_at`. Values come from that review’s run, never another thread snapshot.
- `GET /courses/{id}/market-demand/execution-status` returns `{status:"busy"|"idle",state_updated_at:string|null}`. HTTP failure is local `unknown`, not a third server value.
- `WorkspaceContext = RunReviewContext | OccupationReferenceContext` follows spec §6C field-for-field, including version 1, intents, filter scope and descriptor choices. Pydantic objects forbid extras. Context with country/location/providers/release configuration in the outer chat request is 422.
- `context_resolved` carries the stable human message ID plus safe metadata. `error` carries `code`, `message`, `recovery`. `stream_end` adds `outcome:"completed"|"failed"`; old requests remain supported. History messages gain optional matching context metadata. A restored transcript without terminal proof must not claim success.
- `WorkspaceViewState` contains `view`, `filters`, `focusedCandidateId`, `occupationCodes`, `activeOccupationCode`, `metric`, `descriptorChoices`, `sort:{field,direction}`, `page`. Use candidate IDs and evidence IDs, never chart positions as identity.
- Frontend `SendCommand = {mode:"workflow",text:string} | {mode:"contextual",text:string,context:WorkspaceContext}`. Contextual transport omits workflow configuration. Missing focus never means workflow mode.
- Pattern corpus is one reviewed JSON corpus mirrored byte-for-byte into backend and frontend test directories because the existing containers mount each application separately. Edit the backend copy, copy it to the frontend, and verify `cmp` at integration. Both languages assert exact outputs from all cases; neither has a separate set of thresholds.

Backend dependency chain: **1 → 2 → 3 → 4**. Frontend: **5 → 6 → 7**, then **8 → 9**, with **10** using the reference API and shared types. **11** joins these pieces; **12** verifies the result. Backend and frontend work may overlap after these contracts are frozen, but tasks within each ownership boundary remain sequential. No product rollout until task 12 passes.

### Execution preflight, folded into Task 1

Use `superpowers:using-git-worktrees` at execution time and a feature branch such as `feat/teacher-evidence-workspace`; base it on the approved specification and plan commits. Preserve the existing unrelated dirty checkout. Do not copy `.env` into Git or include unrelated dependency/Docker changes in this feature. Apply the user’s current AGENTS instructions in the worktree too.

Check which source checkout the Docker containers actually mount before testing. Reuse suitable containers only when they point to the implementation checkout; otherwise create scoped development containers with the existing Compose definitions and isolated names/ports. Do not claim verification against another checkout. Commands below use the project’s standard container names; substitute only the verified scoped equivalents.

Use the explicit test database URL shown in every backend command. `tests/conftest.py` creates/drops schema and truncates tables: never point it at a development or production database, and never run two pytest processes against the same test database. Start required containers if stopped; investigate an unhealthy environment before changing product code. If `docker` is absent from PATH on this Mac, use `/Applications/Docker.app/Contents/Resources/bin/docker`. No host app-dependency installation. For every task commit, stage the named files explicitly with `git add -- <task paths>`, inspect the staged diff, then `git commit -m "<task message>"`; do not stage the whole working tree.

---

### Task 1: Return authoritative analysis metadata and execution status

**Files:** Modify `B/schemas.py`, `B/review_service.py` (`review_from_run`), `B/repository.py` (`ThreadStateRepository`), `B/thread_state_service.py`, `B/routes.py`. Tests: `backend/tests/modules/test_market_skill_review.py`, `backend/tests/modules/test_market_demand_thread_state.py`.

**Interfaces:** Produces `AnalysisMetadata`, `AnalysisOccupation`, `ExecutionStatus`; `ThreadStateRepository.execution_status(thread_id: str) -> ExecutionStatus`; `async ThreadStateService.execution_status(thread_id: str) -> ExecutionStatus`. Existing `get_review` returns the extended `SkillReview`.

- [ ] **Write failing tests** for populated/legacy/no-run metadata, ownership, and a second service observing a real PostgreSQL lease. Core assertions:

```python
assert review.analysis_metadata.onet_release == run.config["onet_release"]
assert empty_review.analysis_metadata is None
assert (await observer.execution_status(thread_id)).status == "busy"
# Repeated observation neither releases nor acquires the conversation lock.
with pytest.raises(ThreadBusy):
    await competitor.claim(thread_id)
```

- [ ] **Run red:** `docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_market_skill_review.py tests/modules/test_market_demand_thread_state.py'`. New tests must fail for missing fields/status behavior, not infrastructure.
- [ ] **Implement** metadata from the same run, including null/empty legacy fields. Observe `pg_locks` using current database OID, granted advisory lock, unsigned high/low 32-bit halves of `hashtextextended(thread_id,0)` and `objsubid=1`; read `MDAThreadState.updated_at`. Add the owned, injected GET endpoint. Never call lock acquisition in status. Test wrong-key/current-database separation and busy through finalization.
- [ ] **Run green:** repeat the exact task command; all selected tests pass. Run the backend Ruff command in the final-check section before committing Python changes.
- [ ] **Commit only this task’s files:** `feat: expose market analysis metadata and execution status`.

### Task 2: Resolve bounded, owned context and deterministic patterns

**Files:** Create `B/workspace_service.py`, `B/workspace_patterns.py`, `backend/tests/modules/test_market_workspace_context.py`, `backend/tests/modules/test_market_workspace_patterns.py`, `backend/tests/fixtures/teacher-workspace-patterns.json`. Modify `B/schemas.py`, `B/repository.py`, `B/routes.py` (dependency factory), and fixture helpers in `backend/tests/market_skill_fixtures.py` only as needed.

**Interfaces:** `WorkspaceContextService.resolve(course_id:int, teacher_id:int, request:WorkspaceContext) -> ResolvedWorkspaceContext`; detached result holds `request`, `intent`, `revision:SkillReviewRevision|None`, `model_bundle:dict`, `history_metadata:ResolvedContextMetadata`. `derive_pattern_observations(review:SkillReview, context:RunReviewContext) -> list[PatternObservation]`. Constructor-inject SQL and occupation repositories. `PatternObservation` has `kind:InsightKind`, `candidate_ids:list[str]`, `occupation_codes:list[str]`, `descriptor_keys:list[tuple[str,str,str]]`, `values:list[PatternValue]`, `coverage:dict`. `PatternValue` is `{candidate_id, occupation_code:null|str, value:float, supporting_count:null|int, assessed_count:null|int}`; `InsightKind` is the spec's three pattern names. Use that same JSON shape in TypeScript; snapshot/revision/filter identity is carried by the enclosing resolved context.

- [ ] **Write failing SQL/contract tests** covering every bound, unknown fields, foreign ownership, stale revisions, invalid candidate/occupation/evidence membership, mixed configuration and reference-only contexts. Seed from real SQL fixtures; model invocation count stays zero on rejection.

```python
assert stale_response.status_code == 409
assert stale_response.json()["detail"]["code"] == "context_stale"
assert len(json.dumps(resolved.model_bundle, ensure_ascii=False).encode()) <= 24 * 1024
assert "original_description" not in json.dumps(resolved.history_metadata.model_dump())
assert source_excerpt not in json.dumps(resolved.history_metadata.model_dump())
```

- [ ] **Run red:** `docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_market_workspace_context.py tests/modules/test_market_workspace_patterns.py'`.
- [ ] **Implement resolution** against the active owned run after lease acquisition. Query bounded owned postings and fresh O*NET rows through repositories; validate ready/pinned release, occupation, descriptor and relation. Detach facts and release the read transaction before model work. Use saved selection for attached `scope="selected"`; reject dirty selected-scope/proposal requests. Return 404/409/422 per the spec. Apply the UTF-8 byte budget to valid complete JSON; count omissions after budgeting. Only IDs/labels/facts/revisions/counts enter persistent metadata, never source bodies/excerpts.
- [ ] **Implement pure pattern rules and corpus.** Common sample: denominator ≥10, support ≥3 and percentage ≥50, same denominator, ≤3 skills. Difference: same `(release,family,element_id)`, ≥2 occupations and IM spread ≥1.0. Shared importance: every compared occupation reported IM≥4, ≥2 roles. Max 2 observations in approved priority, no repeated skill; sort ties by normalized label then stable ID using identical lexical rules in both languages. Corpus cases include 9/10 denominators, 2/3 supports, 49.9/50%, spread .99/1.0, IM3.99/4, ties, partial/mixed coverage, missing/suppressed values, ambiguity, duplicate evidence and distinct per-role evidence UUIDs. Pattern scope is all matching candidates, not a page.
- [ ] **Run green:** repeat task command and Ruff. Include multibyte text at byte limits, empty search/filter combinations and purged evidence. Both models and DB facts remain unmodified during resolution.
- [ ] **Commit only this task’s files:** `feat: resolve validated workspace evidence context`.

### Task 3: Add a restricted contextual entry to the existing graph

**Files:** Create `B/workspace_chat.py`, `backend/tests/modules/test_market_workspace_chat.py`. Modify `B/graph.py`, `B/routes.py` (`ChatRequest`, `/chat`, stream context/persistence arguments), `B/prompts.py`. Reuse `B/review_service.py`, `B/tools.py` owned-execution helpers; change them only if a narrow public helper is required.

**Interfaces:** `WorkspaceRuntimeContext` carries an optional detached resolved context, course/teacher identity and allowed intent for one invocation; absent context means legacy workflow. `route_entry(state:SwarmState, runtime:Runtime[WorkspaceRuntimeContext]) -> str`; `async workspace_review(state:SwarmState, runtime:Runtime[WorkspaceRuntimeContext]) -> dict` returns only `messages`. `create_workspace_proposal(course_id:int, teacher_id:int, revision:SkillReviewRevision, changes:list[RecommendationChange]) -> tuple[SkillReview,dict]` delegates to the existing recommendation service with frozen revisions. No inner lease acquisition. Extend `_sse_stream` with `runtime_context:WorkspaceRuntimeContext|None` and server-only `persistence_policy:Literal["workflow_snapshot","checkpoint_only","proposal_snapshot"]`; the client cannot choose these parameters.

- [ ] **Write failing real-graph/checkpointer tests** with a deterministic external model double, not a fake graph. Run workflow → explain → workflow and inspect routing/history/state; try fabricated fetch/delete/publish tool calls and stale proposals.

```python
assert after_inspect.values["active_agent"] == before.values["active_agent"]
assert provider_calls == []
assert saved_run.config == before_config
assert saved_selection == before_selection
assert pending_checkpoint_response.status_code == 409
assert pending_checkpoint_response.json()["detail"]["code"] == "workflow_recovery_required"
```

- [ ] **Run red:** `docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_market_workspace_chat.py tests/modules/test_market_skill_recommendations.py'`.
- [ ] **Implement one guarded entry.** Replace only the `create_swarm` convenience construction with equivalent public `StateGraph(SwarmState, context_schema=...)` construction, preserving current nodes/handoff destinations/checkpointer and `skill_extractor`. Use one START router: validated runtime context → `workspace_review`; otherwise existing active agent/default supervisor. Do not add a second START branch or second parent graph. Review node has no handoffs and leaves `active_agent` unchanged. Runtime bundle never enters graph state or `STATE_KEYS`.
- [ ] **Wire the contextual route under the existing lease.** Check ownership, claim, resolve revisions/facts, then read checkpoint. Reject unfinished workflow tasks before invoking a model; do not resume them through chat. Explain binds zero tools; propose binds only the revision-bound proposal wrapper with existing owned-worker finalization. Reference questions create no run. Skip configuration and seeded tool-state defaults. Pass an explicit server-owned persistence policy: explain/reference writes checkpoint messages only; proposal relies on the existing committed proposal snapshot rather than overwriting it with stale state.
- [ ] **Run green:** repeat task command and Ruff. Verify stale proposal rejection, no saved/excluded selection mutation, no nested lease, no raw context in checkpoints, ordered history and unchanged legacy handoffs. Clean test checkpoint IDs/pools. Consolidate legacy prompt conflicts around sample frequency, permitted retries and teacher approval; do not change the provider contract.
- [ ] **Commit only this task’s files:** `feat: isolate workspace explanations and proposals`.

### Task 4: Make stream completion and restored context truthful

**Files:** Modify `B/routes.py` (`_sse_stream`, history conversion), `B/workspace_chat.py`, `B/schemas.py`; extend `backend/tests/modules/test_market_demand.py`, `test_market_demand_thread_state.py`, `test_market_workspace_chat.py`.

**Interfaces:** Existing SSE frame shape plus the shared `context_resolved`, `error`, `stream_end.outcome` fields. Safe contextual metadata lives in `HumanMessage.additional_kwargs["workspace_context"]`. Stable server-generated human ID joins live and historical messages. Terminal SSE outcome is distinct from checkpointed reply text; no new durable terminal-status store is introduced.

- [ ] **Write failing tests** for model failure, final SQL/checkpoint failure, absent terminal result after detachment, stable message identity and redacted history:

```python
assert frames[-1]["data"]["outcome"] == "failed"
assert context_event["messageId"] == restored_user_message["id"]
assert "workspace_context" in restored_user_message
assert source_excerpt not in json.dumps(restored_user_message["workspace_context"])
```

- [ ] **Run red:** `docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_market_demand.py tests/modules/test_market_demand_thread_state.py tests/modules/test_market_workspace_chat.py'`.
- [ ] **Implement** sanitized error codes/messages/recovery without exception repr. Emit completed only after successful owned finalization; failed when final persistence fails. On restore, reconcile review/history and keep outcome unknown when no terminal proof exists; do not retrofit a synthetic success marker into checkpoints or infer it from reply text. Preserve managed producer/draining/lease release after browser detach. Register `workspace_review` display metadata as “Evidence assistant” and retain that agent identity in stream/history. Extend history conversion without merging distinct contextual turns or dropping old messages. Tool completion is not source success; source outcomes remain authoritative. Use a `finished`/unknown display state where success is not proven, retaining old wire compatibility where necessary.
- [ ] **Run green:** repeat task command and Ruff. A second service must still observe busy until owned work drains. Historical purged evidence is unavailable through inspection; context metadata contains no retained payload. Legacy request/event tests remain green.
- [ ] **Commit only this task’s files:** `fix: report market conversation outcomes accurately`.

### Task 5: Extract the single teacher shortlist controller

**Files:** Create `F/hooks/useSkillReviewController.ts`, `F/__tests__/useSkillReviewController.test.tsx`. Modify `F/components/SkillReviewPanel.tsx`, `F/pages/MarketDemandPage.tsx`, `F/types.ts`, `F/__tests__/SkillReviewPanel.test.tsx`; reuse `F/selection.ts` and integration review.

**Interfaces:** `useSkillReviewController({courseId,review,onReviewChange,disabled}) -> SkillReviewController`. It receives the one authoritative review from `useAgentStream`; owns local draft/undo/reconciliation/view state. Export actions `setCandidate`, `setCategory`, `applyProposal`, `acknowledgeReconciliation`, `acknowledgeIncomingReview`, `updateView`, `undo`; `save()`, `reviewMappings()`, `acknowledgeAvailableEvidence()` each return `Promise<SkillReview>` and reject failures. Expose `dirty`, `busy`, `reviewRequired`, `error`, `canUndo`.

- [ ] **Write failing controller/component tests:** category selection includes search-hidden members; exclusions survive proposals; new/merged candidates are not auto-selected; dirty same-run refresh preserves valid choices; an older save cannot cross a course/run generation.

```ts
expect(result.current.draft.selected_candidate_ids).toEqual([pythonId, sqlId]);
expect(result.current.draft.excluded_candidate_ids).toContain(powerBiId);
expect(confirmSkillReviewSelection).toHaveBeenCalledWith(courseId,
  expect.objectContaining({expected_selection_revision: acknowledged.selection_revision}));
```

- [ ] **Run red:** `docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/useSkillReviewController.test.tsx src/features/market-demand/__tests__/selection.test.ts src/features/market-demand/__tests__/SkillReviewPanel.test.tsx src/features/market-demand/__tests__/IntegrationReview.test.tsx'`.
- [ ] **Implement extraction, not a second store.** First mirror the shared `AnalysisMetadata`, `WorkspaceContext`, `ResolvedContextMetadata`, `ExecutionStatus` DTOs and define `WorkspaceViewState` in `types.ts`; Task 8 adds their transport behavior. Move existing local decisions/actions into the controller. Keep server-owned selection separate from dirty draft. Acknowledge changed revisions before another save, surface lost candidate names, retain protected exclusions and explicit reconciliation IDs. `reviewMappings()` first awaits successful save if dirty and confirms the returned revisions. Make SkillReviewPanel controlled. Do not add an earlier backend posting gate or alter approval/withdrawal semantics.
- [ ] **Run green:** repeat task command. Include failed save → no confirm, stale proposal disabled, undo, zero-member category and refresh during save. Keep the old page functional by instantiating its controller at the page boundary.
- [ ] **Commit only this task’s files:** `refactor: share the teacher skill selection controller`.

### Task 6: Build exact chart datasets, patterns and context requests

**Files:** Create `F/workspace-data.ts`, `F/workspace-context.ts`, `F/__tests__/workspace-data.test.ts`, `F/__tests__/workspace-context.test.ts`, `F/__tests__/teacher-workspace-patterns.json`. Modify `F/types.ts`, `F/__tests__/review-fixtures.ts`.

**Interfaces:** `resolveOnetRating(candidate,occupationCode,metric,release,evidenceId?) -> RatingResolution`; `buildWorkspaceData(review:SkillReview,draft:SelectionDraft,view:WorkspaceViewState) -> WorkspaceData`; `derivePatternObservations(scope:NormalizedWorkspaceScope) -> PatternObservation[]`. Rating union distinguishes reported/missing/suppressed/not-relevant/no-association/ambiguous; reported includes evidence and descriptor identity. Data includes full filtered scope, demand rows, scatter points, heatmap page, table page and observations. `buildRunReviewContext({review,view,dirty,intent,candidateIds?,insightKind?}) -> {ok:true,context:RunReviewContext}|{ok:false,reason:"save_required"|"invalid_context"}`; `removeContextFocus(context:WorkspaceContext) -> WorkspaceContext`.

- [ ] **Write failing selectors/builders tests** and copy Task 2’s corpus byte-for-byte. Both suites compare the same expected observation JSON:

```ts
expect(data.demandRows).toHaveLength(12);
expect(data.tablePage.rows).toHaveLength(25);
expect(data.observations.length).toBeLessThanOrEqual(2);
expect(resolveOnetRating(ambiguous, soc, "IM", release).status).toBe("ambiguous");
expect(removeContextFocus(context).intent).toBe("explain");
expect(buildRunReviewContext(dirtySelectedScope)).toEqual({ok:false,reason:"save_required"});
```

- [ ] **Run red:** `docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/workspace-data.test.ts src/features/market-demand/__tests__/workspace-context.test.ts'`.
- [ ] **Implement pure selectors** using server `job_metrics`, eligible equivalent O*NET associations, matching pinned release and reported finite in-range values. Never aggregate percentages or map broader/software references to numerical importance. Deduplicate evidence IDs; explicit descriptor choice resolves ambiguity. Missing sorts last both ways. Normalize search/labels with Unicode NFKC, trim and lowercase in both languages; category filtering intersects search, then optional local selected scope. Stable ties compare normalized Unicode code points then ID, not locale-sensitive ordering. Add Cyrillic and supplementary-character corpus cases. Keep counts independent of top-12/pagination; clamp page after filtering.
- [ ] **Implement context builders** with IDs/filters only, no client facts/URLs/excerpts. Preserve explicit intent after focus removal, freeze a deep copy at Send, and enforce all shared bounds. A dirty selected-only context or proposal requires save; explain otherwise carries the unsaved notice. No run means reference context only.
- [ ] **Run green:** repeat task command and both-language corpus tests. `cmp backend/tests/fixtures/teacher-workspace-patterns.json frontend/src/features/market-demand/__tests__/teacher-workspace-patterns.json` must exit 0. Test all-zero demand versus unassessed demand, same descriptor across distinct evidence IDs and different descriptor choices across occupations.
- [ ] **Commit only this task’s files:** `feat: derive evidence charts and inspectable patterns`.

### Task 7: Render ECharts and accessible evidence views

**Files:** Create `F/components/EvidenceChart.tsx`, `WorkspaceOverview.tsx`, `WorkspaceCompare.tsx`, `WorkspaceDataTable.tsx`, `F/__tests__/EvidenceChart.test.tsx`, `WorkspaceViews.test.tsx`. Modify `frontend/package.json`, `frontend/package-lock.json`, `F/components/SkillEvidencePanel.tsx` and relevant evidence tests.

**Interfaces:** `EvidenceChart({option,label,className,onFocus,onError?})`; `ChartFocus={candidateId:string,occupationCode?:string,evidenceId?:string}`. View props `{data:WorkspaceData,controller:SkillReviewController,onAsk:(request:WorkspaceQuestion)=>void}`; `WorkspaceQuestion={text:string,candidateIds?:string[],occupationCodes?:string[],insightKind?:PatternObservation["kind"]}`. Question objects contain no source values. Default-export Compare for lazy loading.

- [ ] **Write failing lifecycle/view tests** proving resize/disposal and that bar/cell/pattern interactions stage focus/question without selecting or POSTing:

```ts
expect(onFocus).toHaveBeenCalledWith({candidateId:pythonId});
expect(saveSkillReviewDraft).not.toHaveBeenCalled();
expect(streamMarketDemandChat).not.toHaveBeenCalled();
unmount();
expect(chart.dispose).toHaveBeenCalledTimes(1);
```

- [ ] **Run red:** `docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/EvidenceChart.test.tsx src/features/market-demand/__tests__/WorkspaceViews.test.tsx'`.
- [ ] **Install and implement** with `docker exec lab_tutor_frontend sh -lc 'cd /app && npm install --save-exact echarts'`; retain the resolved version in the lockfile, no router upgrade or wrapper dependency. Register Bar/Scatter/Heatmap, Grid/Dataset/Tooltip/VisualMap/Aria and required renderer through `echarts/core`. Adapter owns init/update/ResizeObserver/listeners/dispose, handles zero-sized/hidden containers and theme changes. Use safe text tooltips and accessible values; no raw source HTML rendering. Container dimensions use Tailwind.
- [ ] **Render** Overview bars and ≤2 cards, fixed scales, explicit occupation/metric controls, 12-row heatmap, 25-row keyboard Data table, row ranges, empty/partial/error states and all unavailable reasons. Zero occupations → empty comparison; one → single-role view; hidden confirmed role can be re-enabled without a new run. Multiple descriptors require choice. Inspector reuses lazy owned posting retrieval, original links, retrieval/availability and rating provenance. Chart failure retains table/shortlist. Compare is lazy-loaded; labels/values work in light/dark mode.
- [ ] **Run green:** repeat task command; save actual chart resize/theme/browser verification for task 12 because jsdom’s ResizeObserver cannot prove it.
- [ ] **Commit only this task’s files:** `feat: add ECharts teacher evidence views`.

### Task 8: Add typed contextual transport and recovery

**Files:** Modify `F/types.ts`, `F/api.ts`, `F/hooks/useAgentStream.ts`, `F/__tests__/api.test.ts`, `F/__tests__/useAgentStream.test.tsx`.

**Interfaces:** `getMarketExecutionStatus(courseId:number,signal?:AbortSignal):Promise<ExecutionStatus>`; `streamMarketDemandChat` takes discriminated workflow/contextual arguments; `MarketDemandApiError` retains `status`, `code`, `message`, `recovery`. Hook `send(command:SendCommand):Promise<SendResult>` where result is completed/failed/detached; `closeLiveResponse():void`, `reconcile():Promise<void>`, `clearConversation():Promise<void>` rejects reset failures. Existing hook configuration remains workflow-only.

- [ ] **Write failing transport/hook tests** for structured 409/422, truncated frames, failure events, EOF without stream_end, detach, stale course generations and failed/partial reset:

```ts
expect(sentBody.workspace_context.intent).toBe("explain");
expect(sentBody).not.toHaveProperty("sources");
expect(sentBody).not.toHaveProperty("country");
expect(result.current.execution.outcome).toBe("unknown"); // EOF without terminal proof
await expect(result.current.clearConversation()).rejects.toThrow();
expect(result.current.skillReview).toEqual(reviewBeforeRejectedReset);
```

- [ ] **Run red:** `docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/api.test.ts src/features/market-demand/__tests__/useAgentStream.test.tsx'`.
- [ ] **Implement** typed context/history/error/outcome transport and terminal tracking, including the `workspace_review` agent identity. Network errors must not silently resolve as success. Preserve source fields only on workflow requests. Resolve history/state/review coherently, retain recoverable failed questions and ignore stale generations. Status polling: visible busy 2 seconds, 10 seconds after 30 seconds; stop idle/hidden/unmount/course change; refresh on visibility return. Idle + no terminal proof stays unknown. Never automatically replay uncertain work. Rejected reset clears nothing; ambiguous reset reconciles authoritative state before another mutation.
- [ ] **Run green:** repeat task command with fake timers for polling and stream fragmentation. Assert polling cannot create runs or acquire execution ownership; late responses cannot replace a new course’s state. Source outcomes determine source success.
- [ ] **Commit only this task’s files:** `feat: connect contextual chat and execution recovery`.

### Task 9: Make conversation controls understandable and stateful

**Files:** Create `F/components/WorkspaceConversation.tsx`, `F/__tests__/WorkspaceConversation.test.tsx`. Modify `F/components/ChatInput.tsx`, `AgentMessage.tsx`, `UserMessage.tsx`, existing message tests and `frontend/src/test/AgentComponents.test.tsx` as required.

**Interfaces:** `ConversationDraft={text:string,command:{mode:"workflow"}|{mode:"contextual",context:WorkspaceContext}}`; `WorkspaceConversation({stream,draft,onDraftChange,onSubmit})`. Controlled ChatInput receives `value`, `onChange`, submission and close-live-response callbacks; page owns draft above responsive panes.

- [ ] **Write failing interaction tests** for editable prefilled questions, removal of focus, frozen submitted context, failed send retention and scroll attention:

```ts
expect(onSubmit).not.toHaveBeenCalled(); // clicking Ask only stages
expect(latestDraft.command.context.intent).toBe("explain");
expect(screen.getByRole("textbox")).toHaveValue(questionAfterFailure);
expect(scrollToBottom).not.toHaveBeenCalled(); // reader scrolled upward
```

- [ ] **Run red:** `docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/WorkspaceConversation.test.tsx src/features/market-demand/__tests__/AgentMessage.test.tsx src/test/AgentComponents.test.tsx'`.
- [ ] **Implement** visible context chip and unsaved notice, simple current-agent/activity line, expandable tool details, safe historical chips and truthful outcome notices. “Close live response” detaches; show continued-work explanation. Preserve typed follow-up text entered while a reply streams. No automatic view switch or forced scroll. “Save draft and suggest” awaits controller save and uses its returned review; render reviewable immutable proposals and apply only to draft.
- [ ] **Run green:** repeat task command. Test busy conversation staging, refresh-context recovery, removed-source evidence and keyboard focus. No chain-of-thought or fake progress percentages.
- [ ] **Commit only this task’s files:** `feat: improve teacher conversation controls`.

### Task 10: Support genuine empty states and O*NET reference exploration

**Files:** Create `F/components/OccupationReferencePanel.tsx`, `F/__tests__/OccupationReferencePanel.test.tsx`. Modify `F/api.ts`, `F/types.ts`, `F/__tests__/api.test.ts`.

**Interfaces:** `getOccupationSkills(courseId:number,release:string,socCode:string,signal?:AbortSignal):Promise<OccupationSkills>` mirrors existing backend response. `OccupationReferencePanel({courseId,onAsk:(context:OccupationReferenceContext,suggestedQuestion:string)=>void})`. Reference items remain `OnetEvidence[]`, never selectable `SkillCandidate` objects.

- [ ] **Write failing tests** for ready release/occupation selection, missing/suppressed/software data, stale responses and a reference question with no run:

```ts
expect(onAsk).toHaveBeenCalledWith(expect.objectContaining({kind:"occupation_reference",intent:"explain"}), expect.any(String));
expect(saveSkillReviewDraft).not.toHaveBeenCalled();
expect(screen.queryByRole("button", {name:"Approve integration"})).toBeNull();
```

- [ ] **Run red:** `docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/OccupationReferencePanel.test.tsx src/features/market-demand/__tests__/api.test.ts'`.
- [ ] **Implement** release/occupation/reference browsing using existing picker conventions and APIs, with attribution and correct IM/LV statuses. Show Start an analysis as primary empty-state action and reference exploration as secondary. Browsing changes no locked collection settings, creates no run and cannot publish. Abort/ignore superseded release/occupation/course requests. Context bounds are identical to the backend.
- [ ] **Run green:** repeat task command; verify empty imported dataset and request errors have retry actions rather than invented data.
- [ ] **Commit only this task’s files:** `feat: add O*NET reference exploration for teachers`.

### Task 11: Assemble the simple workspace and preserve teacher checkpoints

**Files:** Modify `F/pages/MarketDemandPage.tsx`, `frontend/src/App.tsx`, `F/__tests__/MarketDemand.test.tsx`, `MarketDemandConfiguration.test.tsx`, `frontend/src/App.test.tsx`. Create `F/hooks/useWorkspaceNavigationGuard.ts`, `F/__tests__/useWorkspaceNavigationGuard.test.tsx`. Remove `F/components/StatePanel.tsx` and obsolete usages once replaced. Reuse `SelectionPanel`, `PipelineStepper`, source pickers and integration review.

**Interfaces:** Page composes tasks 5–10. `useWorkspaceNavigationGuard({dirty:boolean,save:()=>Promise<SkillReview>})` returns blocked destination and `saveAndLeave`, `discardAndLeave`, `stay` actions. Root exports an application shell preserving current AuthProvider/AppRoutes/Toaster; use a single root `*` Data Router route, retaining existing descendant paths/layouts.

- [ ] **Write failing page/guard tests** for main evidence/right chat, exact available-width breakpoint, coherent draft across narrow tabs, restored source summary and query/job-group confirmations. Dirty link/back navigation has Save/Discard/Cancel; failed save keeps the page.

```ts
expect(confirmQuerySend.mode).toBe("workflow");
expect(ordinaryReviewSend.mode).toBe("contextual");
expect(screen.getByRole("checkbox",{name:/Python/})).toBeChecked(); // after pane switch
expect(resetRequestCount).toBe(0); // cancelling New analysis
expect(currentPath()).toBe(originalPath); // dirty navigation cancelled
```

- [ ] **Run red:** `docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/MarketDemand.test.tsx src/features/market-demand/__tests__/MarketDemandConfiguration.test.tsx src/features/market-demand/__tests__/useWorkspaceNavigationGuard.test.tsx src/App.test.tsx'`.
- [ ] **Compose the page** at its existing URL and hub entry point. Overview default; Compare/Data reveal detail. Keep main/transcript scroll independent, collapse configuration after start, preserve pre-extraction query/group checkpoints and explicit workflow mode. Maintain one review/controller/composer above responsive panes. Base layout on observed content width, not browser width. Keep unread indicator; no auto-switch. No-run/partial/error states use actual API results.
- [ ] **Implement supported navigation protection.** Replace only BrowserRouter shell with RouterProvider/createBrowserRouter root `*` route; retain AppRoutes paths and existing auth/layout behavior. Create the browser router once outside rendering, never nest routers, and keep AuthProvider/Toaster inside AppShell. Use one `useBlocker` above the responsive panes for internal/history navigation and `useBeforeUnload` for reload/close. The browser controls native unload confirmation. Guard tests use a fresh catch-all `createMemoryRouter`, disposed after each test. No popstate monkeypatch or broad routing migration. Test protected routes, deep links and existing non-market routes under the shell.
- [ ] **Implement New analysis** with the existing DELETE history API and precise confirmation: saved evidence/published skills remain; current analysis is no longer resumable here. Save/Discard/Cancel for dirty draft; reset only after save succeeds. Disable known-busy, retain view on 409, reconcile ambiguous partial failure. Clear local state only after acknowledged success; show setup without automatic collection. Keep retry-all-providers/reassessment wording and existing omission acknowledgement before advancing.
- [ ] **Run green:** repeat task command; existing integration-review tests remain green. Verify ordinary questions never lose inspection intent and final approval remains the existing exact mapping/digest action.
- [ ] **Commit only this task’s files:** `feat: assemble the teacher evidence workspace`.

### Task 12: Verify the complete database-backed teacher flow

**Files:** Create `backend/tests/acceptance/teacher_workspace_server.py`, `frontend/e2e/teacher-evidence-workspace.cjs`, and `output/teacher-evidence-workspace/acceptance/index.html` with screenshots/readback evidence during execution. Add an empty `backend/tests/acceptance/__init__.py` if needed. Do not commit credentials, transient browser storage or real posting bodies.

**Interfaces:** Acceptance server module starts the real FastAPI app against a dedicated PostgreSQL database named `lab_tutor_workspace_acceptance`, rejecting any other database name. Its CLI is `python -m tests.acceptance.teacher_workspace_server --port 8000 --manifest /tmp/teacher-workspace.json`. It seeds a disposable course/review/occupation fixture through existing SQL services and installs deterministic external-model/provider doubles; business routes, repositories, checkpointing and approval gates remain real. It exposes no fixture-control endpoints in production. Browser script consumes `WORKSPACE_UI_URL`, `WORKSPACE_API_URL` and a temporary 0600 fixture manifest path supplied through `WORKSPACE_FIXTURE_PATH`.

- [ ] **Build the isolated acceptance fixture and headless script.** Seed a synthetic, clearly labeled test sample: 10 assessed postings, two occupations, shared and differing descriptors, missing/suppressed/ambiguous metrics, 30 candidates, partial provider outcome, saved exclusions and existing student records. Include SQL IDs/expected values in the private manifest and public non-sensitive expected-results file. Import actual small O*NET test fixtures; no production fallback data.
- [ ] **Run acceptance and capture failures before declaring success.** Start one-off backend/frontend Docker services on free loopback ports using the existing images/network and implementation checkout (defaults 18000 for API and 15173 for UI). Override the backend DB and disable external credentials for this fixture; override frontend `VITE_API_URL`. Do not repoint existing app containers. Create a fresh dedicated database; if that name already belongs to another run, wait for its owner to finish rather than truncating or dropping it. The server must wait for health, verify its database and clean up only its own resources. Copy its manifest to a host temporary file with mode 0600. Run `WORKSPACE_UI_URL=http://127.0.0.1:15173 WORKSPACE_API_URL=http://127.0.0.1:18000 WORKSPACE_FIXTURE_PATH=/tmp/teacher-workspace.json node /Users/khajievroma/.codex/skills/playwright-skill/run.js "$PWD/frontend/e2e/teacher-evidence-workspace.cjs"` headlessly; no host frontend dependency installation. Expected success is exit 0 with every scenario assertion below, not merely screenshots.
- [ ] **Exercise A1–A12:** hub/direct route; empty/reference modes; saved SQL values and links; chart focus without writes; descriptor choice and pattern parity; category select + individual exclusion; save/reload; dirty refresh + stale second-tab proposal; contextual explanation/proposal permissions; query/group workflow checkpoints; partial-source acknowledgement; stream failure/detach + unknown outcome; New analysis rejection/partial failure/success; missing-evidence publication rejection; exact approved mapping; unchanged student paths/resources/quiz mastery. Browser assertions compare displayed counts and posted revisions with fresh SQL/API readback.
- [ ] **Verify actual charts and attention** at 1440, 1024, 768, 390 and 320px with app sidebar expanded/collapsed; light/dark; real ResizeObserver; hidden-pane reopening; repeated course/view changes; keyboard table; guarded link/back/reload; conversation scroll and retained composer. Record no runtime errors, no clipped labels/document overflow, no duplicate click handlers and no unintended chat/selection requests. A chart-load failure must leave Data usable.
- [ ] **Run final scoped regression/check commands below.** Fix failures within the task that owns them, then rerun only affected checks plus integration when the fix changes integrated behavior. A passing build alone does not satisfy any scenario above. Live HeadHunter smoke is optional when existing local credentials and provider availability permit it; clearly distinguish controlled real-DB acceptance from live-provider proof.
- [ ] **Write the HTML handoff** with screenshots, scenario results, exact commands, commit range and any material limitation. Remove acceptance fixture data/services and private manifests. Review the complete branch, then commit only acceptance/report files with `test: verify the teacher evidence workspace end to end`. No deployment, merge or student publication outside the isolated acceptance data is part of this plan.

## Final scoped commands and acceptance mapping

Run backend commands serially; all test targets use the explicit test database. Do not substitute host dependency installs if Docker is unavailable.

```sh
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_market_workspace_context.py tests/modules/test_market_workspace_patterns.py tests/modules/test_market_workspace_chat.py tests/modules/test_market_demand.py tests/modules/test_market_demand_thread_state.py tests/modules/test_market_skill_review.py tests/modules/test_market_skill_recommendations.py tests/modules/test_market_vacancy_evidence.py tests/modules/test_market_skill_approval.py tests/modules/test_market_skill_student_access.py tests/modules/occupation_reference/test_routes.py'
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/ruff check . && /app/.venv/bin/ruff format --check .'
docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand src/test/AgentComponents.test.tsx src/App.test.tsx'
docker exec lab_tutor_frontend sh -lc 'cd /app && npm run lint && npm run build'
cmp backend/tests/fixtures/teacher-workspace-patterns.json frontend/src/features/market-demand/__tests__/teacher-workspace-patterns.json
```

| Spec acceptance | Tasks responsible |
| --- | --- |
| A1 Route and agents hub | 11, 12 |
| A2 Real/empty data | 1, 2, 10, 12 |
| A3 Exact chart values | 2, 6, 7, 12 |
| A4 Bounded patterns | 2, 6, 7, 12 |
| A5 Focus versus selection | 5, 7, 9, 12 |
| A6 Revisions/reconciliation | 2, 3, 5, 8, 12 |
| A7 Context/tool permissions | 2, 3, 4, 6, 8, 9, 12 |
| A8 Evidence/provenance | 2, 4, 6, 7, 10, 12 |
| A9 Failure/detachment/reset | 1, 3, 4, 8, 11, 12 |
| A10 Approvals/student regression | 5, 11, 12 |
| A11 Responsive/accessibility | 7, 9, 11, 12 |
| A12 Chart lifecycle | 7, 11, 12 |

## Plan review and execution handoff

This plan changes documentation only until approved for execution. Recommendation: **subagent-driven**, with frontend/backend ownership and a coordinator, because graph permissions, asynchronous recovery and teacher approval depend on several shared contracts. Fresh task reviews should precede the final whole-branch review. Native execution remains an option with the same task/checklist boundaries.

Before implementing, confirm that the plan captures the approved behavior and choose the execution approach. After execution, preserve the usual branch review/merge process; this plan does not authorize deployment.

Planning references: [approved specification](../specs/2026-10-11-teacher-evidence-workspace-design.html), [ECharts modular imports](https://echarts.apache.org/handbook/en/basics/import/), [ECharts accessibility](https://echarts.apache.org/handbook/en/best-practices/aria/), [React Router navigation blocking](https://reactrouter.com/api/hooks/useBlocker), [reload/unload handling](https://reactrouter.com/api/hooks/useBeforeUnload), [supported root catch-all router migration](https://reactrouter.com/6.30.1/upgrading/v6-data#add-routerprovider-with-a-root-splat-route). The graph-entry decision is grounded in the repository’s installed LangGraph/Swarm source, preserving its existing routing semantics.
