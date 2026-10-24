# Chat skill review implementation plan

> Use the existing React components and narrow behavior tests. Frontend worker owns frontend; coordinator owns integration, verification and reporting.

**Goal:** Put the skill chooser in the conversation when a teacher needs it, then collapse it after confirmation. Preserve access through Skills & chart.

**Basis:** User's production screenshot and request on 24 October 2026. The large card currently lives outside the chat scroll area. Existing server state includes `selection_confirmation`, `review_stage`, and revision/selection identifiers, although the frontend type omits them.

**Scope:** Frontend presentation and confirmation lifecycle, plus the mapper response-limit repair authorized by the user's “Fix both” answer. Keep backend authorization, saved choices, evidence acknowledgement, final publication approval and existing component styling. No dependencies or browser-storage confirmation markers. Separate provider outages and the Neo4j book-selection query are diagnosis-only.

- [x] Add narrow regressions for decision controls inside the conversation, immediate collapse after successful confirmation, failure recovery, exact-confirmation restoration, changed-selection reopening and one working confirmation action in Skills & chart.
- [x] Run the regressions against the pre-change behavior in Docker.
- [x] Add typed fields for existing server confirmation metadata; match current run/revisions/IDs before treating restored choices as confirmed.
- [x] Move the decision region into the conversation scroll area and collapse confirmed choices to a compact summary. Preserve existing editing, busy and recovery controls.
- [x] Run the market-demand tests plus frontend lint and build against the isolated checkout in Docker.
- [x] Exercise the page headlessly with deterministic HTTP fixtures: chooser placement, confirmation, stalled mapping, restored confirmed state and reopened editor. Capture desktop/mobile screenshots.
- [x] Review the diff, record limitations and link the HTML report/preview.

**Outcome:** 97 relevant tests passed; after the final keyboard-focus fix, all 44 page tests passed again. Lint and build passed with existing warnings. Final headless checks passed at desktop and mobile sizes, including focus after both confirmation paths. The earlier concurrent full-suite run was inconclusive due to resource timeouts. No production deployment or backend repair. Report and screenshots are in the main checkout's `output/production-logs-2026-10-24/index.html`.

**Review focus:** A saved draft is not confirmation; stale confirmation must not hide new choices; mapping failure must not force re-confirmation or lose choices; drawer and chat must not render competing confirmation buttons; scrolling must free the conversation space shown in the screenshot.

## Backend follow-up

Production evidence: five model responses ended at 4,096 tokens with `finish_reason=length`; JSON stopped around row35–37 of139. The mapper omits an output budget. Keep existing all-candidate validation and persistence checks.

- [x] Add failing request-wire and streamed 139-candidate persistence regressions using real graph, PostgreSQL and existing test graph; isolate the model HTTP boundary.
- [x] Give only the mapper an explicit 32,768-token output budget, preserving provider thinking settings and literal `max_tokens` transport compatibility.
- [x] Reject length-truncated responses before tools execute; expose an actionable error and preserve confirmation. Verify a subsequent user retry is not poisoned by unanswered tool calls.
- [x] Run one bounded synthetic provider probe beyond 4,096 output tokens to verify gateway support without using customer data or workflow state.
- [x] Run targeted backend tests and Ruff inside Docker; review final diff and update HTML report with evidence and remaining limits.

**Backend outcome:** 51 targeted tests pass, including the unchanged seven-chapter workflow at 100 steps. Ruff check/format pass. One live synthetic139-row provider call returned HTTP200, normal tool-call completion, 14,089 output tokens and every expected ID exactly once. Production deployment and a real course workflow replay have not occurred. Separate HTTP522 outages and Neo4j book-query repair remain outside this change.
