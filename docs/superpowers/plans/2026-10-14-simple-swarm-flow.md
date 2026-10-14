# Simple Swarm Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (the user's selected method) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use superpowers:executing-plans only if subagents are unavailable.

**Goal:** Give the teacher one clear decision at a time, with optional compact evidence and O*NET comparisons, while preserving the existing Swarm workflow and saved choices.

**Architecture:** Reuse the current agent stream, SQL review, selection controller, ECharts adapter, evidence API and publication gates. Replace the dashboard presentation at the existing market-analyst route; add no extraction pipeline, database migration or public endpoint. Keep semantic merging and original posting provenance unchanged.

**Tech Stack:** React 19, TypeScript, TailwindCSS v4, existing shadcn components and ECharts 6.1.0; FastAPI/Pydantic/SQLAlchemy, PostgreSQL and the existing LangGraph workflow.

**Spec:** [Archived approved minimal design](../specs/2026-10-14-simple-swarm-flow-approved.html). The original interactive mock is retained locally because it contains provider quotations; the [verified implementation report](../../../output/teacher-evidence-workspace/simple-flow-acceptance/index.html) supplies sanitized screenshots. This plan supersedes the presentation tasks in the 12 October workspace plan. The existing data and safety contracts remain authoritative.

**Status:** Design and implementation plan approved on 14 October 2026; all implementation tasks, independent reviews and authorized production deployment are complete. Exact verification and deployed source identity are recorded in the linked HTML implementation report. Worktree: `/Users/khajievroma/.codex/worktrees/teacher-evidence-workspace/lab_tutor`, branch `feat/teacher-evidence-workspace`, inspected base `b86cdacc185b180731789794ca18990024cf0866`.

## Global Constraints

- “Confirm search terms → Choose job groups → Choose skills → Review curriculum fit.” No additional teacher stage for HeadHunter, O*NET or merging.
- “The main conversation shows at most five chosen or proposed skills at a time.” Show an explicit “Review all N” control when more are selected; never silently drop choices.
- “Selecting a category selects every current member, including other pages and filtered members.” Individual exclusions persist; suggestions never silently undo them.
- “Show at most five labelled bars, one measure and one sentence of interpretation.” Charts open only on request, using ECharts already installed.
- “Keep sample job frequency separate from O*NET importance.” IM uses the reported 1–5 scale for a named occupation/release. A related Programming descriptor is context for SQL, not an official SQL rating. Missing ratings are unavailable, not zero. LV is not student mastery.
- “O*NET’s 394 reference candidates do not enter the job-backed skills checklist.” Counts 58 and 394 describe the current saved sample, not application limits or hardcoded production defaults.
- Preserve every original posting link, label and validated passage in merged skills; count each distinct posting once. Recheck availability before displaying retained posting content.
- “Do not silently acknowledge incomplete evidence, bypass backend review checks, or hide a blocking decision inside optional details.” Missing individual O*NET ratings alone introduce no extra gate.
- At 1280×720 and 1440×900, the current decision and next action fit without main-page scrolling. Optional dialogs and conversation/history may scroll internally. Mobile and keyboard interaction remain usable.
- Preserve course ownership, stale-revision checks, source/configuration locks, dirty navigation, execution recovery, explicit final approval, publication, student APIs, saved learning paths, resources and quiz mastery.
- Use existing `@/` imports, feature API wrappers, Tailwind/`cn()` and existing form conventions. No new dependencies, host app-dependency installation, private teacher data in Git or changes to the dirty primary checkout.

## Review Focus

1. A 58-skill selection with a search filter and off-page category members: bulk selection is complete, exclusions survive reopening and reload (Tasks 2, 6).
2. Related, ambiguous, missing or mixed-release O*NET evidence: no invented SQL score, zero filling, category average or cross-occupation composite (Tasks 1, 4, 6).
3. Multiple quotations/snapshots for one posting, including a later purge or failed refresh: no duplicate cards/counts, lost quotations or stale content disclosure (Tasks 3, 6).
4. A failed save, failed workflow start, double click or revision change: preserve the draft, avoid accidental advancement and require reconciliation when needed (Tasks 2, 5, 6).
5. Partial coverage, existing reference-only exclusions and previously published student work: keep required decisions visible and prevent implicit publication or loss of student records (Tasks 1, 2, 5, 6).

## File map and ownership

Paths below are relative to the worktree. `F` means `frontend/src/features/market-demand`; `B` means `backend/app/modules/marketdemandanalyst`. These abbreviations are file-map notation, not shell variables.

| Task | Files and responsibility |
| --- | --- |
| 1 · Accurate agent advice | Modify `B/review_service.py`, `B/tools.py`, `B/prompts.py`; extend `backend/tests/modules/test_market_skill_review.py` and `test_market_workspace_chat.py`. Explicit evidence counts and concise recommendations. |
| 2 · Skill selection | Modify `F/selection.ts`, `F/hooks/useSkillReviewController.ts`; create `F/components/SkillChoice.tsx`; extend `F/__tests__/review-fixtures.ts`, `selection.test.ts`, `useSkillReviewController.test.tsx`; create `SkillChoice.test.tsx` in that test directory. |
| 3 · Posting inspector | Create `F/posting-evidence.ts`, `F/__tests__/posting-evidence.test.ts`, `F/__tests__/SkillEvidencePanel.test.tsx`; modify `F/components/SkillEvidencePanel.tsx`. Grouped provenance and availability. |
| 4 · O*NET comparison | Create `F/compact-comparison.ts`, `F/components/CompactComparison.tsx`, and matching test files in `F/__tests__/`; reuse `workspace-data.ts`, `workspace-context.ts` and `EvidenceChart.tsx`. |
| 5 · Chat-first flow | Modify `frontend/src/App.tsx`, `F/pages/MarketDemandPage.tsx`, `F/components/WorkspaceConversation.tsx`, `F/components/IntegrationReview.tsx`; create `F/teacher-decision.ts` and its test. Update `frontend/src/App.test.tsx` and the existing MarketDemand, MarketDemandConfiguration, WorkspaceConversation and IntegrationReview tests. Remove old presentation files only if no callers remain. |
| 6 · Acceptance and review | Update `backend/tests/acceptance/teacher_workspace_server.py`, `frontend/e2e/teacher-evidence-workspace.cjs`; add sanitized HTML results under `output/teacher-evidence-workspace/simple-flow-acceptance/`. Coordinator owns integration, verification and reports. |

Task 1 and Task 2 have disjoint backend/frontend ownership and may run concurrently after sharing these contracts. Frontend Tasks 2–5 run sequentially; Task 6 follows integration. No worker may change another worker's files. Preserve the selected subagent-driven execution method; read its review requirements before execution.

## Verification environment

Use `lab_tutor_workspace_backend` and `lab_tutor_workspace_frontend`, whose `/app` mounts were verified to point to this worktree. Use `/Applications/Docker.app/Contents/Resources/bin/docker` if `docker` is absent from PATH. Backend pytest must use `postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test`; never a development or production database. Only one pytest process may use that test database at once. Do not restart or repoint unrelated containers.

For each task: run the new behavioral test red, implement, rerun its targeted command green, inspect `git diff --check`, stage only the files named for that task, inspect the staged diff and commit with the supplied message. Do not use `git add .`. A build alone is not behavior verification.

## Task 1: Give the agent accurate, concise skill advice

**Interfaces:** Add `candidate_advice_summary(review: SkillReview) -> dict` in `B/review_service.py`, where `SkillReview` is the existing Pydantic DTO. It returns the current safe summary plus `evidence_counts: {job_backed_candidates: int, reference_only_candidates: int, unavailable_candidates: int, selected_postings: int | None, assessed_postings: int | None}`. Count job-backed candidates only when `posting_support == "supported"` and at least one qualifying HTTP(S) posting URL exists. Among the remainder, O*NET-associated candidates count as reference-only; others count as unavailable, never as extracted job skills. Keep revision IDs, all candidate metadata and O*NET associations; continue excluding full posting bodies, approval records and recommendations from this tool response. No public API change.

- [x] **Write failing tests** using the existing real-SQL fixtures, seeded with 58 supported candidates, 394 reference-only candidates and seven assessed/selected postings. In `test_candidate_advice_summary_separates_job_skills_from_references`, assert:

```python
assert summary["evidence_counts"] == {
    "job_backed_candidates": 58, "reference_only_candidates": 394, "unavailable_candidates": 0,
    "selected_postings": 7, "assessed_postings": 7,
}
assert len(summary["candidates"]) == 452
assert all("evidence_references" not in c for c in summary["candidates"])
```

Also test zero/unknown coverage without inventing a denominator; an invalid supported candidate without a URL counted as unavailable; wrong run/owner rejection; and read-only O*NET explanation with related Programming IM 3.38, missing ETL and unchanged selection/publication state. Model responses may be controlled; SQL and business services remain real.

- [x] **Run red:** `docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_workspace_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_market_skill_review.py tests/modules/test_market_workspace_chat.py'`. Expect the new summary test to fail for absent counts/helper, not an unavailable database.
- [x] **Implement** the helper and call it from the owned-run branch of `get_skills_by_category()`. Update Supervisor/Skill Finder instructions to present one current decision, no more than five proposed skills, accurate job-backed counts and optional details. Reuse the existing 180-word contextual answer limit, evidence isolation and immutable proposal rules. Require recommendations to distinguish direct/equivalent ratings from broader/related context, name the occupation, respect explicit exclusions and avoid invented category scores. Do not change semantic grouping, extraction state or tools available to Explain turns.
- [x] **Run green:** repeat the task command; run backend Ruff checks shown under final verification. Inspect the actual resolved tool payload and controlled response, not just prompt-string assertions.
- [x] **Commit** only Task 1 files: `fix: distinguish job-backed skills from O*NET reference advice`.

## Task 2: Make skill and category selection compact and complete

**Interfaces:** Export `jobBackedCandidates(review: SkillReview): SkillCandidate[]` from `F/selection.ts`. Reuse `isUsablePostingUrl`, `categorySelectionState` and selection reducers. `SkillChoice` takes `{controller: SkillReviewController, onInspect: (candidateId: string) => void}`. Its main list contains at most five selected/proposed rows; its optional Browse skills dialog has search, ten rows per page and category checkboxes. The controller remains the only draft owner.

- [x] **Write failing tests** in the task's named test files. Extend `review-fixtures.ts` with `largeReviewFixture(): SkillReview`, returning 58 supported candidates plus 394 reference-only candidates, including one saved reference-only exclusion. Pin these interaction assertions:

```typescript
expect(jobBackedCandidates(review)).toHaveLength(58);
// Select a category while search shows one member; all 12 eligible members count.
expect(controller.draft.selected_candidate_ids).toHaveLength(12);
// Uncheck one member on another page, close and reopen the chooser.
expect(controller.draft.selected_candidate_ids).toHaveLength(11);
expect(controller.draft.excluded_candidate_ids).toContain(excludedMemberId);
expect(controller.draft.excluded_candidate_ids).toContain(referenceExclusionId);
expect(categorySelectionState(memberIds, controller.draft.selected_candidate_ids)).toBe("indeterminate");
```

Also test zero selections, 58 selected with “Review all 58”, no silent recommendation acceptance, explicit exclusion surviving an add proposal, failed save with retained draft, and a formerly selected skill losing valid posting evidence. That last choice must be surfaced for review, not silently removed or made invisible.

- [x] **Run red:** `docker exec lab_tutor_workspace_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/selection.test.ts src/features/market-demand/__tests__/useSkillReviewController.test.tsx src/features/market-demand/__tests__/SkillChoice.test.tsx'`. Expect missing component/helper or wrong membership assertions.
- [x] **Implement** the helper and component with existing checkbox/dialog/input/button primitives. Change `setCategory` to operate on all eligible members before search/pagination; preserve unrelated saved exclusions. Keep candidate order stable by name/ID and saved choices as-is. Show proposals as proposals, with explicit Apply actions through `controller.applyProposal`. Surface unsupported saved choices as a required current review. Retain controller revision reconciliation, undo and request-generation protection; do not add duplicate selection state.
- [x] **Run green:** repeat the task command. Include keyboard category toggling, mixed state, Escape/focus return and save-response reconciliation.
- [x] **Commit** only Task 2 files: `feat: add compact skill selection with complete category choices`.

## Task 3: Show every merged skill's original evidence clearly

**Interfaces:** Export `groupPostingEvidence(candidate: SkillCandidate): PostingEvidenceGroup[]` from `F/posting-evidence.ts`. Each group has `key: string`, `originalUrls: string[]`, `snapshotIds: string[]` and `references: VacancyEvidenceReference[]`. Group references sharing the same snapshot identity or the same provider and exact stored original URL; union those identities transitively. Do not strip URL parameters or infer identity from job titles. Keep link-only qualifying evidence as a provenance-only group. Extend `SkillEvidencePanel` with optional controlled `open`/`onOpenChange` dialog props while retaining existing callers until Task 5.

- [x] **Write failing tests** for `groups_two_quotes_and_two_snapshots_under_one_posting` and `rechecks_before_revealing_content_after_reopen`. Use five references over four distinct postings, including Create ETL and Develop ETL/ELT original labels:

```typescript
expect(groupPostingEvidence(candidate)).toHaveLength(4);
expect(groupPostingEvidence(candidate).flatMap(group => group.references)).toHaveLength(5);
expect(screen.getAllByRole("link", {name: /Original posting/})).toHaveLength(4);
// A snapshot purged after closing must not reveal its old quotation on reopen.
expect(screen.queryByText(purgedQuote)).not.toBeInTheDocument();
```

Also exercise duplicate identical references, distinct same-offset passages in different snapshots, safe hostile text/URLs, fetch failure, cancellation/course change and a link without retained content. Deduplicate only identical quotation identities; retain every distinct validated passage.

- [x] **Run red:** `docker exec lab_tutor_workspace_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/posting-evidence.test.ts src/features/market-demand/__tests__/SkillEvidencePanel.test.tsx'`. Expect duplicate cards or absent grouped inspector behavior.
- [x] **Implement** one card per posting with all its quotations. On opening, fetch each distinct snapshot once using `fetchPostingEvidence`, at most three concurrent requests, and discard bodies on close. Reveal a quotation only after its own snapshot passes current availability checks. Key passages by snapshot/kind/phrase/offsets/excerpt, not snapshot alone. Use fetched title/employer when available and posting-ID fallback while unavailable. Use chevrons for opening in-app evidence, external arrows for original links, expandable descriptions/provider data and retained provenance for unavailable content.
- [x] **Run green:** repeat the task command. Verify four unique external links, both ETL labels, no repeated React keys and no retained content leaking after purge.
- [x] **Commit** only Task 3 files: `fix: group merged skill evidence by original posting`.

## Task 4: Add one small comparison, including O*NET importance

**Interfaces:** `buildCompactComparison(review: SkillReview, candidateIds: string[], metric: "frequency" | "IM", occupationCode: string | null, descriptorChoices: DescriptorChoice[] = []): CompactComparisonModel` lives in `F/compact-comparison.ts`. Export its model: `metric: "frequency" | "IM"`, `occupation: AnalysisOccupation | null`, `release: string | null`, `scale: [number, number] | null`, `rows: CompactComparisonRow[]` and `insight: string`. Each row has `candidateIds: string[]`, `evidenceIds: string[]`, `label: string`, `value: number | null`, `status: string`, `mappings: {candidateId: string; relation: OnetAssociation["relation"]}[]`, `sourceUrl: string | null`. The separate React `CompactComparison` component accepts `{review: SkillReview, candidateIds: string[], open: boolean, onOpenChange: (open: boolean) => void, onAsk: (question: WorkspaceQuestion, descriptorChoices?: DescriptorChoice[]) => void}`. Preserve each candidate's relation when several candidates share a descriptor; frequency rows have empty mappings.

- [x] **Write failing tests** using SQL with related Programming IM 3.38 for Database Architects, ETL with no rating, an equivalent descriptor rated 4.2, two conflicting descriptors, a suppressed value and a different release. Assert:

```typescript
expect(programmingRow.label).toBe("Programming — related to SQL");
expect(programmingRow.value).toBe(3.38);
expect(programmingRow.mappings).toEqual([{candidateId: sql.candidate_id, relation: "related"}]);
expect(etlRow.value).toBeNull();
expect(model.scale).toEqual([1, 5]);
expect(model.occupation?.title).toBe("Database Architects");
expect(resolveOnetRating(sql, occupationCode, "IM", release).status).toBe("no_association");
```

Also assert equal 4/7 demand values produce a factual tie, an unknown denominator never becomes 0%, changing the occupation never borrows another rating, different-release data is excluded, numeric software flags are not IM, mixed relations on one descriptor retain their individual labels, and five visible entries are labelled “5 of N” when more comparisons exist. Related context must never become an equivalent candidate rating.

- [x] **Run red:** `docker exec lab_tutor_workspace_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/compact-comparison.test.ts src/features/market-demand/__tests__/CompactComparison.test.tsx src/features/market-demand/__tests__/workspace-data.test.ts src/features/market-demand/__tests__/EvidenceChart.test.tsx'`. Expect the new model/component tests to fail.
- [x] **Implement** a lazy optional “Compare skills” dialog. Offer “Collected jobs” and “O*NET importance”; show one confirmed occupation and one stored release at a time. Default to the current selected skills, with comparison pagination in groups of five. Reuse the ECharts SVG adapter with a labelled accessible value list and text fallback. Job frequency uses stored counts/coverage. O*NET bars represent official descriptors: keep `resolveOnetRating` equivalent-only; a separate context path may show related/broader descriptors with that relation in the bar label. Do not rank SQL numerically using related Programming, average category ratings or combine occupations. Deduplicate shared descriptors and associate all relevant candidate IDs. Require a descriptor choice for ambiguous matches; render unavailable/suppressed/not-relevant entries as text, never zero-height numeric bars. IM axis shows the original scale; source, release and context remain readable. LV stays optional evidence detail, outside this small chart. Ask the agent carries exact candidate/occupation/descriptor context into the existing read-only explanation path and never changes selection.
- [x] **Run green:** repeat the task command. Assert no chart instance before opening, safe tooltips, disposal, keyboard controls, chart-load fallback and no POST from a bar/measure/occupation click. Display one factual sentence; avoid a market-wide conclusion from seven postings.
- [x] **Commit** only Task 4 files: `feat: add compact job evidence and O*NET importance comparison`.

## Task 5: Restore the four simple teacher decisions

**Interfaces:** Extract existing search-term/job-group detection into `F/teacher-decision.ts`, preserving exact group names. Export `resolveTeacherDecision(state: AgentState, messages: ChatMessage[], review: SkillReview | null): "search_queries" | "job_groups" | "skills" | "curriculum" | "working"`. Preserve the existing pending search/group priority; otherwise a current integration review means curriculum, current candidates mean skills, and no ready choice means working. The page overrides a ready decision with working while an explicit workflow request is active, and rejects reviews from a different run. Unresolved review/coverage decisions are overlays of the current decision, not new workflow stages. Extend `WorkspaceConversation` props with `decision?: ReactNode`, `historyOpen?: boolean`, `onHistoryOpenChange?: (open: boolean) => void`; keep its existing stream/draft/submit/controller contract. The page owns one dialog at a time and one primary decision action.

- [x] **Write failing tests** in the named page/conversation/integration/App tests and `teacher-decision.test.ts`. Pin these behavior sequences:

```typescript
expect(visibleSkillRows).toHaveLength(5);
expect(screen.getByRole("button", {name: "Review all 58"})).toBeVisible();
// A failed save: no confirmation, no mapping command, no approval.
expect(confirmSkillReviewSelection).not.toHaveBeenCalled();
expect(send).not.toHaveBeenCalled();
expect(approveSkillIntegration).not.toHaveBeenCalled();
// A successful Continue: save -> confirm -> explicit workflow mapping request.
expect(callOrder).toEqual(["save", "confirm", "mapping-request"]);
```

Also test exact-name job-group submission and failed-send retry; double-click single flight; detached execution requiring reconcile before retry; draft typed while streaming; stale revision; dirty navigation; zero/all-58 choices; late review after course switch; mandatory coverage and reconciliation decisions; reference-only saved exclusion preserved; and final approval still requiring digest, matching IDs, valid links and acknowledged omissions.

- [x] **Run red:** `docker exec lab_tutor_workspace_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/teacher-decision.test.ts src/features/market-demand/__tests__/MarketDemand.test.tsx src/features/market-demand/__tests__/MarketDemandConfiguration.test.tsx src/features/market-demand/__tests__/WorkspaceConversation.test.tsx src/features/market-demand/__tests__/IntegrationReview.test.tsx src/App.test.tsx'`. Expect old dashboard/default layout and advancement behavior assertions to fail.
- [x] **Implement** the focused route using the existing `ProtectedRoute withDashboardLayout={false}` for `/courses/:id/market-analyst` only. Add a course backlink and existing theme control; keep ordinary course navigation elsewhere. Page uses `h-dvh`, bounded conversation space and an anchored composer/action; show the most recent agent exchange/current decision, with full history behind the small step label. Setup/source status/diagnostics live there too, except actionable errors/gates remain visible. Render Task 2–4 components only when relevant. Keep source/occupation configuration locks and explicit retries. Long terms/groups/mappings use the same five-row summary plus an optional ten-row-paged review dialog.
- [x] **Wire existing guarded actions:** skill Continue calls `controller.reviewMappings()` (saves dirty draft and confirms) and then sends an explicit mapping workflow command. Do not advance from optimistic local confirmation. On failed/unknown workflow start, reconcile execution first and expose one retry; never automatically retry a possible running job. Coverage acknowledgement has its own plainly labelled current action: save first if dirty, then call `acknowledgeAvailableEvidence`; do not hide it inside Continue. Reconciliation requires explicit teacher review. Final stage keeps `IntegrationReview` approval/digest checks, all targets available through Review all, and the distinct primary label “Approve and publish”. Ordinary chat defaults to Explain; proposing changes is an explicit action with immutable suggestions. Hide technical IDs in details; retain meaningful error/recovery controls. Remove unused old dashboard-only components/tests after checking callers, preserving the ECharts adapter, shared rating/context helpers and guards.
- [x] **Run green:** repeat the task command; run `useWorkspaceNavigationGuard.test.tsx` and `useAgentStream.test.tsx` as targeted integration regressions. Verify no calls to approval/publication from Continue, chart inspection, category selection or an explanation. Confirm the no-O*NET-rating case has no extra checkpoint while actual partial source coverage still does.
- [x] **Commit** only Task 5 files and any proven-unused presentation files: `feat: restore the chat-first teacher decision flow`.

## Task 6: Verify the real flow and iterate with a fresh reviewer

**Interfaces:** Keep the existing real-DB acceptance server CLI and private 0600 manifest. Add its test-only `--action seed-simple-flow` and browser `WORKSPACE_SCENARIO=simple-flow`; update `all` orchestration to use the new UI while retaining applicable ownership, context, provenance, recovery and student-preservation scenarios. No fixture-control production endpoints or browser-response mocks.

- [x] **Write the failing acceptance scenario** using 58 supported candidates plus 394 reference-only rows, saved SQL/ETL choices, one reference exclusion, four links per example and multiple quotations on one posting. Use a dedicated fixture course; do not overwrite the actual Big Data course. Exercise the full four-decision flow and assert SQL readback:

```javascript
assert.equal(jobBackedIds.length, 58);
assert.equal(new Set(etlOriginalLinks).size, 4);
assert.deepEqual(afterReload.selected_candidate_ids, savedSelectionIds);
assert(afterReload.excluded_candidate_ids.includes(referenceExclusionId));
assert.equal(beforeExplicitApproval.publication_revision, 0);
assert.deepEqual(studentPathsAfter, studentPathsBefore);
assert.deepEqual(studentResourcesAfter, studentResourcesBefore);
assert.deepEqual(studentMasteryAfter, studentMasteryBefore);
```

Include a blocked/save-failed request through controlled server conditions, partial coverage acknowledgement, revised candidates, multi-page category exclusion, all-58 selection, evidence purge, chart import failure and explicit final approval in the disposable fixture only. Reuse semantic tests proving Create ETL / Develop ETL/ELT merge while every original link/validated passage survives; do not rewrite the deployed algorithm.

- [x] **Run red in an isolated environment:** reuse existing acceptance images/network and this worktree on free loopback ports (defaults UI 15173/API 18000), database `lab_tutor_workspace_acceptance`. Before starting, verify no other run owns that database/ports; never truncate another run's database. The existing server refuses other DB names. Run it with `python -m tests.acceptance.teacher_workspace_server --port 8000 --manifest /tmp/teacher-workspace.json` inside the acceptance API container. Disable external provider credentials for fixtures. Copy the 0600 manifest to a temporary host path. Then run `WORKSPACE_UI_URL=http://127.0.0.1:15173 WORKSPACE_API_URL=http://127.0.0.1:18000 WORKSPACE_FIXTURE_PATH=/tmp/teacher-workspace.json WORKSPACE_SCENARIO=simple-flow node /Users/khajievroma/.codex/skills/playwright-skill/run.js "$PWD/frontend/e2e/teacher-evidence-workspace.cjs"`. Expect new UI/fixture assertions to fail until the harness and app agree; do not accept screenshots alone.
- [x] **Complete fixtures and the integrated checks** without weakening expectations. Capture fresh headless pages at 1280×720, 1440×900, 1024×768, 390×844 and 320×667; test keyboard and light/dark. Assert no main-page scrolling on the two required desktop sizes, next action visible, no clipped labels/overflow/errors, all evidence inspectable, real ECharts SVG interaction, retained drafts and no unintended mutations. Verify controlled SQL publication only after explicit fixture approval and saved student paths/resources/mastery unchanged.
- [x] **Run green and final checks:** rerun the corrected acceptance scenario, applicable preserved acceptance scenarios and the final commands below. Resolve only failures caused by this work; record any pre-existing limitation precisely. No automatic live-source recollection or teacher-course publication as a test shortcut.
- [x] **Run the requested fresh-context simplicity review.** Give a fresh agent only the approved design, the running test URL/fixture instructions and observed screenshots, not earlier scores or rationales. Ask it to complete the teacher tasks and rate clarity, clicks, scrolling and density. Fix concrete findings, rerun affected checks, then request a fresh recheck until no material simplicity problem remains. Treat the earlier mock's 9/10 as a mock result, not an acceptance target that overrides findings. Coordinator verifies the final diff and writes an HTML report with screenshot links, counts, tests and limitations.
- [x] **Commit** only the two acceptance source files and sanitized report assets intended for Git: `test: verify the simple teacher flow with complete skill evidence`. Keep private teacher screenshots, credentials, original posting bodies and runtime receipts out of Git. Follow the existing authorized feature-branch/PR deployment workflow only after review and verification; preserve Azure settings and verify deployed source/image identities. Do not merge the divergent main branch or publish the actual teacher course implicitly. Reuse the existing Big Data draft for read-only post-deploy inspection; retain its 38 documents and saved choices.

## Final verification and handoff

Run once on the integrated change, then repeat only checks affected by subsequent fixes:

```bash
docker exec lab_tutor_workspace_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand src/App.test.tsx src/test/AgentComponents.test.tsx'
docker exec lab_tutor_workspace_frontend sh -lc 'cd /app && npm run lint && npm run build'
docker exec -e LAB_TUTOR_DATABASE_URL="postgresql://labtutor:labtutor@lab_tutor_postgres:5432/lab_tutor_test" lab_tutor_workspace_backend sh -lc 'cd /app && /app/.venv/bin/python -m pytest -v tests/modules/test_market_skill_review.py tests/modules/test_market_workspace_chat.py tests/modules/test_market_semantic_merge.py tests/modules/test_market_skill_evidence.py tests/modules/test_market_skill_approval.py tests/modules/test_market_skill_student_access.py'
docker exec lab_tutor_workspace_backend sh -lc 'cd /app && /app/.venv/bin/ruff check . && /app/.venv/bin/ruff format --check .'
git diff --check
```

Coverage map: complete selection and exclusions → Task 2 + real-SQL Task 6; all original links and semantic continuity → Task 3 + semantic regressions; trustworthy O*NET and compact ECharts → Tasks 1/4 + browser Task 6; four checkpoints, recovery and explicit publication → Task 5 + Task 6; responsive simplicity and fresh review → Task 6. Build/lint are additional checks, not substitutes.

Self-review completed against the approved design: requirements mapped, shared signatures defined, five failure classes assigned tests, deployment/student boundaries retained. The user-facing HTML companion foregrounds the simple flow and O*NET behavior; this file is the technical execution record. The user approved this plan on 14 October 2026. Preserve the selected subagent-driven method during implementation.
