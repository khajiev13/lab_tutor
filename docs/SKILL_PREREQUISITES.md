# Skill Prerequisite Graph — Architecture & Design Document

> **Module**: `backend/app/modules/curricularalignmentarchitect/skill_prerequisites/`
> **Pattern**: LangGraph batch pipeline — embed → deduplicate → cluster → LLM judgment → DAG enforcement
> **Trigger**: `POST /book-selection/courses/{course_id}/skill-prerequisites/build` (SSE stream)

---

## 1. Purpose

The Skill Prerequisites pipeline builds a **directed prerequisite graph** between skills in the course knowledge graph. Once built, this graph enables:

1. **Topological learning order** — students see skills ordered by dependency, not just chapter index
2. **Prerequisite visualization** — DAG displayed in the UI so students understand what to learn first
3. **Smarter resource recommendations** — foundational skills are resourced before advanced ones

Skills are of two types (both handled uniformly via the shared `:SKILL` label):
- `BOOK_SKILL` — extracted from textbook chapters by the Curricular Alignment Architect
- `MARKET_SKILL` — extracted from job postings by the Market Demand Analyst

---

## 2. System Architecture

### 2.1 High-Level Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        React Frontend                            │
│   (SSE progress stream + prerequisite DAG visualization)         │
└──────────────────────┬──────────────────────────────────────────┘
                       │ POST /book-selection/courses/{id}/skill-prerequisites/build
                       │ GET  /book-selection/courses/{id}/skill-prerequisites
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                  FastAPI SSE Router                               │
│   api_routes/skill_prerequisites.py                              │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│              LangGraph Batch Pipeline                             │
│                                                                   │
│  embed_missing → find_and_merge_dupes → load_skills_for_clustering│
│       │                                        │                  │
│       │                           [fan_out: judge_cluster × N]    │
│       │                                        │                  │
│       └──────────────────────────── synthesize → enforce_dag → persist
└─────────────────────────────────────────────────────────────────┘
                       │
            ┌──────────▼──────────┐
            │       Neo4j         │
            │                     │
            │  :SKILL nodes       │
            │  :CONCEPT nodes     │
            │  :PREREQUISITE rels │
            │  stored embeddings   │
            └─────────────────────┘
```

### 2.2 Module Structure

| File | Responsibility |
|------|---------------|
| `schemas.py` | Pydantic output schemas: `DupeGroupVerdict`, `PrerequisiteEdge`, `ClusterPrerequisiteResult` |
| `state.py` | LangGraph state: `SkillPrerequisiteState`, `ClusterInput` |
| `prompts.py` | LLM prompt templates: `DUPE_JUDGE_PROMPT`, `CLUSTER_PREREQ_PROMPT` |
| `repository.py` | Neo4j layer — embedding backfill, skill loading, dupe merge, prerequisite read/write |
| `nodes.py` | Pipeline node functions + DAG enforcement utilities |
| `graph.py` | `build_skill_prerequisite_graph()` — StateGraph wiring |

---

## 3. Working Set

The pipeline operates on **448 skills** per course (verified against production data):

| Label | Count | Has Embeddings | Has Concepts | Has Chapter Mapping |
|-------|-------|---------------|--------------|---------------------|
| `BOOK_SKILL` | 239 | Yes | Yes | Via `BOOK_CHAPTER` |
| `MARKET_SKILL` (linked) | 209 | No (backfilled by pipeline) | Yes | Via `MAPPED_TO COURSE_CHAPTER` |
| `MARKET_SKILL` (orphaned) | 380 | No | No | None — **excluded** |

Orphaned market skills (no `course_id`, no chapter mapping, no concepts) are excluded automatically since they do not appear in any course-scoped query.

---

## 4. Pipeline Phases

### 4.1 Phase 0 — Embed Missing (`embed_missing`)

Market skills are stored without `name_embedding` by the Market Demand Analyst insertion path. Without embeddings they cannot participate in the course-local cosine comparisons used by dedup and clustering.

**What it does:**
1. Queries all `:SKILL` nodes in the course scope where `name_embedding IS NULL`
2. Batch-embeds skill names via `EmbeddingService.embed_documents`
3. Writes embeddings back via `UNWIND ... SET s.name_embedding = row.embedding`

**Idempotent** — skills with existing embeddings are skipped.

**Stream event:**
```json
{ "type": "prerequisite_progress", "phase": "embedding", "embedded": 209 }
```

---

### 4.2 Phase 1 — Deduplicate (`find_and_merge_dupes`)

Semantic duplicates must be merged before clustering, otherwise the same skill under two names produces two separate clusters and the prerequisite graph is fragmented.

**Why duplicates exist:** The book skill extraction runs independently per chapter. Different chapters or different textbooks may extract the same skill with slightly different wording.

**Algorithm:**

```
1. Load all course skills once after embeddings are backfilled
2. Build course-local cosine candidates from:
   - skill-name embeddings at threshold ≥ 0.78
   - concept multi-hot vectors at threshold ≥ 0.80
3. Union the two candidate sets with Union-Find so transitive duplicate groups are preserved
4. For each group of ≥2 skills, call LLM (DUPE_JUDGE_PROMPT)
5. If LLM confirms duplicates → APOC mergeNodes into canonical name
```

**Why LLM confirmation is mandatory:**

Cosine similarity still produces false positives:
- `"Construct correlated nested queries"` ≈ `"Construct uncorrelated nested queries"` (0.941) — **opposite concepts**
- `"Apply indexing techniques for RDF graphs"` ≈ `"Evaluate indexing strategies for RDF query processing"` (0.934) — **different Bloom's levels**

**LLM output schema:**
```python
class DupeGroupVerdict(BaseModel):
    are_duplicates: bool
    canonical_name: str | None       # best name to keep
    skill_names_to_merge: list[str]  # names to collapse into canonical
    reasoning: str
```

**Merge operation** — uses APOC `mergeNodes` with `mergeRels: true`:
- All relationships (`HAS_SKILL`, `MAPPED_TO`, `REQUIRES_CONCEPT`, `SOURCED_FROM`, `HAS_READING`, `HAS_VIDEO`, `HAS_QUESTION`, `SELECTED_SKILL`) are unioned onto the canonical node
- Both `:BOOK_SKILL` and `:MARKET_SKILL` labels are preserved when applicable

**Stream event:**
```json
{ "type": "prerequisite_progress", "phase": "dedup", "merged": 4 }
```

---

### 4.3 Phase 2a — Build Clusters (`load_skills_for_clustering` + `build_cluster_fanout`)

Skills are grouped into **semantic neighborhoods** using course-local name-embedding cosine. Each neighborhood is an independent cluster of related skills — for example, all SQL skills land together, all distributed computing skills land together.

**Why clustering (not pairwise comparison):**
- Pairwise comparison across 448 skills = ~100K pairs = infeasible
- Skills in the same semantic area are the only meaningful prerequisite candidates
- Giving the LLM all related skills at once produces holistic, coherent judgments vs. isolated yes/no on pairs

**Algorithm:**

```
1. Reload skills from Neo4j (excludes merged-away names)
2. Build an in-memory cosine matrix over the course's skill-name embeddings
3. For each skill: keep top-10 neighbors in [0.72, 0.90)
   - 0.90 ceiling excludes near-duplicates that survived dedup
4. Each skill + its neighbors = a cluster candidate
5. Deduplication:
   - If cluster A ⊂ cluster B → drop A
   - If two clusters share > 70% of members → merge them
6. Drop singletons (no neighbors in range)
```

**Expected output:** ~50–80 clusters of 4–12 skills each.

---

### 4.4 Phase 2b — Judge Clusters (`judge_cluster`, parallelized)

Each cluster is sent to the LLM in parallel via LangGraph's `Send` API. The LLM receives all skills in the cluster, sorted by `chapter_index` ascending, and produces prerequisite edges.

**Prompt context per cluster:**
```
Skills in this learning area (sorted by chapter order):
  1. "Identify SQL data types and constraints"
     Chapter: "Foundations of Data Management" (index 1)
     Concepts: [data types, primary key, foreign key]
  2. "Write SELECT queries with WHERE and JOIN clauses"
     Chapter: "Relational Databases" (index 3)
     Concepts: [SELECT, WHERE, JOIN, table relationships]
  3. "Optimize complex SQL queries with indexes and execution plans"
     Chapter: "Query Performance" (index 5)
     Concepts: [B-tree index, query planner, EXPLAIN]
```

**LLM instructions:**
- Only output `A → B` when `B` directly uses knowledge, procedure, or vocabulary from `A` and the learner would be blocked without `A`
- Chapter ordering is a strong hint (lower index → likely prerequisite), but same-chapter skills are often parallel
- Do not emit edges for paraphrases or near-duplicate skills
- Do not emit edges for same-level analytical peers such as compare-vs-compare or classify-vs-classify unless one explicitly depends on the other
- Do not emit edges for broad-tool vs specific-tool variants when neither blocks the other
- Do not emit taxonomy/classification → operational edges unless the operational skill explicitly depends on the taxonomy
- Do NOT create transitive edges (A→C if A→B and B→C already)
- Confidence: `high` (clear dependency), `medium` (strong suggestion), `low` (helpful but not required)

**Output schema:**
```python
class ClusterPrerequisiteResult(BaseModel):
    edges: list[PrerequisiteEdge]

class PrerequisiteEdge(BaseModel):
    prerequisite_skill: str
    dependent_skill: str
    confidence: Literal["high", "medium", "low"]
    reasoning: str
```

Edges from all clusters are accumulated into `prereq_edges` via LangGraph's `operator.add` fan-in reducer.

---

### 4.5 Phase 3 — Synthesize + Enforce DAG + Persist

**`synthesize`:** Deduplicates edges from overlapping clusters. If the same (A→B) pair appears in multiple clusters, the highest-confidence version is kept. Result is written to `final_edges`.

**`enforce_dag`:**

1. **Filter** — keep only `confidence in ("high", "medium")`
2. **Cycle detection** (Kahn's algorithm):
   - Run topological sort; any node not visited is in a cycle
   - Remove the lowest-confidence edge involving cycle nodes
   - Repeat until the graph is acyclic
3. **Transitive reduction:**
   - For each edge A→C: check if C is reachable from A via other paths
   - If yes, remove A→C (it's redundant — the chain A→B→C already implies it)
   - Result: minimal DAG with no redundant edges

**`persist`:**
1. Clears all existing `:PREREQUISITE` edges for the course (two separate queries — one for market skills, one for book skills)
2. Writes final edges:
```cypher
UNWIND $edges AS e
MATCH (a:SKILL {name: e.prereq_name})
MATCH (b:SKILL {name: e.dependent_name})
MERGE (a)-[r:PREREQUISITE]->(b)
SET r.confidence = e.confidence,
    r.reasoning = e.reasoning,
    r.created_at = datetime()
```

**Stream event:**
```json
{ "type": "prerequisite_completed", "edges_written": 87 }
```

---

## 5. Graph Schema

### New Relationship

```
(a:SKILL)-[:PREREQUISITE {
  confidence: "high" | "medium",
  reasoning: "...",
  created_at: datetime
}]->(b:SKILL)
```

Direction: `a` must be mastered **before** `b`.

### New Index

```cypher
CREATE INDEX skill_prerequisite_confidence_idx IF NOT EXISTS
FOR ()-[r:PREREQUISITE]-() ON (r.confidence)
```

Added to `core/neo4j.py` `initialize_neo4j_constraints`.

### Full Topology (post-pipeline)

```
BOOK_CHAPTER -[:HAS_SKILL]-> BOOK_SKILL:SKILL -[:PREREQUISITE]-> BOOK_SKILL:SKILL
BOOK_SKILL:SKILL -[:PREREQUISITE]-> MARKET_SKILL:SKILL
MARKET_SKILL:SKILL -[:PREREQUISITE]-> MARKET_SKILL:SKILL
```

Cross-type prerequisites are supported — a book skill can be a prerequisite of a market skill and vice versa.

---

## 6. API Reference

### `POST /book-selection/courses/{course_id}/skill-prerequisites/build`

Triggers the full pipeline. Returns an SSE stream.

**Auth:** Teacher role required.

**SSE Event Types:**

| Event | Payload | When |
|-------|---------|------|
| `prerequisite_started` | `{course_id}` | Pipeline begins |
| `prerequisite_progress` | `{phase, embedded/merged}` | After embed and dedup phases |
| `prerequisite_completed` | `{edges_written}` | Pipeline finished |
| `error` | `{message}` | Fatal error |

---

### `GET /book-selection/courses/{course_id}/skill-prerequisites`

Returns the prerequisite DAG for the course.

**Auth:** Teacher role required.

**Response:**
```json
{
  "edges": [
    {
      "from_skill": "Identify SQL data types and constraints",
      "to_skill": "Write SELECT queries with WHERE and JOIN clauses",
      "confidence": "high",
      "reasoning": "Students must understand data types before writing queries that filter by type."
    }
  ]
}
```

---

## 7. Cost Profile

| Phase | LLM Calls | Embedding Batches | Approx. Time |
|-------|-----------|------------------|--------------|
| Embed missing (209 market skills) | — | ~3 | ~30s |
| Dedup (~20 groups) | ~20 | — | ~1 min |
| Cluster judgment (~70 clusters) | ~70 | — | ~4 min |
| DAG enforcement + persist | — | — | ~5s |
| **Total** | **~90** | **~3** | **~6 min** |

---

## 8. Verification

After running the pipeline, verify with these Cypher queries:

```cypher
-- 1. Confirm no cycles (should return 0 rows)
MATCH p=(a:SKILL)-[:PREREQUISITE*]->(a) RETURN p LIMIT 1

-- 2. Check edge count
MATCH ()-[r:PREREQUISITE]->() RETURN count(r) AS total_edges

-- 3. Spot-check — skills with most prerequisites
MATCH (a:SKILL)-[:PREREQUISITE]->(b:SKILL)
RETURN b.name AS skill, count(a) AS prereq_count
ORDER BY prereq_count DESC LIMIT 10

-- 4. Verify no orphaned edges (all endpoints exist as SKILL nodes)
MATCH (a:SKILL)-[r:PREREQUISITE]->(b:SKILL)
WHERE a.name IS NULL OR b.name IS NULL
RETURN count(r)

-- 5. Confirm market skills now have embeddings
MATCH (s:MARKET_SKILL) WHERE s.name_embedding IS NULL RETURN count(s)
```

**Expected results:**
- Query 1: no rows (acyclic)
- Query 2: ~80–200 edges (1–3 per skill on average)
- Query 5: 0 (all market skills embedded)

---

## 9. Re-running the Pipeline

The pipeline is **fully idempotent**:
- Phase 0 skips skills that already have embeddings
- `clear_skill_prerequisites` drops all existing `:PREREQUISITE` edges before writing new ones
- `MERGE` prevents duplicate relationships

Re-running after adding new skills or re-extracting book skills will produce an updated DAG reflecting the current skill set.
