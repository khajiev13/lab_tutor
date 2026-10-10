# Multi-source skill operations

This runbook accompanies the HeadHunter and O*NET integration. The HTML
implementation report at `output/headhunter-explorer/implementation-status.html`
records which rollout checks have actually completed. Commands in this document
are operating instructions, not evidence that activation has occurred.

## Configure sources

The backend reads these settings from its protected local environment:

- `LAB_TUTOR_HH_USER_AGENT`: an identifying application User-Agent containing the application
  name and developer contact email.
- `LAB_TUTOR_HH_ACCESS_TOKEN`: the existing application access token.

Keep credentials out of tracked files, command output, screenshots, response
exports and browser persistence. Reuse the granted token; setup does not require
rotation. The separate API playground keeps its connection in memory. Restarting
that playground loses its connection and does not configure the application
backend.

After updating the intended backend's ignored environment file, recreate that
backend to load its settings. Verify the course's source catalog: HeadHunter
should report `available` for Uzbekistan. `not_configured` means its application
settings are missing. The catalog does not probe the provider over the network.

O*NET uses versioned bulk files and needs no API credential. See
[O*NET catalog operations](onet-import.md) for validation, import, activation,
checksums and attribution. Keep historical releases referenced by analyses.

## Collection bounds

Only explicitly selected providers run. There is no automatic fallback to an
unselected source. The initial HeadHunter market is Uzbekistan (`host=hh.uz`,
`area=97`). Indeed is unavailable for Uzbekistan in the installed adapter;
LinkedIn retains the selected location without using an unsupported Indeed
country enumeration.

The default sample is 15 postings per query and provider from the previous
72 hours. The result cap accepts 1–100. Duplicate queries are combined. Source
collection allows at most eight concurrent tasks and two active HeadHunter
calls. HeadHunter uses a five-second connection timeout, a fifteen-second read
timeout, at most three attempts, and at most five seconds of total retry delay.
Access denials and CAPTCHA responses are reported without repeated auth attempts.

A small or empty sample is not a complete measure of market demand. Each source
retains its own status, counts and warnings. Teachers explicitly acknowledge
partial evidence before advancing; acknowledgement does not supply missing
posting support. Changing the source, market or occupation configuration after
collection requires a new analysis.

## Stored evidence and removal

Vacancy storage preserves the complete returned provider JSON, original
description, separately cleaned text, provider skill tags and original posting
URLs. Extraction context limits do not truncate the stored description. Teacher
evidence views render text and escaped JSON, never executable provider HTML.
Students receive approved evidence summaries and posting links, not arbitrary
provider payloads.

Repeated observations use provider-native identities where available. URL
fallbacks normalize scheme/host case and default ports while retaining path
case, query order and fragments. Matching title and company alone do not prove
two postings are the same job. Counts use distinct demand identities; merging
evidence does not add model-generated frequency estimates.

The repository's explicit content-removal operation removes raw JSON,
descriptions and tags for every stored copy of a provider posting, records a
reason and timestamp, and invalidates affected final reviews. A tombstone keeps
a subsequent fetch from restoring the removed content. Do not describe a
purged snapshot as full available evidence.

Removal also redacts copied source quotations from candidate history, approved
items, evidence bindings, reference display data and matching saved agent state.
IDs, original posting links, audit hashes and permitted derived competencies
remain. Saving an older state cannot restore a removed quotation. Graph cleanup
has a durable pending/error status and is retried separately from the committed
SQL removal; neither retry changes the teacher's approved targets.

No blanket retention interval is inferred from API access. Before unattended
collection, reconcile the granted research use and provider removal requirements
with the intended storage and processing. There is no scheduled collection or
automatic retention-policy assumption in this rollout.

## Teacher decisions and student continuity

Category selection means all current skills in that category, including hidden
rows. Individual exclusions persist through sorting, advice and reload. Later
candidates remain unselected. Recommendations are proposals; teachers decide
whether to apply them. If a retry removes or merges a previously chosen skill,
the unresolved decision remains visible after reload. Teachers explicitly review
and acknowledge those changes before confirming the shortlist; agent retries
cannot erase that decision history.

Saving a draft, confirming a shortlist for mapping, and approving the final
review are separate actions. Every newly approved skill and reviewed target
needs a genuine supporting posting from the selected sources in the same
analysis, with its original HTTP(S) link. An unrelated URL, O*NET reference or
neighboring merged skill does not qualify. An unsupported skill may remain in
the draft, but the whole final approval request is rejected if any proposed
skill lacks support.

O*NET importance, occupational level, observed posting frequency and quiz mastery
remain separate. Only equivalent reported descriptors supply sortable O*NET
ratings for the selected occupation. Missing, suppressed and not-relevant
values are not zero. Software examples retain their flags without fabricated
importance or level ratings.

The server associates extracted job competencies with the selected immutable
O*NET catalog. Complete label matches use case folding and collapsed whitespace;
they inspect every selected row before inference limits apply. Model-inferred
equivalent, broader or related associations are labelled context. They never
lend posting support to a separate O*NET candidate. That candidate needs its own
complete validated competency or provider-tag match, and the final mapped target
must independently pass the posting-evidence check.

Inferred context is bounded to 16 job observations and 200 catalog rows, sampled
across occupation and evidence-family groups. Batches contain at most eight
observations and 50 rows, with eight sequential calls per save, a 45-second call
timeout, no retries and at most two concurrent calls per process. Configured
model wait can total 360 seconds plus queue and scheduling time. Omitted rows,
failed calls and invalid outputs appear as partial-coverage warnings that need
teacher acknowledgement. Exact matches are not limited by these inference caps.

SQL records are authoritative; graph publication has its own status. A newly
introduced career skill with pending or failed projection is unavailable for
new student selection. Independently verified existing book/market offerings
remain usable while a new evidence attachment is pending or withdrawn; the
teacher review still reports the attachment's actual status. The server verifies
existing course relationships, never a client claim of legacy status. Stable
course references preserve target identity across analyses.
Existing student payloads, saved learning paths, resources and quiz mastery
remain supported. Withdrawal blocks new selections without deleting saved work.
Clearing the agent conversation removes its active pointer, not durable
evidence or previously approved offerings.

For course-owned career skills, current chapter mappings follow the union of
active, supported approvals. Remapping or withdrawing one analysis does not
remove a chapter still required by another active approval. Historical graph
edges remain available for saved work; new selections and prerequisite discovery
use only current mappings. Student selections record their authoritative chapter
IDs, and older saved selections are backfilled before a mapping is retired.
Bodyless recovery keeps that saved chapter selection. A deliberate deselection
and new selection can adopt the current mapping. Existing independent book and
legacy market mappings retain their ownership.

Successful publication completes the market gate and makes the prerequisite
review stale once for that approval revision. Open the course's prerequisite
review, regenerate, inspect the resulting edges and isolated skills, then approve
the graph before publishing the course. Repeating a successful recovery must not
invalidate a later prerequisite approval. Processing preserves all graph targets
bound to durable references, including existing book and market skills and
withdrawn offerings; ambiguous names may remain separate to preserve saved work.

To withdraw an existing offering, use **Prepare withdrawal** in the teacher
review and then **Withdraw approval** on the prepared server review. Preparation
does not publish or remove anything. The final action submits the current review
digest with an empty approved-candidate list. The teacher's visible draft remains
available, and other active approvals of the same skill are preserved.

The preparation endpoint is
`POST /courses/{course_id}/market-demand/skill-review/withdrawal-review`, with
the run ID and expected candidate/selection revisions. The final action uses
the existing `POST /courses/{course_id}/market-demand/integration-approval`.
Refresh after a stale-version response before preparing again. Withdrawal does
not require approving unrelated draft changes, but still requires ownership,
the current analysis and a current server-issued review. An empty initial
publication is not a withdrawal.

## Retry a saved approval

A failed graph projection does not undo the teacher's SQL approval. After
restoring the configured graph, retry the exact course, analysis run and approved
revision from the saved review:

```bash
docker exec lab_tutor_backend /app/.venv/bin/python scripts/project_market_skill_evidence.py --course-id COURSE_ID --run-id RUN_UUID --revision APPROVED_REVISION
```

Replace the three placeholders with the recorded values. This command reads
committed SQL intent and validates its evidence; it cannot approve a draft or
accept a caller-provided graph target. Its JSON reports `projection_status`, and
it exits successfully only for `projected`. Repeating a successful projection
uses the same reference, evidence and target identities. Check the refreshed
teacher review and student bank before treating the offering as ready.

`--test-graph` is reserved for the explicit disposable graph configuration used
by the integration tests. It refuses another graph hostname or database. Keep
its credentials in the protected test environment, never in this runbook.

To retry pending provider-content cleanup for one course:

```bash
docker exec lab_tutor_backend /app/.venv/bin/python scripts/project_market_skill_evidence.py --course-id COURSE_ID --redact-only
```

This mode needs no approval revision or run ID. It reports the actual cleanup
status and exits successfully only for `projected`. Normal approval projection
also drains pending cleanup first. A failed cleanup remains retryable; unrelated
active evidence, saved learning paths and resource identities are retained.

## Verification and rollout

Run backend/frontend checks in Docker and serialize PostgreSQL test processes:
the existing fixtures truncate the test database. Never point them at the main
application database. Graph acceptance uses an explicitly configured disposable
Neo4j instance and must not fall back to the application's graph settings.

Browser acceptance runs headlessly with a disposable teacher/course and a
separate test backend. Route both normal API requests and SSE chat requests to
that backend. A passing build does not verify teacher confirmation, publication,
student selection, withdrawal or saved-path recovery; exercise those actions and
inspect their persisted readback.

Keep fixture-driven acceptance separate from a live provider check. A limited
authenticated HeadHunter fetch verifies native IDs, original URLs, full
descriptions and provider selection without triggering live LLM processing or
graph publication. Record exactly which checks used synthetic external
responses. Activate the validated O*NET release only after integration
acceptance in the intended environment.

## Local acceptance record — 10 October 2026

The controlled integration completed 11 headless browser scenarios (43 checks),
three resource failure/recovery checks and direct SQL/graph readback. Providers,
search and language-model outputs were synthetic external fixtures; application
routes, auth, ToolNode execution, PostgreSQL, Neo4j, grading and persistence were
real. The official O*NET 31.0 catalog is now active in the main local database.
Direct live backend HeadHunter ingestion still awaits the protected credential
location and identifying User-Agent. The existing playground connection remains
separate and preserved.

Acceptance found a source-outcome persistence defect with `autoflush=False`.
Final outcomes are now assigned after the candidate-manifest refresh and committed
with coverage. A fresh-session SQL regression covers both autoflush settings.
The fresh acceptance database also required checkpoint migration initialization
before serving authenticated requests: existing lazy concurrent-index setup can
wait on a transaction opened by the same request. This startup issue was not
changed by the integration.

See the HTML report for screenshots, individual results, prior timeout limits and
the distinction between controlled workflow checks and the two earlier live
HeadHunter samples. No scheduled collection or live model-quality claim is made.

## Local live connection — 11 October 2026

The existing application token and the already configured playground User-Agent
were saved to the Git-ignored root `.env` with mode 0600. Only the local backend
was recreated to load them. Its production source-service factory reported
HeadHunter available for Uzbekistan and fetched two live Python vacancies
(72-hour window, result cap two), with no provider warnings. Original URLs,
native IDs, complete HTML, cleaned text and provider tags matched the raw
payloads. The HTML report links to credential-free verification metadata.
This does not assert that Azure or GitHub Secrets have been configured.

Both real records also passed repository SQL save/readback in a dedicated
transaction. A temporary disabled teacher and course used explicit negative IDs
to avoid sequence changes. All temporary user/course/run/snapshot rows were
rolled back, with absence verified from a fresh session. This checks database
serialization; it is not a committed course analysis or live model/graph run.
