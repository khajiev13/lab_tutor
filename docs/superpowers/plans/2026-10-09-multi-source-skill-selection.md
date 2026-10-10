# Multi-Source Skill Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect vacancy and O*NET evidence concurrently, help teachers choose categories and individual skills, and make only approved, job-backed skills available for new student selections. Every skill approved through this flow must retain at least one real supporting job-posting link.

**Architecture:** Reuse the Market Demand Analyst swarm and parallel extractor. Add a dedicated HeadHunter provider, an imported O*NET catalog, durable SQL evidence and versioned teacher decisions. PostgreSQL is authoritative; an idempotent projector updates Neo4j and existing curriculum/student views. Recommendations propose changes to a draft; they do not approve or publish it.

**Tech Stack:** Existing Python/FastAPI/Pydantic/HTTPX/SQLAlchemy/PostgreSQL/Neo4j/LangGraph backend and React/TypeScript/Shadcn/Tailwind frontend. Existing Docker development containers. No new package dependency or queue service.

**Spec:** `output/headhunter-explorer/teacher-skill-selection-proposal.html`, approved by the user's “Of course” on 2026-10-09. Supplementary provider design: `docs/superpowers/specs/2026-10-03-headhunter-job-sources-design.md`.

**Status:** Implementation approved by “Proceed” on 2026-10-09 and in progress. Execution uses subagent TDD with disjoint backend/frontend ownership. Track verified task completion in the execution ledger; do not interpret unchecked steps as complete.

## Global Constraints

- “Each candidate has a stable ID.” Candidate IDs remain stable within an analysis run; approved course skill references remain stable across runs.
- “Selecting a category selects every current member of that category.” Bulk actions resolve to explicit current candidate IDs; late arrivals stay unselected.
- “Sorting, refreshing or asking the agent for advice must preserve those exclusions.” Explicit exclusions survive recommendation generation, regrouping and reload.
- “Only the approved skills become available for students to select.” Draft selection and final approval are distinct decisions.
- “Each skill should have the link to their job postings.” Every skill approved through this new flow requires at least one real posting whose evidence supports that skill, with its original URL visible to teachers and students. O*NET enriches candidates; an O*NET reference alone never qualifies a skill for publication. This correction governs the contracts and tests below.
- “Store the full returned vacancy details” and “retain every source and original posting link.” An LLM context limit is not a storage limit.
- “O*NET's ratings are occupation-specific.” Keep occupation, original descriptor, release, scale, quality flags and mapping relation. Never present a broader descriptor's rating as a specific technology's official score.
- Importance, occupational level, job frequency and agent recommendations remain separate. Missing/suppressed/unmatched values are not zero or learner mastery.
- Use only selected job providers, with no unselected fallback. Preserve results and explicit failure status from each enabled source.
- Source failures, incomplete extraction and sample limits remain visible; never claim complete market coverage.
- No credentials in tracked files, evidence snapshots, browser persistence, logs or exports. Reuse the existing HeadHunter token; do not rotate it.
- Scope collection to the selected course, occupations and market. Preserve provider retention requirements when implementing snapshot storage; successful HTTP access does not define an unlimited retention policy.
- Follow existing module/repository/service boundaries and `Depends()` injection. No SQL or ad hoc HTTP calls in UI components. Frontend imports use `@/`, styles use Tailwind/cn, and actual forms use react-hook-form/zod.
- Headless browser verification; all backend/frontend checks inside existing Docker containers. Do not install host dependencies.
- Preserve unrelated WIP. Serialize PostgreSQL test runs because fixtures truncate the shared test database. Query live Neo4j schema through its MCP tool before authoring new Cypher; test graph writes on a disposable graph only.

## Review Focus

1. A category is selected, one child excluded, then filtering, new evidence or an agent proposal arrives: exclusions survive and new members stay unselected (Tasks 5, 8).
2. One posting contains synonymous mentions or appears on two sites: count one supporting vacancy, retain every provider link, and do not collapse different jobs merely because their titles/employers match (Tasks 2, 4).
3. A relevant skill appears after character 4,000, or one extraction chunk fails: preserve full text and report extraction coverage without inflating or silently zeroing demand (Task 4).
4. SQL approval succeeds but graph projection fails, or another course uses the same skill label: retain approval, retry idempotently and keep course metrics/visibility isolated (Tasks 6, 9).
5. A withdrawn/unapproved skill is requested through an old name-based API, bulk posting selection or a new ID: enforce the same availability boundary while preserving existing student study paths (Task 9).
6. An O*NET candidate has no supporting vacancy, or merging gives it an unrelated posting URL: keep it pending and reject final approval until actual skill-specific job evidence exists (Tasks 4, 6, 8–9).

## Relationship to earlier plans

This is the execution entry point. The earlier HeadHunter and O*NET plans remain detailed implementation references, not independent branches to execute in full.

- Reuse HeadHunter's provider separation, Uzbekistan handling, source catalog, bounded requests and conversation-isolation requirements.
- Replace its “no new relational table” assumption: durable evidence must survive chat deletion. Keep full returned vacancy payloads; do not truncate stored descriptions to 4,000 characters or discard provenance during deduplication.
- Reuse the O*NET versioned import/catalog and evidence-preserving mapping design. Replace its O*NET-only approval table with one generic evidence-binding table used by jobs-only and mixed approvals. O*NET-only candidates remain discovery/draft references until supported by real postings; earlier instructions permitting their publication are superseded.
- Preserve existing public student `source` values (`book`, `market`). Add explicit reference IDs and evidence metadata rather than introducing an `onet` transport source enum. An internal O*NET graph target remains distinguishable; its provenance is never presented as a fabricated vacancy.
- Replace category-name/chat-string confirmation with versioned, ID-based selection. Agent-generated text cannot grant final approval.
- New worker instructions must read this plan first. Where older names or behaviors conflict, this document wins.

## Implementation ownership and file map

Work in the existing `feat/headhunter-job-sources` checkout, already mounted in the local containers. Do not create a second execution branch for O*NET or copy unrelated WIP. Confirm current status at execution start. Coordinator owns docs, contracts, integration, local secret setup and final verification; one backend worker owns `backend/`, one frontend worker owns `frontend/`. Implementation workers may proceed in parallel after the contracts below are frozen. Independent review remains read-only.

| Files | Responsibility |
| --- | --- |
| NEW `backend/app/providers/headhunter.py` | Injected HTTPX provider, full vacancy payloads, safe bounded retries and normalization |
| `backend/app/core/settings.py`, NEW MDA `schemas.py`, `job_sources.py`, existing `countries.py` | Provider configuration, typed records, source catalog and concurrent dispatch |
| MDA `state.py`, `routes.py`, `models.py`; NEW `repository.py`, `thread_state_service.py`, `review_service.py`, `evidence.py`, `neo4j_repository.py` | Isolated runs, durable source/candidate evidence, decisions, deterministic metrics and graph projection |
| MDA `tools.py`, `extractor.py`, `graph.py`, `prompts.py` | Source orchestration, chunked extraction, ID-preserving mapping, recommendation proposals and final-review gate |
| NEW `backend/app/modules/occupation_reference/{__init__,models,schemas,importer,repository,service,routes}.py` | Versioned O*NET release, occupation/skill lookup and attribution |
| NEW `backend/scripts/import_onet.py`, `project_skill_evidence.py`; `backend/main.py`, `backend/app/core/neo4j.py` | Administrative import/retry and existing startup/constraint registration |
| Courses `curriculum_schemas.py`, `curriculum_service.py`, `curriculum_neo4j_repository.py` | SQL-enriched evidence and approved career skills, preserving current book/posting views |
| Student learning path `schemas.py`, `service.py`, `neo4j_repository.py`; resource pipeline `schemas.py`, `neo4j_repository.py` | Stable selection identity, availability enforcement and resource target resolution |
| Frontend market-demand `types.ts`, `api.ts`, `countries.ts`, `hooks/useAgentStream.ts`, `pages/MarketDemandPage.tsx`, `components/StatePanel.tsx` | Configuration, state restoration, source progress and review state |
| NEW market-demand `components/{JobSourcePicker,OnetOccupationPicker,SkillReviewPanel,SkillEvidencePanel,IntegrationReview}.tsx`, `selection.ts`, `pipeline.ts` | Nested selection, source evidence, revisions and final confirmation; retain existing flat SelectionPanel for queries/job groups |
| Frontend curriculum `types.ts`, `skill-bank-display.ts`, `components/MarketSkillBank.tsx`; NEW `components/CareerSkillBank.tsx`; relevant curriculum page | Approved skills with their supporting job-posting links |
| Frontend student learning path `api.ts`, `pages/StudentLearningPathPage.tsx`, skill-bank components | ID-based selection and evidence display with legacy compatibility |
| Existing affected tests plus new test files named below | Behavior, real persistence and end-to-end verification |

## Frozen contracts

### Sources and concurrency

- `JobSource = Literal['indeed', 'linkedin', 'headhunter']`; `EvidenceSource = Literal['jobs', 'onet']`.
- Existing chat gains optional `sources`, `evidence_sources` and `onet_release`. Legacy defaults remain jobs with Indeed/LinkedIn; never silently enable an external provider. Restore saved choices before allowing input.
- O*NET-only configuration permits reference discovery and draft shortlisting, not publication. Explain that collecting supporting vacancies requires a new analysis with explicitly selected job providers; never silently enable one to fill missing evidence.
- Job source catalog: `GET /courses/{course_id}/market-demand/sources?country=Uzbekistan` returns `{id,label,availability,reason}` records. Availability is `available`, `unsupported_country` or `not_configured`; no catalog network probes.
- HeadHunter's initial market is Uzbekistan (`host=hh.uz`, `area=97`). Indeed is unavailable for Uzbekistan in the installed adapter. LinkedIn keeps that location without passing an unsupported Indeed country enum.
- Defaults: 15 postings per selected query/provider, previous 72 hours. Validate result cap 1–100; deduplicate queries. Maximum eight source tasks, with at most two active HeadHunter calls. Each branch returns its own records; coordinator merges them deterministically.
- `SourceOutcome` contains `status: idle|loading|success|empty|partial|error`, `received_count`, `usable_count`, `warnings`. Report provider and O*NET status independently.
- Once configuration starts producing results, changing sources/market/occupation release requires a new analysis. Selection editing does not rerun fetch/extraction.
- In mixed mode, O*NET lookup may overlap job collection; teacher job-group approval still precedes vacancy extraction. A partial/error source requires an explicit teacher “Continue with available evidence” acknowledgement or retry before review advances. Record acknowledged omissions in the review digest. Continuation never waives the supporting-posting requirement: if all job sources fail, O*NET results remain pending references.

### Small durable storage model

Use typed JSONB for variable provider payloads and run manifests; do not introduce a general-purpose skill ontology service.

| SQL record | Contract |
| --- | --- |
| `onet_releases`, `onet_occupations`, `onet_evidence` | Reuse the earlier O*NET plan: immutable release/hash manifest, SOC/element identities, original rows and separate ratings/flags. Only completely imported releases become ready. |
| `market_analysis_runs` | UUID, course/teacher ownership, server-set approval contract version, config JSONB, source/extraction status, candidate manifest JSONB, candidate/selection/publication revisions, selected/excluded candidate IDs, recommendation proposals, final review and lifecycle. Durable independently of chat history. Legacy exemptions cannot be selected by client payloads. |
| `market_vacancy_snapshots` | UUID, run FK, provider, native ID or canonical-URL identity, content hash, original URL, full returned JSON, original description, cleaned text, returned dates/status, retrieval time, query membership and `demand_identity`. Preserve separate source snapshots even when grouped for counting. Unique run/provider/identity/hash; repeated identical fetches update run observation/query membership without duplicate evidence. |
| `course_skill_references` | UUID, course FK, verified target identity/label, origin, display data, approved mapping/chapters, approved/projection revisions and status, availability for new student selection. Reuse existing reference when a candidate resolves to the same verified course target. |
| `course_skill_evidence` | UUID, composite course/reference FK, approval/run/candidate identity, mapping relation, rationale/excerpts, and exactly one FK to `market_vacancy_snapshots` or `onet_evidence`. Enforce the exclusive source constraint and idempotent binding key. |

Candidate manifests contain UUID `candidate_id`, display name, one primary `category_id`, original labels/aliases, evidence references, job metrics, O*NET associations and recommendation reasons. Include server-derived `posting_support: supported|missing` and qualifying posting links. IDs survive rename/regroup within a run; a different run receives new candidate IDs, and approved references carry the stable cross-run identity. Do not use names, O*NET elements or Neo4j element IDs as universal skill IDs.

Each vacancy evidence item includes snapshot ID, original extracted phrase, evidence kind (`provider_tag` or `extracted_text`), and validated cleaned-text excerpt/offset. Keep provider tags separate from model-inferred skills. The official provider response remains unchanged in its snapshot; cleaned/rendered content is separate. Never render provider HTML directly.

Qualifying job support requires a stored posting in the same run/course from a selected provider, its original absolute HTTP(S) posting URL, and a provider tag or validated source passage supporting this specific skill and its final reviewed target. A source homepage, search page, O*NET URL, arbitrary client URL or broader/related skill association does not qualify. Record retrieval time and returned status; a later-archived posting can remain genuine evidence, so do not require a fresh HTTP 200 at every approval or promise that external postings remain online forever. Merges preserve all genuine supporting URLs and cannot transfer eligibility between unrelated skills.

Posting deduplication is conservative: identical provider IDs/URLs identify repeated observations; proven syndicated copies may share a demand identity. Same title/company alone is insufficient. A merge unions source records, URLs and supporting identities instead of adding counts. Keep uncertain duplicates separate and label sample limits.

No hardcoded vacancy lifetime is inferred. Implement the approved provider retention/archival policy in the storage service/runbook before unattended collection; preserve tombstone identity and permitted derived provenance if content must expire. Never claim that full evidence remains available after a required content purge.

### O*NET scope and ratings

Import official release 31.0 using versioned bulk CSV: occupation data, job titles, content model reference, essential skills, transferable skills, software skills and scales reference. Reuse strict parsing, SHA256 manifests, transactional activation and license attribution from O*NET plan Tasks 2–4. Do not crawl O*NET pages or require API credentials.

Teachers confirm 1–5 occupations. Each evidence item retains release, SOC, occupation title, family, original element/label/definition, official URL and original rows. `Metric` has `scale_id`, nullable `value`, `minimum`, `maximum`, `status: reported|missing|suppressed|not_relevant`, source date and quality metadata. Software examples retain Hot Technology/In Demand flags and have no IM/LV metric values.

Each candidate association has `relation: equivalent|broader|related|unmatched`, mapping method and rationale. Only equivalent rated descriptors are sortable as that candidate's O*NET rating; broader/related evidence is shown explicitly as context. Job-backed candidates remain approvable without O*NET ratings. O*NET-only candidates may be shortlisted but show “Needs supporting job posting” and cannot be published. Multi-occupation sorting requires an active occupation chosen by the teacher; no unexplained average or maximum score. Knowledge, Abilities and Work Styles imports remain outside this first release.

### Versioned teacher review API

All endpoints enforce existing teacher/course ownership through injected services. IDs in requests must belong to the specified run/course. Record server-side teacher identity; never trust client ratings, graph targets or approval authors.

- `GET /courses/{course_id}/market-demand/skill-review` returns the active `SkillReview`, or a typed empty review with no active run.
- `SkillReview`: `run_id`, `candidate_revision`, `selection_revision`, `categories`, `candidates`, `selected_candidate_ids`, `excluded_candidate_ids`, `recommendations`, `source_outcomes`, `extraction_coverage`, `integration_review`, `publication_revision` and approved reference summary.
- `PUT .../skill-review/draft` takes `run_id`, `expected_candidate_revision`, `expected_selection_revision`, `selected_candidate_ids`, `excluded_candidate_ids`; returns the acknowledged full review. Lists are disjoint, contain only current candidates, and may both be empty. Return 409 for stale revisions and 422 for invalid/foreign IDs. Do not show success until acknowledged.
- `POST .../skill-review/selection-confirmation` takes run ID and both expected revisions; records the exact nonempty draft as the input for mapping/cleaning. Changing the draft later invalidates that confirmation and any final review, without changing published skills.
- Agent proposals contain ID, candidate/base-selection revisions and changes `{candidate_id,action:add|remove,reason}`. Proposals do not mutate selection. The teacher explicitly applies all or selected changes through the draft endpoint; a proposal cannot automatically re-add an excluded item.
- `POST .../integration-approval` takes run ID, both expected revisions, `review_digest`, and explicit `approved_candidate_ids`. The server resolves only its own stored reviewed targets, validates current selection, and atomically records references, evidence and publication revision. In the same transaction, validate at least one qualifying vacancy binding for every approved candidate and resulting skill target, including covered/merged skills. Reject the whole request with 422 `missing_job_evidence` and affected candidate IDs if any lack support; never silently omit candidates or fabricate links. Neither teacher continuation nor agent tools can bypass this gate. Return projection status separately. Empty approval is allowed only when explicitly withdrawing a previously published offering for this analysis; initial approval must include at least one candidate. Candidates covered by existing skills may still attach evidence without creating a new competency.
- Digest includes candidates, exact target/course/chapter relationships, accepted evidence associations with snapshot IDs and original posting URLs, omissions, and reviewed revisions. Merging, evidence removal or mapping changes invalidate it. Use transactional revision checks so concurrent evidence changes cannot bypass the support gate. Keep the previous published offering intact until a new approval succeeds.
- A publication updates only this run's previously approved offering, never unrelated book skills or another run's approvals. A new-flow reference remains available while at least one active, job-backed course approval includes it. Record run-level approved reference IDs/revisions so withdrawing a run's offering cannot erase evidence or another approval.
- `GET .../skill-review/postings/{snapshot_id}` returns full safe evidence only for an authorized course/run; no unscoped raw-payload endpoint. Student views expose approved, permitted evidence summaries and original posting links for every new-flow skill; O*NET reference links are labelled separately. Do not expose arbitrary provider JSON.
- Add one SSE event, `skill_review_changed`, carrying `run_id`, `candidate_revision`, `selection_revision`, `publication_revision`. The client refetches a coherent snapshot; do not stream selected/excluded arrays independently. Retain existing SSE events for legacy pipeline state.

O*NET release/occupation lookup and `POST .../occupations` retain the earlier plan's owner-scoped routes and explicit confirmation, using this run's current revision. The source catalog and every send path must resolve the same teacher configuration.

### Selection behavior

Category state is derived from membership intersection with selected IDs: none, some (indeterminate), or all. Selecting a category adds all its current member IDs, including hidden matches; show that count. Clearing it removes its current members and records explicit exclusions. Individual check/uncheck removes/adds that ID from the excluded set as appropriate. Merely expanding a category has no effect.

Filtering changes visibility only. Offer a separately labelled “Select visible results” action if useful; never change the meaning of a category checkbox with an invisible filter. Later candidates remain unselected. Evidence or category revisions keep choices for unchanged IDs; removed/merged IDs require visible reconciliation, not silent transfer of a prior approval. Persist drafts, debounce only where acknowledgement remains clear, and provide undo for local batch actions.

Draft selection may include candidates awaiting vacancy evidence, so category selection still means every current member. Display their pending status and missing-evidence count. Final approval stays disabled until all proposed skills have qualifying postings or the teacher explicitly removes the unsupported skills; the server independently enforces the same rule.

### Graph and student compatibility

Use one SQL approval and projection service for every new run, including jobs-only. Existing agent insert tools become service delegates; they cannot write unapproved candidates directly. Project only approvals satisfying the per-skill posting requirement; reject malformed approval data instead of publishing an O*NET-only skill. Mapping/cleaning/concept proposals retain candidate/evidence IDs and include covered/merged results rather than dropping their evidence.

Inspect actual schema via MCP before new Cypher. Reuse verified book/market targets; give targets a durable evidence target ID where absent. Create O*NET-origin targets using the earlier `ONET_SKILL:SKILL` design only after they also acquire qualifying job evidence. Origin records discovery, not an exemption from posting support. Project course-scoped reference/binding identity and real `SOURCED_FROM` links using idempotent writes. Do not overwrite global skill frequency or other course-specific properties on shared name-keyed nodes. Read metrics from course/run evidence.

Add `career_skill_bank` to teacher/student bank DTOs: approved reference ID, label/category, public `source` (`book` or `market`), separate origin/evidence arrays, nullable job metrics, projection state and `available_for_new_selection`. Keep existing book and posting-grouped arrays. Every new-flow skill includes at least one qualifying original job-posting link; O*NET-only references stay out of this published bank. Existing book/market cards receive attached evidence and count stable references once.

New student requests may send `skill_reference_ids`; retain existing name/source payloads and bodyless recovery builds. Resolve new IDs server-side to the verified course graph target, and verify enrollment, job-backed publication and projection readiness. Legacy names resolve only unambiguously within the accessible course; ambiguity returns a typed error requesting an ID. Use one availability check for direct skills, posting bulk selection, drafts and build requests.

Scope assumption: this requirement applies to every new approval through the multi-source flow; it does not retroactively delete existing book skills or student work. Grandfather existing enrolled-student selections and pre-feature course offerings; lazily create reference bindings when first touched without changing quiz/resource identity. An existing skill receiving a new approval through this flow still requires job evidence for that approval. Withdrawal prevents new selection but preserves saved learning paths, resources and recovery builds. O*NET ratings never change quiz-derived `is_known` or readiness scores. Resource discovery resolves trusted graph target identity from the reference, not a client label.

## Verification setup

Docker executable is `/Applications/Docker.app/Contents/Resources/bin/docker`. Use the following helper only against the local test database; it disables live external services during ordinary pytest runs:

```bash
backend_pytest() {
  /Applications/Docker.app/Contents/Resources/bin/docker exec -e PYTHONPATH=/app lab_tutor_backend /app/.venv/bin/python -c 'import os,subprocess,sys; from urllib.parse import urlsplit,urlunsplit; env=os.environ.copy(); url=urlsplit(env["LAB_TUTOR_DATABASE_URL"]); assert url.hostname=="lab_tutor_postgres"; env["LAB_TUTOR_DATABASE_URL"]=urlunsplit(url._replace(path="/lab_tutor_test")); env["LAB_TUTOR_NEO4J_URI"]=""; env["LAB_TUTOR_AZURE_STORAGE_CONNECTION_STRING"]=""; env["LANGSMITH_TRACING"]="false"; env["LANGCHAIN_TRACING_V2"]="false"; sys.exit(subprocess.run([sys.executable,"-m","pytest",*sys.argv[1:]],env=env,cwd="/app").returncode)' "$@"
}
frontend_vitest() {
  /Applications/Docker.app/Contents/Resources/bin/docker exec lab_tutor_frontend npm test -- --run "$@"
}
```

Use real PostgreSQL for persistence/ownership/concurrency tests; mock only external providers/LLMs. Graph acceptance uses an isolated Neo4j fixture and refuses the production graph URI. Add `backend/tests/fixtures/market_skill_graph.py` and `backend/docker-compose.market-skill-test.yml`: graph tests read explicit `MARKET_SKILL_TEST_NEO4J_URI`, username/password/database variables from the container; they never fall back to app settings. Launch the isolated service on a separate network/volume and remove only its test data. Required graph checks must fail clearly when their fixture is unavailable rather than silently pass by skipping. No blanket deletion in a shared graph. Run source/state tests serially across workers.

At execution, baseline the touched suites and report unrelated failures. Final static checks are `docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/ruff check . && /app/.venv/bin/ruff format --check .'` and `docker exec lab_tutor_frontend sh -lc 'cd /app && npm run lint && npm run build'`, using the absolute Docker binary above when needed.

## Task 1: Isolate conversations and persist versioned analysis runs

**Owner:** Backend. **Files:** MDA `state.py`, `models.py`, `routes.py`; new `repository.py`, `thread_state_service.py`, `schemas.py`; tests `test_market_demand_thread_state.py`, `test_market_skill_review.py`.

**Interfaces:** `bind_tool_store(state)`, detached `snapshot_state/restore_state`, `ThreadStateService.claim/release/load/save/delete`, and `MarketReviewRepository.create_run/get_run/update_manifest/save_draft`. Repository mutations require expected revisions; routes obtain services via Depends. `run_id` links chat state to durable SQL, which is not deleted by clearing chat.

- [x] Write failing tests for cross-course isolation, overlapping run conflicts, ordered writes, stream disconnect/late worker completion, detached nested snapshots, durable run restoration and revision conflicts. Use Event barriers, not timing guesses.
- [x] Run `backend_pytest tests/modules/test_market_demand_thread_state.py tests/modules/test_market_skill_review.py -q`; verify the failures correspond to missing behavior.
- [x] Implement request/task-local mapping, execution guard and ordered persistence. Bind both the streaming producer and synchronous tool execution; workers receive captured immutable configuration. Create the run model/schema through existing startup conventions.
- [x] Rerun the two files and `tests/modules/test_market_demand.py`; require passing real-DB assertions and guard release on setup failure/cancellation.
- [x] Review and commit only the task-owned files. Freeze DTO names with the frontend worker before its tasks begin.

## Task 2: Add HeadHunter and retain complete provider evidence

**Owner:** Backend. **Files:** provider `headhunter.py`; MDA `job_sources.py`, `countries.py`, `models.py`, `repository.py`, `schemas.py`, `routes.py`; settings; tests `tests/providers/test_headhunter.py`, `tests/modules/test_market_demand_sources.py`, `test_market_vacancy_evidence.py`.

**Interfaces:** `HeadHunterService(client,user_agent,access_token).search_jobs(search_term,area_id,results_wanted,hours_old)`, normalized `ProviderVacancy` retaining full raw detail, `JobSourceService.catalog/validate_compatibility/fetch`, `MarketReviewRepository.upsert_vacancy_snapshot(run_id,record)`.

- [x] Write provider/real-DB evidence tests: correct auth/host/area/time range; search then full detail; all returned fields/full multilingual description retained; nullable employer; removed detail; repeated IDs; same title/company different IDs; syndicated evidence preserves all links; tokens never stored/logged; selected sources genuinely overlap and HeadHunter concurrency never exceeds two.
- [x] Run `backend_pytest tests/providers/test_headhunter.py tests/modules/test_market_demand_sources.py tests/modules/test_market_vacancy_evidence.py -q` and observe intended failures.
- [x] Implement using the old HeadHunter plan Tasks 1/3/4 as detailed provider guidance. Preserve its 15-second/read, 5-second/connect timeouts, maximum three attempts and five-second total retry-delay budget per HTTP request; honor Retry-After only within that budget. Stop on auth/CAPTCHA and malformed responses, retain usable partial details. Persist safe full records before analysis filtering. Resolve source lifecycle/retention requirements in the repository, not frontend code.
- [x] Rerun the same tests plus country regressions. Verify no unselected provider runs after another source fails and no API request data exposes secrets.
- [x] Review and commit provider/source/evidence files only.

## Task 3: Import and expose the O*NET catalog

**Owner:** Backend. **Files:** new occupation_reference module, import script, startup registration, `tests/modules/occupation_reference/`, synthetic `tests/fixtures/onet/`.

**Interfaces:** Retain the prior O*NET plan's immutable importer, catalog repository, owner-scoped release/occupation routes and `OnetEvidence` contract, using the `Metric` statuses above. `load_occupation_evidence(release,soc_codes)` returns every supported row, including unavailable flags.

- [x] Write tests for required files/headers, encoding/null values, exact identifiers, software flags, IM/LV scale preservation, suppressed/not-relevant records, manifest equality, duplicate import idempotency, failed import rollback, owner-scoped search and occupation confirmation limits.
- [x] Run `backend_pytest tests/modules/occupation_reference/ -q`; observe missing import/catalog behavior.
- [x] Implement the seven-file pinned 31.0 import using prior O*NET Tasks 2–4. Store original source rows, URLs, checksums and attribution. Only complete imports become ready; an unavailable catalog does not disable jobs-only work.
- [x] Rerun the catalog tests and validate the official release through the importer's `--validate-only` mode inside Docker. Report counts/flags without treating old expected counts as universal future-release constraints.
- [x] Review and commit catalog files. Defer activation in the intended environment until integration acceptance passes.

## Task 4: Combine source results and preserve extraction evidence

**Owner:** Backend. **Files:** MDA `evidence.py`, `extractor.py`, `tools.py`, `graph.py`, `prompts.py`, review repository/service; tests `test_market_skill_evidence.py`, `test_market_source_orchestration.py`.

**Interfaces:** `collect_sources(run_config) -> source results`, `make_extraction_chunks(text,max_chars=4000,overlap=300)`, `reconcile_candidates(evidence,previous_manifest)`, `calculate_job_metrics(supporting_identities,assessed_identities)`. Source branches return independent results; only the coordinator commits manifests.

- [x] Write tests for jobs-only/mixed analysis and O*NET-only reference discovery, source overlap, partial-failure acknowledgement without waiving job support, a skill after character 4,000, evidence offsets, aliases within one posting counting once, equivalent merge evidence union, unrelated same-name candidates, broader/unmatched O*NET mappings, and ratings unchanged by teacher/student state.
- [x] Run `backend_pytest tests/modules/test_market_skill_evidence.py tests/modules/test_market_source_orchestration.py -q`; confirm expected failures.
- [x] Preserve full text; use 4,000-character chunks with 300-character overlap, maximum 16 chunks per posting and eight active extraction calls across the run. Record full/partial/failed coverage; do not silently discard a tail. Validate snippets against cleaned source text. Teacher can retry or explicitly accept partial coverage. Determine metrics from distinct successfully assessed posting identities; publish the denominator, partial coverage and selected-posting count. Never sum LLM-supplied frequencies.
- [x] Reuse existing swarm handoffs and extraction subgraph; add O*NET lookup as source work, not an unnecessary autonomous agent for each HTTP request. Preserve candidate IDs during equivalent merges where unambiguous; require visible reconciliation for conflicting teacher decisions. Rerun tests including existing tool/extraction regressions.
- [x] Review and commit the integration slice.

## Task 5: Persist teacher selection and agent proposals

**Owner:** Backend. **Files:** MDA `schemas.py`, `review_service.py`, `repository.py`, `routes.py`, `state.py`, selection-related tools/prompts; `test_market_skill_review.py`, `test_market_skill_recommendations.py`.

**Interfaces:** `SkillReviewService.get_review/save_draft/confirm_selection/create_recommendation`, exact HTTP contracts above. Recommendation methods produce versioned diffs only. State summary exposes acknowledged selection and review stage.

- [x] Write tests for disjoint/empty lists, invalid and wrong-course IDs, stale candidate/selection revisions, draft reload, explicit exclusions surviving agent proposals and late candidates, pending unsupported candidates remaining draft-only, selection confirmation invalidation after edits, and an LLM attempt to publish without teacher approval.
- [x] Run `backend_pytest tests/modules/test_market_skill_review.py tests/modules/test_market_skill_recommendations.py -q`; observe expected failures.
- [x] Implement transactional draft persistence and server-verified confirmation. Tool-generated recommendations cannot call an approval writer. Emit `skill_review_changed` only after commits; preserve legacy SSE state events for other stages. Chat steering generates proposals with concrete additions/removals and reasons.
- [x] Rerun both files and endpoint ownership/stream regressions. A failed write must not appear confirmed in returned state.
- [x] Review and commit the backend teacher-decision slice.

## Task 6: Approve evidence once and project it safely

**Owner:** Backend. **Files:** MDA `models.py`, `repository.py`, `review_service.py`, `neo4j_repository.py`, mapping/cleaner/linker tools; core graph constraints; retry script; tests `test_market_skill_approval.py`, `test_market_skill_projection.py`.

**Interfaces:** `SkillReviewService.prepare_integration_review/approve_integration`, `SkillEvidenceProjector.project(course_id,approved_revision)`, and `resolve_course_skill_reference(course_id,target)`. Approval is SQL-transactional; projection is retryable with independent status.

- [x] Write tests for job-backed jobs-only/mixed approval; atomic 422 rejection of O*NET-only or partially unsupported batches; unrelated URLs/merged neighbors failing to qualify a skill; covered/existing targets still requiring job evidence; valid archived-posting support; evidence changes invalidating the digest; foreign target rejection; exact one-source FK checks; all-candidates-covered review; withdrawn availability; inconsistent bindings refused by projection; SQL success/graph failure/retry; and same-label skills in separate courses retaining distinct metrics.
- [x] Run real-DB approval tests, then isolated-graph tests; observe the missing contracts before writing queries. Inspect actual graph schema via MCP first.
- [x] Implement one generic `course_skill_evidence` path and idempotent references/bindings. Carry IDs/evidence through Mapper, Cleaner and Linker; the linker prepares reviewed concepts/targets before final approval. Existing insert tools delegate to approved SQL projection and never bypass the review. Batch projection with UNWIND/MERGE and verified course targets; preserve old graph/assessment identities.
- [x] Rerun approval/projection tests and exercise retry after a deliberately induced graph outage in the disposable graph. Confirm the same binding/reference count on retry and no duplicate new skills.
- [x] Review and commit only the approval/projection slice.

## Task 7: Expose source configuration and reliable progress

**Owner:** Frontend; may run with backend Tasks 2–6 after Task 1 freezes contracts. **Files:** market-demand `types.ts`, `api.ts`, `countries.ts`, `hooks/useAgentStream.ts`, `pages/MarketDemandPage.tsx`, source/occupation pickers, `StatePanel.tsx`, new `pipeline.ts`; corresponding feature tests.

**Interfaces:** Typed source/catalog/review wrappers in feature `api.ts`; existing send paths share selected configuration. Hook handles `skill_review_changed` with abort/generation guards and coherent review refetch. UI displays each source's actual status.

- [x] Write tests for exact source serialization on typed/suggested/selection replies, restored configuration, unavailable providers/catalog, occupation confirmation, country compatibility, source error versus empty, course-switch stale responses and stream cancellation.
- [x] Run `frontend_vitest src/features/market-demand/__tests__/api.test.ts src/features/market-demand/__tests__/useAgentStream.test.tsx src/features/market-demand/__tests__/JobSourcePicker.test.tsx src/features/market-demand/__tests__/OnetOccupationPicker.test.tsx src/features/market-demand/__tests__/MarketDemand.test.tsx`; confirm intended failures.
- [x] Implement additive DTOs and controls with existing styles. Default new/legacy behavior remains jobs until explicitly changed. Lock source settings during restoration/collection; do not lock draft skill editing merely because jobs exist. Move actual stage derivation into `pipeline.ts`, imported by production and tests.
- [x] Rerun affected Vitest files. Verify old source choices cannot leak into another course and no stale `finally` clears a newer stream.
- [x] Review and commit frontend-owned source/progress files.

## Task 8: Build category and individual skill review

**Owner:** Frontend. **Files:** new `selection.ts`, `SkillReviewPanel.tsx`, `SkillEvidencePanel.tsx`, `IntegrationReview.tsx`; MDA page/hook/API/types; tests `selection.test.ts`, `SkillReviewPanel.test.tsx`, `IntegrationReview.test.tsx`.

**Interfaces:** `categorySelectionState(memberIds,selectedIds)`, `applyCategorySelection(draft,memberIds,checked)`, explicit snapshot-based draft mutations. Components consume the frozen SkillReview, never infer selections from agent prose.

- [x] Write tests for category select-all, individual exclusion and indeterminate counts, selection surviving filters/sorts/reload, late members unselected, partial recommendation apply, local undo, lost/stale writes, visible reconciliation after candidate merges, unrated job-backed skills selectable, pending missing-posting labels/counts, final approval disabled for unsupported skills, genuine posting links displayed, and multi-occupation ratings separated.
- [x] Run `frontend_vitest src/features/market-demand/__tests__/selection.test.ts src/features/market-demand/__tests__/SkillReviewPanel.test.tsx src/features/market-demand/__tests__/IntegrationReview.test.tsx`; verify behavioral failures before implementation.
- [x] Implement expandable categories and independently selectable rows. Show job sample counts, per-occupation metrics/status, exact/broader relationships and agent reasons in separate fields. Display “Needs supporting job posting” for unsupported draft candidates. Keep original posting links and full authorized posting evidence in an expandable evidence view, with O*NET links labelled separately. Applying suggestions changes only the draft; selection confirmation starts mapping. Final integration confirmation displays targets and publishes only when every proposed skill has qualifying job support; show server rejection without silently dropping candidates.
- [x] Rerun these files plus actual MDA page/hook tests. Assert failure does not display success and existing published skills remain unchanged during draft review.
- [x] Review and commit frontend-owned review files.

## Task 9: Make approved skills usable in curriculum and student paths

**Owner:** Backend first for readback/API contract, then frontend integration; disjoint work may overlap after that contract freezes. **Files:** curriculum/student/resource files in the file map; NEW frontend `CareerSkillBank.tsx`; affected teacher/student page/API tests and `test_market_skill_student_access.py`.

**Interfaces:** Additive `career_skill_bank`, `skill_reference_id`, evidence arrays, nullable job metrics and availability flags. Student APIs accept IDs alongside existing payloads. Resource services resolve reference -> trusted course target; legacy recovery builds remain valid.

- [x] Write real-DB/graph tests for job-backed jobs-only/mixed readback, O*NET-only references absent from the published bank, evidence attached to an existing book skill, distinct counts, direct/new-ID and old-name selection, posting bulk selection filtering, unapproved/unsupported/withdrawn rejection, client attempts to claim legacy exemption, existing student recovery/resources after withdrawal, cross-course IDs and quiz mastery unchanged. Corresponding UI tests must verify every new-flow skill exposes its real supporting posting links.
- [x] Run `backend_pytest tests/modules/test_market_skill_student_access.py tests/modules/courses/test_curriculum_service.py tests/modules/courses/test_curriculum_neo4j_repository.py tests/modules/test_student_learning_path_routes.py tests/modules/test_student_learning_path_service.py tests/modules/test_student_learning_path_repository.py -q` and `frontend_vitest src/features/curriculum/skill-bank-display.test.tsx src/features/curriculum/pages/CurriculumPage.test.tsx src/features/student-learning-path/pages/StudentLearningPathPage.test.tsx`; observe failure at the missing behavior rather than relying on a build. New resource-reference cases belong in `tests/modules/test_market_skill_student_access.py` and must exercise resource target lookup.
- [x] Implement SQL-enriched readback and stable-ID selection, preserving legacy enums and payloads. Keep existing posting browsing; add the flat career-skill view. Fix touched MAPPED_TO/HAS_SKILL read/write mismatches with actual readback tests. Handle pending graph projection explicitly; no false availability.
- [x] Rerun targeted backend and frontend suites. Verify already saved selections and bodyless recovery builds still work, and new selection cannot bypass publication via an old endpoint.
- [x] Review and commit backend/frontend portions separately; coordinator verifies their actual JSON contract together.

## Task 10: End-to-end verification, activation and handoff

**Owner:** Coordinator. **Files:** tests/fixtures, scoped integration fixes, README/example environment, `docs/operations/multi-source-skills.md`, this plan and HTML review.

- [ ] Run the combined new backend suites serially plus affected existing MDA/curriculum/student/resource suites. Run all changed frontend feature tests, backend Ruff check/format-check and frontend lint/build. Separate unrelated WIP failures from this feature.
- [x] Headless browser with a disposable teacher/course exercises: combined source selection; per-source failure and explicit continuation; category selection with one exclusion; agent proposal preserving it; evidence links and long-description access; an O*NET-only candidate blocking final approval until supported or explicitly removed; selection confirmation; covered/merged review; final approval; reload; a genuine supporting posting link on every published skill; student selection and resource recovery; withdrawal blocking only new selections. Verify actual persisted readback, not only displayed success text.
- [x] Validate/import the pinned O*NET release inside Docker and activate only after complete manifest/attribution checks.
- [ ] Resolve any source-retention requirements against the approved HeadHunter research use before unattended runs. Store the existing application token only in ignored protected local environment configuration and recreate the backend to load it; no token rotation and no contact with provider support without explicit instruction.
- [ ] Fetch a small authenticated Uzbekistan sample through the implemented HeadHunter service and verify native ID, original URL, full description, metadata and provider selection. Source-fetch validation is separate from any live LLM/graph run; report exactly what was exercised.
- [x] Exercise real parallel source start using barrier tests and record configured bounds. Demonstrate SQL approval survives a failed graph write and retry produces one set of references. Check approved evidence survives chat clear.
- [x] Run a fresh whole-change review, resolve findings and rerun affected checks. Save desktop/mobile screenshots and an HTML handoff showing actual sources/coverage/limits. Commit only scoped work; do not merge, deploy or push without the corresponding task authorization.

## Self-review and acceptance ledger

| Approved requirement | Tasks |
| --- | --- |
| Parallel source collection and skill extraction | 2–4, 7, 10 |
| Full original metadata, descriptions and every posting link | 2, 4, 6, 9 |
| Every newly approved skill has at least one genuine supporting job-posting link | 4, 6, 8–10 |
| O*NET importance/level and unavailable values with occupation context | 3–4, 8–9 |
| Category bulk selection with individual exclusions | 5, 8 |
| Agent recommends; teacher confirms exact choices and final availability | 5–6, 8–9 |
| Stable choices through reload, late results and revisions | 1, 5, 7–8 |
| SQL authority, graph retry and course isolation | 1, 6, 9–10 |
| Job-backed publication, O*NET enrichment/reference discovery and legacy student compatibility | 3–4, 6, 9–10 |
| Evidence survives covered/merged skill handling and chat deletion | 1, 6, 9–10 |
| Distinct-job counts and extraction coverage without fabricated scores | 2, 4, 8–9 |

The coordinator checked coverage, matching DTO names, six Review Focus cases and source-of-truth boundaries. This plan includes the user's correction that every approved skill needs supporting job-posting links and replaces conflicting execution instructions in both earlier plans. Existing proposal approval is recorded; the next review is this written implementation plan, not the design again.


## Execution status — 10 October 2026

Tasks 1–9 are implemented and committed. Task 10 remains open for protected HeadHunter backend configuration and a
direct live backend collection check; the grouped-suite timeout qualifications
remain explicit in the verification record.
The controlled teacher-to-student workflow completed 11 browser scenarios with
43 checks, three recovery checks and final PostgreSQL/graph readback. Official
O*NET 31.0 was imported and activated in labtutor, independently confirmed as
1,016 occupations and 63,671 evidence records. Two prior live HeadHunter
playground samples and a captured-response adapter replay are separate evidence,
not a direct live backend ingestion result.

Acceptance found and fixed lost source-outcome updates with autoflush disabled
(commit db2277b), after the earlier reviewed fixes in 9961355. The regression
failed under the application setting before the fix and passed both settings
afterward, with scoped Ruff/format and focused review. Full-suite timeout and
fresh-checkpoint startup limitations remain in the HTML report. Primary result:
output/headhunter-explorer/implementation-status.html.

The final narrow CLI projection regression passed on retry (1 passed in 43.46s, child/Docker exit 0), keeping both original 90-second subprocess limits. This closes that individual timeout; it does not turn the interrupted grouped runs into a clean combined suite. Temporary test services, graph volume/network and the task-created source-regression database were removed. The five previously stopped O*NET containers were restored. Main O*NET data and the existing playground connection were preserved.
