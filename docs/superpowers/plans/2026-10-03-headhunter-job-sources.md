# HeadHunter and Teacher-Selected Job Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teachers select the job sources used by the swarm, including a separate HeadHunter integration for Uzbekistan.

**Architecture:** Keep HeadHunter HTTP/API logic in its own provider. A market-demand source service adapts both that provider and JobSpy into the existing posting shape. Request-scoped tool state, ordered PostgreSQL snapshots, and execution guards protect each teacher/course conversation.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, HTTPX, LangChain/LangGraph, SQLAlchemy/PostgreSQL; React 19, TypeScript, existing Shadcn/Tailwind components, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-03-headhunter-job-sources-design.md`

**Status:** Ready for written-plan review. Execution method already requested by the user: sub-agent TDD.

## Global Constraints

- “Its API logic stays separate from the existing Indeed and LinkedIn JobSpy integration.”
- “No new relational table or Neo4j schema is required.”
- “Stable source identifiers are `indeed`, `linkedin`, and `headhunter`.”
- “HeadHunter supports Uzbekistan in this release” and searches `host=hh.uz`, area `97`.
- “Use existing defaults of 15 requested results per selected source/query and a 72-hour recency window.”
- “Continue the existing 4,000-character extraction input limit.”
- “A failing selected provider must never trigger an unselected fallback.”
- “Run tests inside existing Docker containers.”
- Preserve all unrelated WIP, including book-selection changes and dependency locks. Add no dependencies or host installations.
- Use `@/` frontend imports, existing feature API wrappers, local React state, Tailwind v4 and `cn()`. Use react-hook-form/zod if adding a form.
- Backend queries belong in a repository; routes obtain services through `Depends()`.
- Keep HeadHunter live access unconfigured until provider approval covers Lab Tutor's stored vacancies, normalization, derived skills, configured LLM use, and any required retention/archival controls. A working token alone is insufficient; synthetic automated tests remain independent of approval.
- Serialize backend PostgreSQL test runs across agents: shared fixtures truncate the test database.
- Commit only task-owned files; do not stage all changes. Never commit to main.

## Review Focus

1. A provider returns an HTML login/error page with HTTP 200: report malformed provider data and keep other selected sources (Tasks 3–4).
2. A teacher reopens fetched HeadHunter jobs after its token was removed: allow continued analysis of existing jobs; show source configuration status without blocking every chat turn (Tasks 4–6).
3. An old course/catalog response arrives after switching course or country: ignore it and keep the new course's choices (Tasks 5–6).
4. Duplicate queries and missing employer/detail fields must not create duplicate postings or visible “None” values (Tasks 3–4).
5. A disconnected stream's synchronous tool finishes after a new run starts: its late changes must not overwrite or persist into the new run (Task 2).

---

## Workspace and verification setup

Current feature branch: `feat/headhunter-job-sources`. The current checkout has unrelated WIP and is already mounted into running local Docker containers. Recommend working in place with disjoint ownership and focused commits; an isolated worktree is optional and must be explicitly selected before creation. Do not copy, reset, stash, or commit unrelated WIP.

Coordinator owns root docs, example environment, credential setup, integration, and final review. Backend workers own only `backend/`; frontend workers own only `frontend/`. Use fresh task implementers and reviewers per the chosen Superpowers workflow. Frontend Tasks 5–6 may proceed alongside backend Tasks 2–4 after Task 1 fixes the shared contract. Do not run two backend DB test suites together.

Baseline already recorded before feature code: 60 market-demand pytest tests passed, and targeted backend Ruff passed. Previous local setup also passed frontend lint/build and 267 frontend tests. Rerun the relevant checks after feature changes.

Docker executable: `/Applications/Docker.app/Contents/Resources/bin/docker`. Define this test helper in the executing shell so test credentials come from the existing container, are never printed, and live external services are disabled:

```bash
backend_pytest() {
  /Applications/Docker.app/Contents/Resources/bin/docker exec -e PYTHONPATH=/app lab_tutor_backend /app/.venv/bin/python -c 'import os,subprocess,sys; from urllib.parse import urlsplit,urlunsplit; env=os.environ.copy(); url=urlsplit(env["LAB_TUTOR_DATABASE_URL"]); assert url.hostname=="lab_tutor_postgres"; env["LAB_TUTOR_DATABASE_URL"]=urlunsplit(url._replace(path="/lab_tutor_test")); env["LAB_TUTOR_NEO4J_URI"]=""; env["LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING"]=""; env["LANGSMITH_TRACING"]="false"; env["LANGCHAIN_TRACING_V2"]="false"; sys.exit(subprocess.run([sys.executable,"-m","pytest",*sys.argv[1:]],env=env,cwd="/app").returncode)' "$@"
}
```

Use `lab_tutor_frontend` for all frontend verification. No Docker image rebuild is required for source edits using the current bind mounts.

## Shared contract

- Chat request: `{message: string, country?: string, sources?: JobSource[]}`.
- Source catalog: `GET /courses/{course_id}/market-demand/sources?country=Uzbekistan` returns a JSON array of `{id, label, availability, reason}`.
- Availability: `available | unsupported_country | not_configured`; `reason: string | null`.
- State additions: `job_search_sources: JobSource[]`, `job_source_results: Partial<Record<JobSource, SourceOutcome>>`.
- SourceOutcome: `{status: "success" | "empty" | "partial" | "error", count: number, warnings: string[]}`.
- Unknown/empty supplied sources: HTTP 422. Duplicates canonicalize in stable order `indeed, linkedin, headhunter`.
- Unsupported market/source pair: HTTP 400. Changed configuration after fetched jobs, or overlapping same-thread execution/delete: HTTP 409.
- Omitted sources preserve saved choices; legacy snapshots default to Indeed + LinkedIn. No new SSE event names.
- JobPosting retains `title, company, description, url, site, search_term, country, location`; add nullable `source_job_id`.
- Country records gain canonical `key`; retain `jobspy_country` for supported markets and make it nullable for Uzbekistan. Consumers storing market state use `key`.
- Runtime HeadHunter configuration: `LAB_TUTOR_HH_USER_AGENT`, `LAB_TUTOR_HH_ACCESS_TOKEN`.

## Task 1: Source/country contract and catalog

**Owner:** Backend worker.

**Files:**
- Create `backend/app/modules/marketdemandanalyst/schemas.py` and `job_sources.py`.
- Modify `backend/app/modules/marketdemandanalyst/countries.py`, `routes.py`, and `backend/app/core/settings.py`.
- Create `backend/tests/modules/test_market_demand_sources.py`.

**Interfaces:**
- `JobSource = Literal["indeed", "linkedin", "headhunter"]`; Pydantic `JobSourceOption` and `SourceOutcome`; TypedDict `JobPosting`.
- `normalize_job_sources(raw: Sequence[str] | None) -> tuple[JobSource, ...]`.
- `JobSourceService.catalog(country: JobSearchCountry) -> list[JobSourceOption]`.
- `JobSourceService.validate_compatibility(country: JobSearchCountry, sources: tuple[JobSource, ...]) -> None`, raising `ValueError` for unsupported pairs.
- `get_job_source_service() -> JobSourceService` is the route dependency. The service reads settings and performs no HTTP in its catalog.
- Settings: `hh_user_agent: str | None` and `hh_access_token: SecretStr | None`.

- [ ] Write failing tests: `test_uzbekistan_has_no_jobspy_country` asserts canonical key `Uzbekistan` and no JobSpy enum; `test_catalog_requires_owned_teacher_course`; `test_catalog_uzbekistan_availability` asserts Indeed unsupported, LinkedIn available, HeadHunter not configured without both settings; `test_normalize_sources_rejects_empty_unknown_and_deduplicates` asserts duplicates do not create extra invocations.
- [ ] Run `backend_pytest tests/modules/test_market_demand_sources.py -q`; confirm failure comes from missing feature behavior.
- [ ] Implement the declared types, registry values/labels, country aliases `UZ`, `Uzbekistan`, `O‘zbekiston`, and the teacher-owned catalog endpoint. Existing countries retain their current JobSpy values. HeadHunter is available only for Uzbekistan with both nonblank settings. No network probes in this endpoint.
- [ ] Rerun that file and existing country tests: `backend_pytest tests/modules/test_market_demand_sources.py tests/modules/test_market_demand.py::TestJobSearchCountries -q`. Review JSON shapes against the shared contract.
- [ ] Commit only this task's files after checks; send coordinator the frozen contract and output.

## Task 2: Isolated conversations and ordered persistence

**Owner:** Fresh backend worker; depends on Task 1's schema, not on HeadHunter HTTP code.

**Files:**
- Modify `backend/app/modules/marketdemandanalyst/state.py` and `routes.py`.
- Create `backend/app/modules/marketdemandanalyst/repository.py` and `thread_state_service.py`.
- Modify `backend/tests/modules/test_market_demand.py`; create `backend/tests/modules/test_market_demand_thread_state.py`. Change shared conftest only if a reusable fixture is necessary.

**Interfaces:**
- `bind_tool_store(state: dict[str, Any]) -> ContextManager[dict[str, Any]]`; existing `tool_store` imports expose a MutableMapping backed by a ContextVar. Unbound access fails clearly.
- `snapshot_state() -> dict[str, Any]` and `restore_state(state_json: dict[str, Any]) -> None` deep-copy nested values.
- `ThreadStateRepository(session_factory)` exposes async `load(thread_id) -> dict | None`, `save(thread_id, state) -> None`, `delete(thread_id) -> None`.
- `ThreadStateService(repository)` exposes `claim(thread_id) -> ThreadRun`, `release(run) -> None`, and async `load/save/delete` with detached cache values. Busy claims raise `ThreadBusyError`.
- `ThreadRun` carries thread ID, a fresh state dictionary, and whether it still accepts persistence. Use the same dictionary in endpoint setup and the managed streaming iterator.

- [ ] Write failing tests named `test_distinct_streams_and_state_reads_are_isolated`, `test_same_thread_chat_and_delete_conflict`, `test_disconnect_releases_guard_and_late_tool_cannot_persist`, `test_snapshot_writes_are_ordered_and_clear_stays_deleted`, `test_nested_snapshot_values_are_detached`, and `test_sync_toolnode_preserves_bound_context`. Use asyncio/threading Event barriers and independent real PostgreSQL sessions per request, not sleeps or mocked DB.
- [ ] Run `backend_pytest tests/modules/test_market_demand_thread_state.py -q`; identify actual shared-state/race failures before replacing the store.
- [ ] Implement the proxy/binding and move only the existing thread snapshot SQL into the repository. Replace fire-and-forget saves with awaited ordered saves. Claim before load/restore; release on setup failure, stream completion, and disconnect. Bind state independently for state/history reads; deletion clears only its own thread. Cancel and await the producer, discard cancelled-run mutations, and persist only the last accepted detached snapshot before releasing. Do not change Neo4j writes or terminal chat behavior.
- [ ] Update old HTTP tests to inspect returned/persisted state rather than the ambient store; direct-tool tests bind their own dictionary. Run `backend_pytest tests/modules/test_market_demand_thread_state.py tests/modules/test_market_demand.py -q`. Verify a busy delete cannot erase another stream and that guard release survives failed setup.
- [ ] Commit only Task 2 files; reviewer must inspect cancellation/guard lifetime and real DB test evidence before Task 4 integration.

## Task 3: Dedicated HeadHunter provider

**Owner:** Fresh backend worker. May be developed after Task 2 or independently without touching its files.

**Files:**
- Create `backend/app/providers/headhunter.py`.
- Create `backend/tests/providers/test_headhunter.py`.

**Interfaces:**
- `HeadHunterService(*, client: httpx.Client, user_agent: str, access_token: str)`.
- `search_jobs(search_term: str, *, area_id: str, results_wanted: int, hours_old: int = 72) -> HeadHunterSearchResult`.
- `HeadHunterVacancy` contains `id: str`, `title: str`, `company: str`, `description: str`, `url: str`, `location: str`, and `skill_tags: list[str]`.
- `HeadHunterSearchResult` contains `jobs: list[HeadHunterVacancy]`, `warnings: list[str]`, and `error: str | None`; all errors/warnings are safe user-facing strings.
- `html_to_text(value: str) -> str` preserves readable Unicode text and paragraph/list boundaries; skip script/style content.
- Pydantic records for page/items/detail, area, employer, and skill tags ignore unused vendor fields. Detail employer may be null; blank/missing skill-tag names are ignored.

- [ ] Write MockTransport tests: `test_search_fetches_full_details_with_correct_headers_and_market` asserts host `hh.uz`, area `97`, page 0, requested cap 15, bearer and HH-User-Agent headers, and UTC lower bound 72 hours ago without `period`; `test_multilingual_html_normalization`; `test_missing_employer_uses_search_company_and_repeated_ids_fetch_once`; `test_html_200_or_malformed_json_is_safe_error`; `test_detail_404_is_partial_and_forbidden_stops_details`; `test_retry_budget_and_large_retry_after`.
- [ ] Run `backend_pytest tests/providers/test_headhunter.py -q`; verify missing provider/normalization behavior causes failure.
- [ ] Implement the injected synchronous HTTPX provider, using existing dependencies and standard-library HTML parsing. Send integer pagination, per_page at most 100, depth at most 2000, and stop at the requested result cap or exhausted pages. Validate results_wanted 1–100 and nonblank query. Use timeout 15 seconds/connect 5 seconds, at most three attempts for transport/429/500/502/503/504, and at most five seconds total retry delay per request. Honor Retry-After within that budget; fail if it demands more. Stop on 400/401/403 and malformed 200; skip detail 404 with a warning. Preserve usable details before terminal failure. Never log token/raw response/request data.
- [ ] Rerun provider tests. Test headers with synthetic tokens only; real credentials are never fixtures. Verify alternate_url, full description, nullable employer, and repeated IDs with behavior assertions.
- [ ] Commit only provider/test files; reviewer checks that API logic remains separate from JobSpy.

## Task 4: Enforce teacher selection through the swarm

**Owner:** Fresh backend worker; depends on Tasks 1–3.

**Files:**
- Modify `job_sources.py`, `schemas.py`, `tools.py`, `routes.py`, `state.py`, and `prompts.py` under `backend/app/modules/marketdemandanalyst/`.
- Extend `backend/tests/modules/test_market_demand_sources.py` and `test_market_demand.py`; add `test_market_demand_source_flow.py`.

**Interfaces:**
- `JobSourceService.fetch(*, search_terms: Sequence[str], country: JobSearchCountry, sources: tuple[JobSource, ...], results_per_source: int = 15) -> FetchJobsResult`.
- `FetchJobsResult` contains `jobs: list[JobPosting]` and `outcomes: dict[JobSource, SourceOutcome]`.
- ChatRequest gains optional nonempty `sources`; existing stream/state/history contracts remain.
- `fetch_jobs` retains its existing search-term/result signature and grouped text return. No sources override is exposed to the model.

- [ ] Write failing tests: `test_only_selected_provider_is_called` uses fail-on-call unselected adapters; `test_no_unselected_fallback_after_error`; `test_uzbek_linkedin_omits_unsupported_indeed_country`; `test_partial_failure_preserves_jobs_and_safe_outcomes`; `test_legacy_sources_restore_and_request_choices_persist`; `test_changed_fetched_configuration_returns_409_before_graph`; `test_headhunter_job_reaches_extraction_with_original_url`; `test_existing_jobs_remain_usable_without_headhunter_token`; `test_duplicate_terms_and_bad_queries_do_not_duplicate_or_start_empty_pool`.
- [ ] Run `backend_pytest tests/modules/test_market_demand_sources.py tests/modules/test_market_demand_source_flow.py -q`; observe intended failures.
- [ ] Implement explicit adapters with captured immutable configuration. Preserve current JobSpy options for existing markets; for Uzbekistan LinkedIn keep location `Uzbekistan` and omit unsupported country_indeed. Reject Indeed Uzbekistan. Bound dispatch to eight workers and HeadHunter to two concurrent calls. Normalize missing values, provider ID/URL duplicate results, and existing title/company deduplication in stable source order. Keep existing usable-description filtering and 4000-character extraction input.
- [ ] Integrate source fields into STATE_KEYS, snapshot normalization, SSE, summary, and approved prompts. Reject changed fetched settings at the route before executing the graph. Validate provider configuration before fetching, while permitting chat analysis of already-fetched jobs when tokens are absent. Disagreeing explicit fetch country cannot override a confirmed teacher market. Store success/empty/partial/error counts and sanitized warnings; retain other selected providers' usable jobs.
- [ ] Run `backend_pytest tests/providers/test_headhunter.py tests/modules/test_market_demand_sources.py tests/modules/test_market_demand_source_flow.py tests/modules/test_market_demand_thread_state.py tests/modules/test_market_demand.py -q`. Run backend Ruff check and format-check. Commit only the owned integration files after review.

## Task 5: Frontend source contract and restoration

**Owner:** Frontend worker; can start after Task 1 freezes the contract.

**Files:**
- Modify `frontend/src/features/market-demand/types.ts`, `api.ts`, `countries.ts`, and `hooks/useAgentStream.ts`.
- Extend `__tests__/api.test.ts` and `__tests__/useAgentStream.test.tsx` in that feature.

**Interfaces:**
- Export `JobSource`, `JobSourceOption`, `SourceOutcome` matching Shared contract.
- Extend `StreamChatArgs` with optional `sources: JobSource[]`.
- `fetchJobSources(courseId: number, country: string, signal?: AbortSignal): Promise<JobSourceOption[]>` uses the existing shared HTTP helper through feature api.ts.
- Extend `useAgentStream(courseId, countryOverride?, sourcesOverride?)` with nullable source override; every send path resolves the same selected sources.
- AgentState adds job_search_sources and job_source_results. Legacy missing keys merge defaults; never overwrite known persisted choices.

- [ ] Write failing tests asserting sources are serialized only when supplied, country remains optional, restored HeadHunter choices are sent, source SSE changes update state, missing old keys default to Indeed + LinkedIn, clear retains next-run choices, and course changes cannot send stale overrides.
- [ ] Run `docker exec lab_tutor_frontend sh -lc 'cd /app && npm test -- --run src/features/market-demand/__tests__/api.test.ts src/features/market-demand/__tests__/useAgentStream.test.tsx'`; confirm intended failures.
- [ ] Implement the exact contract and Uzbekistan option with `@/` imports. Keep auth refresh, SSE parsing, message history, and group/skill replies unchanged. Cancel/ignore stale restoration requests on course changes; preserve explicit choices separately from restored defaults.
- [ ] Rerun the targeted tests and commit only Task 5 files after contract review.

## Task 6: Teacher source picker and outcomes

**Owner:** Fresh frontend worker; depends on Task 5.

**Files:**
- Create `frontend/src/features/market-demand/components/JobSourcePicker.tsx`.
- Modify `pages/MarketDemandPage.tsx`, `components/ChatInput.tsx`, and `components/StatePanel.tsx`.
- Extend `__tests__/MarketDemand.test.tsx`; add `__tests__/JobSourcePicker.test.tsx`; update affected state fixtures in `pipeline-logic.test.ts` without adding duplicated implementation tests.

**Interfaces:**
- `JobSourcePicker({options, selectedSources, onChange, disabled})`: typed props, accessible labels, existing checkbox/popover/dropdown primitives.
- Page owns the current choices/catalog and passes sourcesOverride to the hook. Source options use the catalog endpoint, not frontend guesses about credentials.

- [ ] Write failing tests for selecting several sources, allowing a checked incompatible source to be removed, requiring at least one usable source before a new fetch turn, request/country change without silently changing websites, locking/restoring after fetched jobs, same choices on typed/suggested/selection-panel sends, per-source counts/warnings, and stale catalog responses after a course/country switch. Existing fetched jobs remain chat-usable when HeadHunter configuration becomes unavailable.
- [ ] Run targeted MarketDemand/JobSourcePicker Vitest files and observe missing behavior.
- [ ] Implement the picker near the composer with Tailwind/cn and plain user-facing availability reasons. Disable during restoration/streaming and after fetched jobs. Do not show environment variable names or HTTP implementation details in product copy. Keep current choices on clear and reset overrides on course switch. Update StatePanel with selected sources and safe provider outcomes.
- [ ] Run all market-demand Vitest tests, then `docker exec lab_tutor_frontend sh -lc 'cd /app && npm run lint && npm run build'`. Commit only the feature UI/test files after review.

## Task 7: Integration, credentials, and actual behavior verification

**Owner:** Coordinator; both workers finished and per-task reviews resolved.

**Files:**
- Modify only the coordinator-owned portions of `README.md`, `.env.example`, this plan, and the spec's status/handoff.
- Real credentials, if obtained, go only into ignored local environment files with restrictive permissions.

- [ ] Run the combined targeted backend suite from Task 4 and all frontend market-demand Vitest tests. Check new DTOs match actual endpoint JSON and restored SSE state. Run full backend Ruff check/format-check and frontend lint/build; distinguish unrelated WIP failures from feature failures. Broaden tests only when dependencies or failures justify it.
- [ ] Exercise the actual teacher UI: choose Uzbekistan and LinkedIn/HeadHunter as available, remove incompatible Indeed explicitly, send a message, select groups, refresh into the same thread, and verify locked sources and StatePanel counts. Use a disposable local teacher/course fixture; preserve user data and existing Neo4j data.
- [ ] HeadHunter access: the current Chrome developer account is authenticated but has no registered applications. The registration form says job-seeker API support ended December 15, 2025 and asks for one/multiple employer use cases; approval can take up to 15 working days. Obtain real employer details or provider confirmation before declaring such a use case. The [API terms](https://dev.hh.uz/admin/developer_agreement) restrict non-recruitment use, retention, redistribution, and third-party data use. Disclose stored job snapshots, HTML normalization, derived skills, and transmission to the configured LLM. Obtain provider confirmation of that use and any required archival/retention controls before live operation. Prepare accurate Lab Tutor application fields and request action-time confirmation before accepting terms/creating credentials. Do not invent an employer, bypass restrictions, or create duplicate applications.
- [ ] If an application token and approval covering the actual use become available, implement/review any additional provider-required controls, save the token without printing it, recreate the backend to reload environment, and fetch a small live Uzbekistan sample through the implemented service. Verify a full description, original URL, and selected-provider enforcement. If approval/access remains unavailable, complete automated implementation and leave HeadHunter explicitly unconfigured with a precise live-verification handoff. Do not contact provider support without the user's explicit messaging authorization.
- [ ] Request a fresh whole-branch review for security of credentials, conversation isolation, source enforcement, HTML normalization, and UI restoration. Resolve findings, rerun only affected checks, and record actual evidence/limitations.
- [ ] Finish with a focused feature diff/commit sequence and a concise user handoff. Do not merge, push, or create a PR unless requested or warranted by the user's continuation.

## Plan self-review

The seven tasks cover the provider boundary, country compatibility, teacher choices, legacy restoration, concurrent state, cancellation/persistence ordering, partial failures, provenance, UI, credential setup, and live verification. The Shared contract is the authority for all cross-stack names. Every Review Focus condition has a named behavioral test in its owning task. No task installs dependencies or changes infrastructure/Neo4j schema. External API approval is separated from automated correctness.

Implementation remains pending review of this written plan; retain the user's already selected sub-agent TDD execution method.
