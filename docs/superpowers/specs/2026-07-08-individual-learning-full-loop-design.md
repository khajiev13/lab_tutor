# Individual Learning Full Loop Design

Date: 2026-07-08
Status: Approved for written design review

## Purpose

Lab Tutor should support individual users who are not part of an organization. An
individual user registers with the `individual` role, uploads a CV, reviews an
AI-extracted profile, chooses or edits target job titles, selects interested job
postings and market skills, then receives personalized readings, videos, and
questions.

The first version should implement the full loop while preserving the existing
student learning-path semantics where they already fit:

1. register as an individual
2. upload PDF or DOCX CV
3. extract CV profile and CV skills
4. pause for human review of profile and target job titles
5. fetch jobs for the target titles
6. extract market skills from job postings
7. score CV coverage against job requirements
8. pause for human selection of interested jobs and learning skills
9. persist selected market skills
10. generate personalized learning resources
11. show individual dashboard, profile, job matches, skill selection, and learning path

## Non-Goals

- Do not use kg-gen in the production path.
- Do not create `INTERESTED_POSITION` or position nodes in Neo4j.
- Do not make CV skills selectable for learning in the first version.
- Do not reuse the course model by creating hidden personal courses.
- Do not require a teacher, class, enrollment, book, or course chapter for individual learning.
- Do not write generic or dynamic graph triples from CV extraction into the canonical graph.

## Existing Project Findings

The existing student learning path already has the right job-posting and skill
selection vocabulary:

- Students are linked directly to job postings with `INTERESTED_IN`.
- Job-derived skills are `(:SKILL:MARKET_SKILL)` nodes.
- Market skills point back to job postings with `SOURCED_FROM`.
- Students choose learning inputs with `SELECTED_SKILL` relationships to
  `MARKET_SKILL` nodes.
- The frontend groups the market skill bank by job posting and lets students
  select all skills from a posting or fine-tune individual skill chips.

The relevant code paths are:

- `backend/app/modules/student_learning_path/neo4j_repository.py`
  - `_MARKET_SKILL_BANK_QUERY`
  - `select_skills`
  - `select_job_postings`
  - `get_selected_job_postings`
  - `get_student_skill_banks`
- `frontend/src/features/student-learning-path/api.ts`
  - `StudentSkillBankJobPosting`
  - `SkillBanksResponse`
  - `selectJobPostings`
  - `buildLearningPath`
- `frontend/src/features/student-learning-path/pages/StudentLearningPathPage.tsx`
  - job posting selection
  - draft skill selection
  - selected skill build handoff

Live Neo4j inspection was attempted through the MCP server and through the
backend Python virtualenv. Both failed from the local session with routing or
TLS/Bolt handshake errors. The design therefore follows the application Cypher
and frontend types as the source of truth.

## Recommended Approach

Use a dedicated individual-learning product boundary while reusing lower-level
project primitives:

- auth and role infrastructure from the existing auth module
- Azure blob upload/download from `app/providers/storage.py`
- PDF extraction patterns from curricular alignment PDF extraction
- DOCX text extraction from existing course/document utilities
- job fetching and market skill extraction from Market Demand Analyst
- resource generation from the existing resource pipeline
- skill-bank UI behavior from the student learning path

This avoids hidden courses while still keeping the familiar student selection
experience.

## Role and Auth Model

Add `individual` as a first-class user role.

Backend role enum:

```python
class UserRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    INDIVIDUAL = "individual"
```

Neo4j user upsert should create:

```cypher
(:USER:INDIVIDUAL {id: $user_id})
```

Registration should offer three choices:

- student
- teacher
- individual

After registration and first login, individual users should be routed to the
individual onboarding flow until their CV profile has reached a usable state.

## Backend Module

Create a new module:

```text
backend/app/modules/individual_learning/
  models.py
  schemas.py
  repository.py
  neo4j_repository.py
  service.py
  routes.py
  graph.py
  cv_extractor.py
  job_matcher.py
```

Responsibilities:

- SQL persistence for individual profiles, CV documents, extraction runs, job
  search runs, match runs, and learning runs
- Neo4j persistence for individual profile graph facts
- CV parsing and structured extraction
- LangGraph orchestration with human-in-the-loop interrupts
- job fetching and market skill extraction for selected target titles
- market skill bank assembly for the individual user
- selected skill persistence
- individual learning path reads and resource generation handoff

## SQL Data Model

Use SQL for durable workflow state, auditability, and recovery. Neo4j should
store the canonical graph projection.

Recommended tables:

```text
individual_profiles
  id
  user_id
  onboarding_status
  preferred_country
  preferred_location
  target_titles_json
  reviewed_at
  created_at
  updated_at

cv_documents
  id
  user_id
  blob_path
  original_filename
  content_type
  content_hash
  size_bytes
  status
  error_message
  uploaded_at
  processed_at

cv_extraction_runs
  id
  cv_document_id
  user_id
  model_provider
  model_name
  raw_text_hash
  extracted_profile_json
  target_title_suggestions_json
  confidence_summary_json
  status
  error_message
  created_at
  completed_at

individual_job_search_runs
  id
  user_id
  target_titles_json
  country
  location
  status
  fetched_jobs_json
  selected_posting_urls_json
  error_message
  created_at
  completed_at

individual_job_match_runs
  id
  user_id
  job_search_run_id
  scores_json
  skill_gap_json
  status
  created_at
  completed_at

individual_learning_runs
  id
  user_id
  selected_skill_names_json
  status
  run_id
  error_message
  created_at
  completed_at
```

JSON columns keep the first version flexible while the graph projection remains
explicit and typed.

## Neo4j Data Model

Use existing graph semantics wherever possible.

Individual CV graph:

```cypher
(:USER:INDIVIDUAL)-[:HAS_CV]->(:CV_DOCUMENT)
(:USER:INDIVIDUAL)-[:HAS_SKILL]->(:SKILL:CV_SKILL)
```

Individual job interest and learning selection:

```cypher
(:USER:INDIVIDUAL)-[:INTERESTED_IN]->(:JOB_POSTING)
(:SKILL:MARKET_SKILL)-[:SOURCED_FROM]->(:JOB_POSTING)
(:USER:INDIVIDUAL)-[:SELECTED_SKILL]->(:SKILL:MARKET_SKILL)
```

CV skills and market skills can share the base `SKILL` label while using subtype
labels to distinguish purpose:

```cypher
(:SKILL:CV_SKILL)
(:SKILL:MARKET_SKILL)
(:SKILL:BOOK_SKILL)
```

Relationship properties carry user-specific context:

```cypher
(:USER:INDIVIDUAL)-[:HAS_SKILL {
  source: "cv",
  confidence: 0.91,
  evidence: "...",
  cv_document_id: "...",
  extraction_run_id: "..."
}]->(:SKILL:CV_SKILL)

(:USER:INDIVIDUAL)-[:INTERESTED_IN {
  selected_at: datetime(),
  source: "individual_job_search",
  job_search_run_id: "..."
}]->(:JOB_POSTING)

(:USER:INDIVIDUAL)-[:SELECTED_SKILL {
  selected_at: datetime(),
  source: "individual_market_skill",
  job_search_run_id: "...",
  match_run_id: "..."
}]->(:SKILL:MARKET_SKILL)
```

Do not create position nodes. Target job titles are search inputs and run
metadata. Once jobs are fetched, the graph links to concrete `JOB_POSTING`
nodes.

## CV Extraction

Supported upload types:

- PDF
- DOCX

Pipeline:

1. Upload the CV to Azure using a user-scoped blob path.
2. Create a `cv_documents` row with status `uploaded`.
3. Extract text using the file type specific extractor.
4. Run a structured LLM extraction into Pydantic schemas.
5. Store the raw structured extraction and confidence summary in SQL.
6. Pause for user review before writing or finalizing user-facing graph facts.

Structured extraction should include:

- contact/profile summary where appropriate
- skills
- work experience
- projects
- education
- certifications
- tools and technologies
- languages
- industries
- seniority signals
- target job title suggestions
- evidence snippets for extracted skills
- confidence per major field

PII should remain user-scoped. Avoid putting sensitive profile details on shared
canonical nodes.

## LangGraph Workflow and HITL

Use a persisted LangGraph workflow with interrupts and stable `thread_id`.

Recommended graph:

```text
extract_cv
  -> suggest_target_roles
  -> interrupt: review_profile_and_roles
  -> search_jobs
  -> extract_job_requirements
  -> score_job_matches
  -> compute_skill_gaps
  -> interrupt: choose_jobs_and_skills
  -> persist_selected_market_skills
  -> build_learning_path
  -> generate_readings_videos_questions
  -> finalize_dashboard
```

Interrupt payloads must be JSON-serializable.

Human-in-the-loop pauses:

1. `review_profile_and_roles`
   - show extracted CV profile
   - show CV skills with evidence and confidence
   - show suggested target titles
   - allow the user to accept, remove, reorder, or add target titles

2. `choose_jobs_and_skills`
   - show ranked job postings
   - show market skills grouped by job posting
   - show job-fit and gap evidence
   - allow direct `INTERESTED_IN` job selection
   - allow `SELECTED_SKILL` market skill selection

Graph writes before interrupts must be idempotent upserts. Non-idempotent audit
records and final relationship writes should happen after the relevant resume.

## Job Search and Market Skills

The user can add several target job titles. The system can also recommend titles
from the CV.

Target titles feed job search. They should not become Neo4j nodes in the first
version.

For fetched jobs:

```cypher
MERGE (:JOB_POSTING {url: $url})
```

For market skills:

```cypher
MERGE (:SKILL:MARKET_SKILL {name: $name})
MERGE (market_skill)-[:SOURCED_FROM]->(job_posting)
```

The individual skill bank should be assembled from the user's interested or
candidate job postings:

```cypher
MATCH (u:USER:INDIVIDUAL {id: $user_id})-[:INTERESTED_IN]->(jp:JOB_POSTING)
MATCH (ms:MARKET_SKILL)-[:SOURCED_FROM]->(jp)
RETURN jp, collect(ms)
```

During pre-selection review, the UI may show candidate job postings before
`INTERESTED_IN` is persisted, but the persisted graph should use the same direct
relationship as students.

## Skill Selection

Only `MARKET_SKILL` nodes are selectable for individual learning in v1.

CV skills are used for:

- profile understanding
- matching evidence
- gap analysis
- showing what the user already has

CV skills are not selectable because they represent current capability, not
learning targets.

Selection write:

```cypher
MATCH (u:USER:INDIVIDUAL {id: $user_id})
MATCH (sk:SKILL:MARKET_SKILL {name: $skill_name})
MERGE (u)-[r:SELECTED_SKILL]->(sk)
ON CREATE SET r.selected_at = datetime(), r.source = "individual_market_skill"
```

The individual frontend should reuse the student pattern:

- posting cards grouped by `JOB_POSTING`
- "select all skills" at posting level
- skill chips for fine-tuning
- draft selection state before build
- selection count validation
- build button that persists selections and starts generation

## Learning Resource Generation

The existing resource pipeline expects selected skills and generates readings,
videos, and questions. For individuals, the pipeline should accept selected
`MARKET_SKILL`s without requiring course chapters.

The first version should group learning path output by selected skill:

```text
Selected Skill
  readings
  videos
  questions
  status/progress
```

This avoids creating fake chapters. Later versions can add grouping by job title,
role, or learning module once there is evidence that users need that structure.

## API Surface

Recommended routes:

```text
POST /individual-learning/cv
POST /individual-learning/graph/start
POST /individual-learning/graph/resume
GET  /individual-learning/profile
GET  /individual-learning/jobs
POST /individual-learning/interested-jobs
DELETE /individual-learning/interested-jobs
GET  /individual-learning/skill-banks
POST /individual-learning/select-skills
DELETE /individual-learning/select-skills
POST /individual-learning/build
GET  /individual-learning/path
GET  /individual-learning/runs/{run_id}/events
```

Route guards should require `UserRole.INDIVIDUAL`.

## Frontend UI

Add a dedicated individual area:

```text
/individual/onboarding
/individual/profile
/individual/jobs
/individual/skills
/individual/learning-path
```

Individual sidebar:

```text
Dashboard
CV Profile
Job Matches
Skill Selection
Learning Path
Career Agent
```

Screens:

1. Onboarding
   - upload PDF/DOCX CV
   - show extraction progress
   - show retry states

2. Profile Review
   - extracted profile sections
   - CV skills with evidence and confidence
   - recommended target job titles
   - user-added job titles
   - approve/resume graph button

3. Job Matches
   - job postings grouped by target title/search term
   - match score and gap summary
   - interested job selection

4. Skill Selection
   - market skills grouped by job posting
   - select all skills for posting
   - fine-tune skill chips
   - show CV evidence where the user already has partial coverage
   - build learning path

5. Learning Path
   - grouped by selected market skill
   - readings/videos/questions
   - resource generation progress

## Error Handling

- CV upload failure: keep the user on upload step and allow retry.
- CV parsing failure: preserve the uploaded file and allow rerun.
- Low extraction confidence: show warning in profile review.
- Job fetch failure: preserve target titles and allow retry or edit.
- Skill extraction failure for a job: show partial job results and mark the job as incomplete.
- Resource generation failure: preserve selected skills and show partial learning path.
- Neo4j unavailable: keep SQL run state and return a clear retryable error.
- Interrupt resume mismatch: require same `thread_id` and show a recoverable state message.

## Security and Privacy

- CV blob paths must be user-scoped.
- CV files must not be stored in public Azure containers.
- Do not expose raw CV text in broad logs.
- Store evidence snippets only where useful for review and explainability.
- Keep PII on user-owned records and relationships, not shared canonical nodes.
- Generated graph visualizations, if added later, must be authenticated and
  sanitized. Do not publish CV-derived HTML snapshots publicly.

## Testing

Backend tests:

- register accepts `individual`
- `USER:INDIVIDUAL` graph upsert works
- PDF CV upload and extraction path works
- DOCX CV upload and extraction path works
- CV extraction validates into structured schemas
- CV skills write as `SKILL:CV_SKILL`
- CV skills are not accepted by individual skill selection
- job postings write as `JOB_POSTING`
- market skills write as `SKILL:MARKET_SKILL`
- individual `INTERESTED_IN` links user directly to `JOB_POSTING`
- individual `SELECTED_SKILL` links user directly to `MARKET_SKILL`
- skill bank returns market skills grouped by job posting
- LangGraph interrupt/resume preserves state
- resource generation starts from selected individual market skills

Frontend tests:

- individual registration option appears
- individual users route to onboarding after first login
- CV upload accepts PDF and DOCX
- profile review allows target title edits
- jobs page allows interested job selection
- skill selection mirrors student job-posting skill selection
- CV skills are visible but not selectable for learning
- learning path renders selected market skills and generated resources

Verification commands should follow project rules:

```text
docker exec lab_tutor_backend sh -lc 'cd /app && /app/.venv/bin/ruff check . && /app/.venv/bin/ruff format --check .'
docker exec lab_tutor_frontend sh -lc 'cd /app && npm run lint && npm run build'
```

Targeted tests should be added for the new backend module and individual
frontend routes as implementation lands.

## Rollout Notes

This design is large enough to implement in staged pull requests:

1. auth role and graph label support
2. CV upload and extraction
3. profile review with LangGraph interrupt
4. individual job search and job matching
5. individual skill bank and selection
6. individual learning resource generation
7. dashboard and career agent polish

Each stage should leave the app in a coherent state and avoid changing student
or teacher behavior except where shared primitives are intentionally generalized.
