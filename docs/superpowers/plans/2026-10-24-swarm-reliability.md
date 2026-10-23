# Swarm reliability implementation plan

Goal: repair both diagnosed failures, exercise parallel saves and repeated calls, and deploy the verified backend. The user later allowed restarting from scratch, so preserving the prior 23 choices is no longer a release requirement.
Architecture: retain current swarm and service/repository structure. Merge chapter results under the SQL lock and synchronize shared state publication. Bound repeated worker tool calls without progress and produce explicit failed/recoverable outcomes.
Spec: approved repair direction in output/swarm-diagnosis-2026-10-24/index.html and user instruction 2026-10-24.

## Constraints and review focus
- Base3574659; backend only; no schema/provider/frontend changes.
- Keep selection and evidence semantics intact. Observe existing selection before/after deployment; no course reset, auto-confirm, publish or live replay is needed for this repair.
- Docker/real PostgreSQL tests; no host installs.
- Parallel saves survive SQL/shared memory completion reordering; same-chapter retry idempotent.
- Repeated successes and validation failures stop boundedly; different arguments/results/progress and new human turns remain valid.
- Backend image-only deployment with protected config and before/after selection comparison.

## Tasks
1. Atomic cleaner accumulation: red regression using parallel ToolNode; service chapter merge using locked latest snapshot; safe memory publication; green concurrency, replacement, finalization and selection-preservation tests.
   Files: backend/app/modules/marketdemandanalyst/{tools.py,review_service.py,repository.py,state.py} as needed; backend/tests/modules/test_market_cleaner_concurrency.py. Interface: chapter-scoped service method, no HTTP contract change.
2. Repeated worker calls: red real-graph tests with scripted repeated read and finalization; minimal current-task/current-worker guard; actionable SSE error and failed outcome; green meaningful-progress/new-turn/handoff tests.
   Files: backend/app/modules/marketdemandanalyst/{graph.py,routes.py}, focused progress module if justified, backend/tests/modules/test_market_worker_progress.py and transport tests. Interface: existing SSE error protocol with specific code.
3. Release: capture exact production selection read-only; run related regressions/Ruff and independent review; commit focused branch; build/test amd64 image from deployed digest; recheck live image/selection; push/deploy only backend; verify health/source hashes and report any selection/evidence changes; HTML handoff with rollback digest.

Progress: worktree /Users/khajievroma/.codex/worktrees/swarm-reliability/lab_tutor on fix/swarm-reliability; implementation and regression coverage complete, final checks/release pending. Review identified an additional stale streaming-snapshot path; intermediate stream saves now capture current state under the same execution lock as durable commits and publication. Coordinator owns deployment and final verification. Backend worker owns backend only.
