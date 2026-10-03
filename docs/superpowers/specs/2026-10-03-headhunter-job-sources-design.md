# HeadHunter and Teacher-Selected Job Sources

Date: 2026-10-03
Status: design approved in conversation; written spec awaiting review

## Intended outcome

Teachers choose the job websites used by the Market Demand Analyst swarm.
Add Uzbekistan vacancies from HeadHunter through a dedicated Python service
inside the existing backend. Its API logic stays separate from the existing
Indeed and LinkedIn JobSpy integration. All selected postings enter the existing
job-group selection, skill extraction, curriculum mapping, and graph-writing flow.

The user approved this architecture and the first-release scope: HeadHunter,
source selection, persistence, provider-specific country handling, explicit
failures, and tests. OLX remains a researched follow-up. A separately deployed
service would introduce another deployment and network contract without helping
this scope; the user explicitly selected an independent service inside the backend.

## Current implementation

- `marketdemandanalyst/tools.py::fetch_jobs` always calls Indeed and LinkedIn,
  concurrently, for every approved query. JobSpy returns DataFrames; usable
  descriptions become dictionaries consumed by `extractor.py`.
- The country module and frontend offer six countries and exclude Uzbekistan.
  The installed JobSpy country enum has no Uzbekistan entry and parses
  `country_indeed` even for LinkedIn searches.
- `POST /courses/{course_id}/market-demand/chat` accepts a message and optional
  country. PostgreSQL `MDAThreadState.state_json`, `STATE_KEYS`, and existing SSE
  `state_update` events already support persisted configuration.
- The page locks country changes after jobs have been fetched. The stream hook
  restores persisted state; older snapshots will lack new source fields.
- Tools share a process-wide `tool_store` dictionary. Adding source choices to
  that dictionary alone would allow concurrent chats to affect one another.
- Baseline verification: the existing 60 market-demand backend tests passed in
  `lab_tutor_backend` against `lab_tutor_test` before this change.

## Provider research and access

The [HeadHunter Uzbekistan developer portal](https://dev.hh.uz/) points to the
[official API](https://api.hh.ru/openapi/en/redoc). Search and vacancy detail are
separate requests. Selecting `host=hh.uz` does not limit geography: searches must
also specify Uzbekistan's area. A live directory request verified area ID `97`.
Vacancy details include an HTML description and optional skill tags.

Two small anonymous vacancy-search probes returned HTTP 403 with
`errors: [{type: "forbidden"}]`. This response does not identify whether the
cause was authentication, request identification, or another access restriction.
No live vacancy description has been fetched. Current documentation warns that
anonymous searches can require CAPTCHA. Do not assume older examples promising
unrestricted anonymous access are sufficient for this integration.

For reliable unattended use, this release requires a configured application
access token and identifying `HH-User-Agent`. Use an existing application token
if available; otherwise register Lab Tutor through the developer portal and use
the documented application authorization flow. Registration approval can be an
external dependency. The runtime reuses its token and does not generate or rotate
one during each search. No applicant OAuth, resume access, or employer-account
features are needed.

The [OLX Developer Hub](https://developer.olxgroup.com/) describes posting and
managing adverts for users. A usable public Uzbekistan vacancy-search API was
not verified. The [Uzbekistan policy](https://help.olx.uz/olxuzhelp/s/article/maxfiylik-siyosati-V32)
also describes developer access for posting users' own adverts. Do not present
OLX as an operational source or implement an undocumented scraper in this release.
The [national vacancy database](https://dgov.uz/en/solution/detail/87/) is another
potential follow-up; its machine-readable access remains unverified.

## Backend boundaries

- Add a dedicated HeadHunter provider/service under `app/providers/`. It owns
  the HTTP client, provider response validation, search pagination, vacancy detail
  requests, HTML-to-text conversion, timeouts, and provider-specific errors.
  Inject an HTTPX client so external requests can be tested with MockTransport.
- Add a small market-demand source service/catalog beside the current module.
  It validates source/country combinations, dispatches selected providers, adapts
  JobSpy output, and returns normalized jobs plus per-source outcomes. Use explicit
  functions and typed records rather than a plugin framework or class hierarchy.
- Keep `fetch_jobs` as the existing LangChain tool and preserve job grouping and
  downstream extraction. The tool delegates fetching and reads teacher-confirmed
  sources; it does not expose a model-controlled sources override.
- Keep route validation and ownership checks in the existing module, and use
  `Depends()` for injected route services. No new relational table or Neo4j schema
  is required: the additional configuration lives in existing thread snapshots.

## API and state contract

Stable source identifiers are `indeed`, `linkedin`, and `headhunter`.

Extend the chat body with optional `sources: list[JobSource]`. Existing clients
that omit it preserve restored selections; legacy snapshots with no selections
use `['indeed', 'linkedin']`. New clients explicitly send their selected sources.
Unknown values and an empty supplied list are validation errors. Canonicalize
duplicate values so a provider is never invoked twice for the same query.

Add a teacher-owned course endpoint:
`GET /courses/{course_id}/market-demand/sources?country=Uzbekistan`.
It returns source IDs, display labels, availability, and safe explanatory reasons.
Availability values are `available`, `unsupported_country`, and `not_configured`.
Never return credentials. The catalog is the authority for the frontend's source
availability; it does not perform paid calls or a live scrape just to render a picker.

Persist and emit these state additions using existing SSE events:

- `job_search_sources`: canonical selected identifiers.
- `job_source_results`: per-source status, usable-job count, and sanitized warnings
  from the latest fetch. Status is `success`, `empty`, `partial`, or `error`.

The selected configuration is authoritative before execution. A request attempting
to change country or sources after nonempty fetched jobs returns HTTP 409 before
the graph executes. The same configuration remains valid on subsequent messages.
Invalid source/country combinations fail clearly rather than being silently
removed. Clearing the conversation unlocks configuration and discards old jobs and
analysis. Old snapshots infer their historical default sources without changing jobs.

Snapshot state must remain scoped to the teacher/course thread. Replace the shared
backing dictionary with request/task-scoped state while preserving the mapping
interface used by existing tools. Start each request from its own restored snapshot;
copy the selected configuration into the fetch operation. Concurrent different
threads must not share mutable state. Reject overlapping execution in the same
thread with a clear conflict, and release that guard on completion or cancellation.
Order each thread's snapshot writes and finish outstanding persistence before
releasing its execution guard or deleting the thread. An older write must not
overwrite a newer selection or recreate state after a clear operation. Executor
workers receive captured configuration; they do not read the current state store.
On cancellation, discard late executor mutations from the abandoned run; stopping
the stream does not forcibly terminate synchronous tools. This work does not change
existing Neo4j side-effect cancellation behavior. A process-local execution guard
fits the current single-worker backend; coordination across replicas is outside
this release. The existing terminal chat entrypoint is outside this feature scope.

## Country and source behavior

- Preserve current country values and behavior; add canonical `Uzbekistan` and
  reasonable aliases such as `UZ` and `O‘zbekiston`.
- Separate the canonical market identifier from the optional JobSpy country value.
  HeadHunter supports Uzbekistan in this release and searches `host=hh.uz`, area
  `97`. Do not claim support for other HeadHunter regions yet.
- Indeed is unavailable for Uzbekistan through the installed integration.
- LinkedIn uses `location='Uzbekistan'`; its adapter must avoid passing the
  unsupported Uzbekistan value to JobSpy's Indeed-specific country parameter.
  Verify this request construction in tests and report real access failures.
- HeadHunter is unavailable until the application token and identifying user-agent
  are configured. This does not disable the existing providers elsewhere.
- Display incompatible selections after a country change and require the teacher
  to adjust them. Do not silently change their selected websites or market.

## Fetching, normalization, and failures

Use existing defaults of 15 requested results per selected source/query and a
72-hour recency window. Validate nonempty queries and bounded result counts before
network work. Respect documented pagination limits; keep HeadHunter concurrency
small and requests bounded by explicit timeouts. Honor rate limits with bounded
retry/backoff and no indefinite waits. Authentication/forbidden/CAPTCHA failures
must stop that provider; do not attempt CAPTCHA bypass or an unselected fallback.

HeadHunter search snippets are not full job descriptions. Fetch each selected
vacancy's detail, normalize HTML to readable Unicode text with paragraph/list
boundaries, and preserve Russian/Uzbek/English text. Never render provider HTML
directly in the frontend. Skill tags may be retained as metadata; they do not
replace the description-based skill extractor.

Normalized jobs preserve existing fields: `title`, `company`, `description`,
`url`, `site`, `search_term`, `country`, and `location`. Add a provider identifier
where supplied. `site='headhunter'` and the original posting URL must survive
grouping, selection, extraction, and skill evidence links. Deduplicate repeated
provider IDs/URLs across queries, and preserve existing cross-source title/company
deduplication behavior for this release. Continue the existing 4,000-character
extraction input limit rather than changing model costs or prompts broadly.

When one selected provider fails, retain usable results from the others and show
its error separately. If search succeeds but some vacancy details fail, report
partial results; a removed vacancy can be skipped with a warning. Zero results
must be distinguished from failure. Report counts after description filtering and
deduplication. Error messages and logs must not contain authorization headers,
tokens, or raw HTTP request objects.

## Teacher experience

Add a multi-select source picker near the chat composer with provider labels and
availability reasons. Keep ownership in the page/hook so typed messages, suggested
prompts, and selection-panel replies all send the same configuration. Require at
least one usable selected source before sending a fetch-capable turn.

Lock the picker and country control during state restoration, streaming, and after
jobs are fetched. Restore authoritative choices before enabling input. On clear,
keep the visible selections as the next search configuration while discarding old
analysis; on a course change reset local overrides so they cannot leak into a new
course. Add selected sources and per-source outcomes to the StatePanel.

Update supervisor and skill-finder prompts to show the selected market/providers,
use them as the fetch boundary, and ask the teacher to adjust the picker when
configuration is missing or unsupported. The LLM cannot substitute providers after
a failure. Existing group and skill approval steps remain in place.

## Configuration and operational handoff

Document `LAB_TUTOR_HH_USER_AGENT` and `LAB_TUTOR_HH_ACCESS_TOKEN` in the example
environment and local setup notes. The former includes the application name and
real developer contact; the latter stays only in ignored backend environment files.
Use existing Compose environment loading. Protect local credential files, and
recreate/restart the backend as required for newly loaded settings. No image,
dependency, Azure, MinIO, or Neo4j changes are part of this feature.

The browser currently requires HeadHunter sign-in; no application key was available
to inspect. Account sign-in/application registration and any approval or agreement
needed by HeadHunter are external prerequisites for live authenticated verification.
Prepare the application details and inspect existing applications before creating
a duplicate. Report this dependency separately from automated test results.

## Verification and acceptance

Use TDD: write a failing behavioral test, observe its intended failure, implement
the smallest change, and rerun. After the written spec and implementation plan are
reviewed, use disjoint backend and frontend workers; coordinator owns integration,
docs, contract review, and final verification. Preserve existing unrelated WIP.

Run tests inside existing Docker containers. Keep PostgreSQL real for API/state
tests, use a separate test database, and disable live Neo4j/storage/tracing in those
tests. Mock only external provider/LLM responses for deterministic coverage.

Required behavioral evidence:

1. HeadHunter search sends the correct market, pagination, recency, identity, and
   bearer headers; details supply the normalized full description and posting URL.
2. HTML normalization preserves multilingual text and handles optional/null fields,
   repeated IDs, removed postings, malformed responses, timeouts, and rate limits.
3. Exactly the selected providers are invoked. An unselected provider is never used
   on success, partial failure, or total failure.
4. Uzbekistan is accepted, Indeed incompatibility is explicit, and LinkedIn's
   adapter avoids the unsupported JobSpy country enum.
5. API validation, teacher/course ownership, source persistence, SSE updates,
   legacy restoration, clear behavior, and locked configuration are exercised.
6. Concurrent distinct chats keep their source choices and jobs isolated; overlapping
   execution of the same thread is rejected and cancellation releases the guard.
   Snapshot writes cannot reorder selections or resurrect a cleared thread.
7. The frontend picker serializes choices from all send paths, restores them after
   reload, shows availability/errors, and follows the configuration lock.
8. A normalized HeadHunter posting passes through real grouping/selection and the
   extraction boundary with its evidence URL intact; an LLM stub can keep this
   regression test deterministic.
9. After credentials/access become available, fetch a small live Uzbekistan sample
   and exercise the teacher selection in the browser. Do not call builds or mocked
   HTTP tests proof of live HeadHunter or LLM success.

Run targeted market-demand/provider pytest and frontend Vitest tests, backend Ruff
check/format checks, and frontend lint/build. Broaden testing only for affected
dependencies or failures. Record actual results and any live-access limitation.
