# Plan: Textual Resource Analyst — Notebook Prototype

Build a prototype notebook that, given course skills (BOOK_SKILL + MARKET_SKILL), finds the best online reading materials to teach each skill. Uses a **3-stage hybrid pipeline: query generation → multi-source search → embedding filter + LLM rubric**.

---

## What We Know About Each Skill (Input)

| Attribute | BOOK_SKILL | MARKET_SKILL |
|-----------|------------|--------------|
| Name + description | ✓ | ✓ |
| Chapter context (title, summary) | ✓ | ✓ (target_chapter) |
| Linked concepts (names, definitions, text_evidence) | ✓ via `REQUIRES_CONCEPT` | ✓ via `REQUIRES_CONCEPT` |
| Category (database, cloud, ML...) | — | ✓ |
| Demand data (frequency, demand_pct, priority) | — | ✓ |
| Job evidence snippets | — | ✓ via `SOURCED_FROM` → `JOB_POSTING` |
| Course level (bachelor/master/PhD) | ✓ (from course) | ✓ |

This rich context becomes the **skill profile** — the signal we use to generate queries and evaluate reading quality.

---

## Algorithm: 3-Stage Hybrid Pipeline

**Stage 1 — Context + Query Generation**: For each skill, assemble a profile (name + concepts + chapter + course level), then LLM generates 4-6 diverse queries targeting different resource types (tutorial, docs, blog, textbook chapter).

**Stage 2 — Multi-Source Search + Embedding Filter**: Fan-out queries across **Tavily + DuckDuckGo + Serper** in parallel. Deduplicate by URL. Then embed the skill profile and all result snippets with `text-embedding-v4`, keep **top-15** by cosine similarity (fast coarse filter).

**Stage 3 — LLM Evaluation + Ranking**: For top-15 candidates, LLM scores using a structured 5-criterion rubric:

| Criterion | Weight | What it measures |
|-----------|--------|------------------|
| **Recency** | 0.25 | Age computed dynamically as `current_year - published_year` (use `datetime.now().year`). ≤1yr = 1.0, 1-2yr = 0.8, 2-3yr = 0.6, 3-5yr = 0.3, >5yr = 0.1. Readings MUST be recent — outdated material is actively harmful in fast-moving fields |
| **Relevance** | 0.25 | Matches skill + covers linked concepts |
| **Pedagogical Quality** | 0.20 | Teaches with examples, exercises, clear explanations |
| **Depth** | 0.15 | Appropriate for course level (bachelor/master/PhD) |
| **Source Quality** | 0.15 | Official docs > known blogs > personal blogs > content farms |

**Recency enforcement**: The current year is obtained dynamically via `datetime.now().year` — never hardcoded. Query generation appends year filters (e.g., `after:{current_year - 1}`). Search results without a discoverable publication date are penalized. The LLM prompt explicitly instructs: *"Prefer the most recent resource. Between two equally relevant readings, always pick the newer one."*

Select **top 3-5 per skill** with diversity constraint (≥2 different resource types). Map each reading to concepts it covers.

---

## Steps

### Phase A: Setup & Data Loading (Cells 1-3)
1. **Imports & config** — Neo4j driver, LLM, embeddings, search tools. Reuse patterns from `backend/app/modules/curricularalignmentarchitect/book_selection/tools.py`
2. **Load curriculum from Neo4j** — skills + concepts + chapters. Reuse query patterns from MDA tools.py (`list_chapters`, `get_chapter_details`)
3. **Build skill profiles** — concatenate all context per skill

### Phase B: Query Generation (Cell 4)
4. **LLM generates 4-6 queries per skill**, following CAA's `generate_queries` pattern in `backend/app/modules/curricularalignmentarchitect/book_selection/nodes.py`. Queries tailored by resource type (tutorial, docs, blog, textbook chapter). **Each query includes a dynamic recency hint** using `datetime.now().year` (e.g., `f"{current_year} tutorial"`, `f"after:{current_year - 1}"`)

### Phase C: Multi-Source Search (Cells 5-6)
5. **Parallel search**: Tavily + DDG + Serper per query (`ThreadPoolExecutor`). Serper already integrated at `backend/app/modules/curricularalignmentarchitect/service.py` via `GoogleSerperAPIWrapper`
6. **URL dedup + blacklist filter** — normalize URLs (strip params, www), remove paywalled/low-quality domains

### Phase D: Embedding Filter (Cell 7)
7. **Embed skill profiles + snippets** via `backend/app/modules/embeddings/embedding_service.py`. Cosine similarity → keep top-15

### Phase E: LLM Evaluation (Cells 8-9)
8. **Structured scoring** with 5-criterion rubric (Pydantic output model). Optionally fetch full content via Tavily `include_raw_content`
9. **Weighted ranking + diversity selection + concept mapping**

### Phase F: Storage (Cells 10-11)
10. **Display results** for teacher review (HITL point)
11. **MERGE `READING` nodes in Neo4j** + `HAS_READING` and `COVERS_CONCEPT` edges

---

## Proposed Neo4j Schema

### New Node: `READING`
| Property | Type | Description |
|----------|------|-------------|
| `url` | string (UNIQUE) | Canonical URL |
| `title` | string | Resource title |
| `source_domain` | string | e.g., "realpython.com" |
| `snippet` | string | ~500 char summary |
| `resource_type` | string | tutorial \| documentation \| blog \| textbook_chapter |
| `published_date` | string | ISO date or year (best-effort extraction from content) |
| `relevance_score` | float | 0-1 |
| `pedagogy_score` | float | 0-1 |
| `depth_score` | float | 0-1 |
| `source_quality_score` | float | 0-1 |
| `recency_score` | float | 0-1 |
| `final_score` | float | 0-1 weighted composite |
| `source_agent` | string | 'textual_resource_analyst' |
| `created_at` | datetime | insertion timestamp |

### New Relationships
- `(SKILL)-[:HAS_READING]->(READING)` — Skill teaches via this reading
- `(READING)-[:COVERS_CONCEPT]->(CONCEPT)` — Reading covers these concepts

---

## Verification
1. Run on 2-3 sample skills → verify query diversity
2. Compare Tavily vs DDG vs Serper results → verify dedup
3. Check embedding filter ranks relevant above irrelevant
4. Manually validate 5-10 LLM scores against human judgment
5. **Verify recency bias** — top-ranked readings should overwhelmingly be from the last 1-2 years
6. Neo4j query: `MATCH (s:SKILL)-[:HAS_READING]->(r)-[:COVERS_CONCEPT]->(c) RETURN s.name, r.title, r.published_date, collect(c.name)`
7. Run twice → verify idempotency (no duplicate nodes)

---

## Decisions Made
- **Granularity**: Readings linked to skills AND cross-referenced to concepts (both)
- **Resource types**: Tutorials, official docs, blogs, free textbook chapters (no papers/videos yet)
- **Search engines**: Tavily + DuckDuckGo + Serper (all already available in codebase)
- **HITL**: Optional review step before Neo4j write
- **Scope**: Notebook prototype only — no FastAPI routes or frontend yet
- **Recency priority**: Recency weight = 0.25 (tied with Relevance as highest). Year computed dynamically via `datetime.now().year` — never hardcoded. Queries include year filters. Outdated material actively penalized

## Further Considerations
1. **Content fetch depth** — Fetch full page content for all 15 candidates or only top-5 after snippet scoring? *Recommendation: all 15 — quality gain justifies cost for a course-level operation*
2. **Rate limiting** — `ThreadPoolExecutor(max_workers=5)` with delays between engine calls, matching CAA pattern
3. **Serper vs Google Scholar** — Start with Serper; add Scholar later if academic papers become a resource type
