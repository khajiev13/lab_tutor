## Plan: Teacher Content Recommendations via Book Gap Analysis

### TL;DR

Add a **`recommendations/`** sub-module inside `curricularalignmentarchitect/` that uses the **already-computed `ChapterAnalysisSummary`** data (book concepts with `sim_max` scores against course concepts) to generate an LLM-driven recommendation report. The report advises teachers on what to add/improve in their uploaded documents, using the book as source of truth. This is exposed as a new API endpoint and designed so future agents (pedagogy, assessment) can plug into the same schema. No new DB tables needed for V1 — all input data already exists in `ChapterAnalysisSummary` JSON blobs + `CourseConceptCache` + Neo4j `TEACHER_UPLOADED_DOCUMENT` nodes.

### Key Insight: We Already Have Everything We Need

The `ChapterAnalysisSummary` already stores:
- **`book_unique_concepts_json`**: every book concept with its `sim_max` against the course. Concepts with **low `sim_max`** (< 0.35 = novel) are concepts the book covers that the teacher's documents do **not**. This is the core signal for "you should add this."
- **`course_coverage_json`**: every course concept's best match in the book. Low `sim_max` here means a teacher concept has weak book support.
- **`chapter_details_json`**: full chapter → section → concept structure with skills.
- **`topic_scores_json`**: per-document topic similarity scores.

The teacher's documents are in Neo4j as `TEACHER_UPLOADED_DOCUMENT` nodes with `MENTIONS` → `CONCEPT` relationships (305 concepts, 38 documents, 352 mentions for the "Big Data" class).

**Steps**

1. **Create `recommendations/` sub-module** inside `backend/app/modules/curricularalignmentarchitect/`
   - `recommendations/__init__.py` — empty
   - `recommendations/schemas.py` — shared recommendation DTOs
   - `recommendations/repository.py` — data fetching (from SQL + Neo4j)
   - `recommendations/service.py` — orchestration: gather data → format → call LLM agent → return structured result
   - `recommendations/prompts.py` — LLM prompt for book gap analysis agent
   - `recommendations/agents/__init__.py` — agent registry
   - `recommendations/agents/book_gap_analysis.py` — first agent: uses `ChapterAnalysisSummary` data + Neo4j teacher docs

2. **Define shared `RecommendationItem` / `RecommendationReport` schemas** in `recommendations/schemas.py`
   - `RecommendationCategory` enum: `missing_concept`, `insufficient_coverage`, `suggested_skill`, `structural`
   - `RecommendationPriority` enum: `high`, `medium`, `low`
   - `RecommendationItem`: `category`, `priority`, `title`, `description`, `rationale`, `book_evidence` (chapter + section + text_evidence), `affected_teacher_document`, `suggested_action`
   - `RecommendationReport`: `source` (e.g. `book_gap_analysis`), `course_id`, `book_title`, `summary`, `recommendations[]`
   - `RecommendationResponse`: wraps one or more `RecommendationReport`s (future: multiple agents)

3. **Build `repository.py`** — two data-fetching tasks:
   - **From PostgreSQL**: Load the pre-computed `ChapterAnalysisSummary` for a given `run_id` + `selected_book_id`. Parse `book_unique_concepts_json` (filter for `sim_max < NOVEL_THRESHOLD` → **novel concepts the teacher is missing**), `course_coverage_json` (teacher's weakly-covered concepts), `chapter_details_json` (skills + structure).
   - **From Neo4j**: Fetch teacher's uploaded documents for the course in a single query that returns per-document context (summary, keywords, topic) alongside its mentioned concepts:
     ```cypher
     MATCH (c:CLASS {id: $course_id})-[:HAS_DOCUMENT]->(d:TEACHER_UPLOADED_DOCUMENT)
     OPTIONAL MATCH (d)-[m:MENTIONS]->(concept:CONCEPT)
     RETURN d.id AS doc_id,
            d.topic AS topic,
            d.summary AS summary,
            d.keywords AS keywords,
            d.source_filename AS source_filename,
            collect(concept.name) AS concept_names
     ORDER BY d.topic
     ```
     This gives the LLM rich per-document context: what the teacher's document is about (summary + keywords) **and** the concept names it covers — all in one efficient query. We skip `definition` and `text_evidence` from the `MENTIONS` relationship since the book side already provides concept descriptions, and the document `summary` + `keywords` give sufficient coverage context.
   - Access Neo4j via `app.state.neo4j_driver` (already available — used by existing extraction code).

4. **Build the Book Gap Analysis agent** in `agents/book_gap_analysis.py`
   - Input: structured data from repository (novel book concepts, teacher doc summaries, chapter details with skills)
   - **Pre-filter before LLM**: Only send novel/low-overlap concepts (sim_max < 0.55) to the LLM, grouped by chapter. Include teacher doc topics for context. This keeps the prompt focused and token-efficient.
   - LLM prompt: "Given these book concepts that are NOT covered in the teacher's materials, and given the teacher's current document topics, generate actionable recommendations for what the teacher should add or improve."
   - Output: `RecommendationReport` via structured output (`with_structured_output`)
   - Use existing `_build_llm()` pattern from `chapter_extraction/nodes.py` for LLM construction.

5. **Build `service.py`** — the orchestrator
   - `RecommendationService` takes `db: Session` and `neo4j_driver`
   - `generate_book_gap_recommendations(course_id, run_id, selected_book_id)` → fetches data from repo, calls agent, returns `RecommendationReport`
   - `get_all_recommendations(course_id, run_id, selected_book_id)` → runs all registered agents (just book_gap for V1), returns `RecommendationResponse`
   - Factory function `get_recommendation_service(db, neo4j_driver)` for DI

6. **Add API route** in a new `api_routes/recommendations.py`
   - `POST /book-selection/courses/{course_id}/analysis/{run_id}/books/{selected_book_id}/recommendations` → run recommendation generation (LLM call takes time)
   - Uses `register_routes(router)` pattern matching existing sub-routes
   - Auth: `require_role(UserRole.TEACHER)` (same as all other endpoints)
   - Validates that `ChapterAnalysisSummary` exists for the given run + book (must run chapter scoring first)

7. **Register the new route** in `api_routes/__init__.py`
   - Import and call `register_recommendations_routes(router)`

### Why This Design

- **No new DB tables for V1** — recommendations are generated on-demand from existing `ChapterAnalysisSummary` data + Neo4j. We can add persistence later if we want to cache reports.
- **Reuses existing scoring infrastructure** — the `sim_max` scores in `book_unique_concepts_json` already classify concepts as novel/overlap/covered. We just need to feed the novel ones to an LLM for human-readable advice.
- **Plugin architecture for future agents** — the `RecommendationResponse` wraps multiple `RecommendationReport`s, each from a different `source`. Adding a pedagogy agent or assessment agent just means creating a new file in `agents/` and registering it in the service.
- **Fits the existing module structure** — lives inside `curricularalignmentarchitect` as a sub-module, uses the same `register_routes` pattern, same auth, same DI.

### Data Flow

```
ChapterAnalysisSummary (SQL)      Neo4j TEACHER_UPLOADED_DOCUMENT
        ↓                                    ↓
  novel concepts (sim_max < 0.35)    teacher's current topics + concepts
  weak concepts (0.35 ≤ sim < 0.55)
  skills from book chapters
        ↓                                    ↓
        └────────── Repository ──────────────┘
                        ↓
               Service (formats data)
                        ↓
              Book Gap Analysis Agent (LLM)
                        ↓
              RecommendationReport (structured output)
                        ↓
                  API Response → Frontend
```

### Verification

1. **Unit test**: Mock the `ChapterAnalysisSummary` data and Neo4j response, verify the agent produces valid `RecommendationReport` output
2. **Integration test**: Against local PostgreSQL + Neo4j — `POST /book-selection/courses/1/analysis/{run_id}/books/{book_id}/recommendations` → verify 200 with structured recommendations
3. **Manual**: Run after agentic extraction + chapter-scoring completes → check that novel book concepts appear as recommendation items

### Decisions

- **No SSE streaming for V1** — the recommendation LLM call is a single-shot (not a multi-step pipeline), so a regular POST returning JSON is sufficient. SSE can be added later if the multi-agent pipeline takes too long.
- **No DB persistence for V1** — recommendations are ephemeral. If the teacher wants to re-generate after updating their documents, they just POST again. Caching/persistence can be added later by adding a `recommendation_reports` table.
- **POST not GET** — because this triggers an LLM call (side effect), POST is more appropriate even though it's conceptually "getting" recommendations.
- **Pre-filter before LLM** — instead of sending ALL book concepts to the LLM, we pre-filter using the already-computed `sim_max` thresholds. This reduces token cost and makes the LLM output more focused.
