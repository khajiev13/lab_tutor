## Plan: Backend-Driven Extraction Jobs

Move extraction into a backend “job” workflow: the teacher clicks Extract → backend creates an `extraction_jobs` row (`queued`) → a worker processes it (`running`) → writes artifacts + Neo4j (`succeeded/failed`). While `queued|running`, block delete/overwrite of the affected uploads by checking DB “locks” in the upload/delete endpoints. Prefer a real queue (Redis + RQ/Celery/Arq) over in-process tasks for durability and progress.

### Steps
1. Add persistent upload records: create `course_files` table and write to it from `backend/app/routes/course_routes.py` upload flow.
2. Add job state: create `extraction_jobs` (and optionally `extraction_job_events`) in `backend/app/models.py` + schemas in `backend/app/schemas.py`.
3. Add extraction endpoints: implement `POST /courses/{course_id}/extractions` and `GET /extractions/{job_id}` in a new router under `backend/app/routes/`, enforcing teacher ownership via `backend/app/auth.py`.
4. Enforce immutability: in upload/delete endpoints, refuse changes when a related job is `queued|running` (return `409`); also stop Blob overwrite by switching to unique blob names in `backend/app/services/azure_blob_service.py`.
5. Run jobs in a worker: add a separate worker process/container that imports `knowledge_graph_builder` and calls `LangChainCanonicalExtractionService.compress_and_extract_concepts` from `knowledge_graph_builder/services/extraction_langchain.py`, updating `extraction_jobs` progress and storing artifacts (Blob or local).
6. Scope Neo4j writes per course: update ingestion to tag nodes/edges with `course_id` (and query by it) inside the KG insert path (e.g., `knowledge_graph_builder/scripts/ingest_ready_data.py`) to avoid cross-course contamination.

### Further Considerations
1. “Agents” vs pipeline: start with deterministic pipeline; add agents (LangGraph) only if you need tool-using multi-step reasoning beyond extraction+linking.
2. Queue choice: MVP `BackgroundTasks` (fast) vs Redis queue (durable/retry/progress); pick based on whether restarts must not lose jobs.
3. UI updates: polling `GET /extractions/{job_id}` is simplest; SSE/event log is nicer if you want live progress.
