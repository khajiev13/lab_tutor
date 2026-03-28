# Concept Normalization — Architecture & Design Document

> **Module**: `backend/app/modules/concept_normalization/`
> **Pattern**: LangGraph iterative workflow with human-in-the-loop review
> **Version**: 1.0

---

## 1. Purpose

The Concept Normalization module automatically detects and merges duplicate or near-duplicate concepts in the Neo4j knowledge graph. It enables teachers to:

1. Discover semantically equivalent concepts (e.g., "MapReduce" vs "Map-Reduce" vs "map/reduce")
2. Review AI-proposed merges before they are applied
3. Consolidate the concept bank to improve downstream analysis quality

---

## 2. System Architecture

### 2.1 High-Level Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        React Frontend                            │
│   (Streaming UI — merge proposals, review interface)             │
└──────────────────────────┬───────────────────────────────────────┘
                           │ GET /normalization/stream?course_id=123
                           │ (SSE stream)
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                      FastAPI SSE Router                           │
│   routes.py — streaming normalization + review endpoints          │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│            ConceptNormalizationService                            │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │           LangGraph StateGraph                             │  │
│  │                                                            │  │
│  │  ┌──────────┐     ┌───────────┐     ┌──────────────────┐  │  │
│  │  │ Generate  │────▶│ Validate  │────▶│ Check convergence│  │  │
│  │  │ merges    │     │ merges    │     │ (< 3 new merges  │  │  │
│  │  │ (LLM)    │     │ (LLM)    │     │  or max 10 iter) │  │  │
│  │  └──────────┘     └───────────┘     └────────┬─────────┘  │  │
│  │       ▲                                      │            │  │
│  │       └──────────── loop ────────────────────┘            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Output: ConceptMerge proposals → SQL review table               │
└─────────────┬─────────────────────────┬──────────────────────────┘
              │                         │
   ┌──────────▼──────────┐   ┌─────────▼──────────┐
   │    PostgreSQL        │   │      Neo4j          │
   │  Review staging      │   │  CONCEPT nodes      │
   │  (approve/reject)    │   │  MENTIONS edges      │
   │                      │   │  APOC.refactor       │
   └──────────────────────┘   └────────────────────┘
```

### 2.2 Module Structure

| File | Responsibility |
|------|---------------|
| `models.py` | Pydantic state models: `ConceptMerge`, `WeakMerge`, `ConceptNormalizationState` |
| `schemas.py` | API request/response schemas |
| `service.py` | `ConceptNormalizationService` — LangGraph orchestrator |
| `repository.py` | Neo4j query layer (concept bank, merge operations) |
| `review_sql_models.py` | `ConceptNormalizationReviewItem` SQLAlchemy table |
| `review_sql_repository.py` | SQL review/proposal persistence |
| `routes.py` | FastAPI endpoints (SSE stream + review) |
| `prompts.py` | LLM system prompts for generation + validation |

---

## 3. Workflow

### 3.1 Complete Pipeline

```
                         TEACHER
                           │
              GET /normalization/stream?course_id=123
                           │
              ┌────────────▼────────────┐
              │  PHASE 1: EXTRACT       │
              │                         │
              │  Query Neo4j for all    │
              │  CONCEPT nodes in       │
              │  course scope           │
              │                         │
              │  Group by semantic      │
              │  similarity             │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  PHASE 2: GENERATE      │
              │                         │
              │  LLM proposes merge     │
              │  candidates:            │
              │  concept_a + concept_b  │
              │  → canonical name       │
              │  → variants list        │
              │  → reasoning            │
              │                         │
              │  Stream: progress events│
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  PHASE 3: VALIDATE      │
              │                         │
              │  LLM re-validates each  │
              │  merge proposal:        │
              │  - Semantically sound?  │
              │  - Flag "weak" merges   │
              │  - Remove false         │
              │    positives            │
              │                         │
              │  Iterate until:         │
              │  < 3 new merges OR      │
              │  max 10 iterations      │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  PHASE 4: REVIEW (HITL) │
              │                         │
              │  Persist to SQL table   │
              │  Teacher reviews:       │
              │  APPROVE / REJECT /     │
              │  MODIFY each merge      │
              │                         │
              │  Stream event:          │
              │  type="complete"        │
              │  requires_review=true   │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  PHASE 5: APPLY         │
              │                         │
              │  PUT /apply-review      │
              │                         │
              │  For each approved:     │
              │  1. APOC.refactor       │
              │     .mergeNodes()       │
              │  2. Consolidate names   │
              │  3. Update MENTIONS     │
              │  4. Delete review rows  │
              └─────────────────────────┘
```

---

## 4. Data Models

### 4.1 State Models

```python
ConceptNormalizationState(TypedDict)
  ├── concepts: list[dict]                 # All concepts from Neo4j
  ├── all_merges: dict[str → ConceptMerge] # Accumulated proposals
  ├── weak_merges: dict[str → str]         # Flagged as weak (false positives)
  ├── new_merge_batch: list[ConceptMerge]  # Current iteration results
  ├── iteration_count: int
  └── workflow_metadata: dict              # Model info, phase tracking

ConceptMerge
  ├── concept_a: str           # First concept name
  ├── concept_b: str           # Second concept name
  ├── canonical: str           # Merge target (preferred name)
  ├── variants: list[str]      # All name variants
  └── r: str                   # Reasoning for merge

WeakMerge
  ├── concept_a, concept_b, canonical
  ├── r: str                   # Original reasoning
  └── w: str                   # Why this merge is invalid
```

### 4.2 SQL Review Model

```python
ConceptNormalizationReviewItem
  ├── course_id, review_id: str
  ├── concept_a, concept_b, canonical: str
  ├── variants_json: str       # JSON array of name variants
  ├── decision: MergeDecision  # PENDING | APPROVE | REJECT
  └── comment: str             # Teacher feedback
```

---

## 5. Neo4j Operations

### Read

```cypher
-- Get all concepts in course scope
MATCH (c:CLASS {id: $course_id})-[:HAS_DOCUMENT]->(d)
      -[:MENTIONS]->(concept:CONCEPT)
RETURN DISTINCT concept.name, concept.description
```

### Write (Merge)

```cypher
-- Merge two concept nodes into one
CALL apoc.refactor.mergeNodes(
  [canonical_node, variant_node],
  { properties: "combine", mergeRels: true }
)
```

---

## 6. API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/normalization/stream?course_id=123` | SSE: run normalization workflow |
| `GET` | `/normalization/concepts?course_id=123` | List course concepts |
| `GET` | `/normalization/review/{review_id}` | Fetch review proposals |
| `PUT` | `/normalization/apply-review/{review_id}` | Apply teacher decisions |
| `POST` | `/normalization/update-merges` | Batch update decisions |

### SSE Stream Events

| Event Type | Payload | When |
|-----------|---------|------|
| `progress` | `{phase, iteration, merges_found}` | During generation/validation |
| `merge_proposal` | `{concept_a, concept_b, canonical, reasoning}` | New merge found |
| `weak_merge` | `{concept_a, concept_b, reason}` | Merge flagged as weak |
| `complete` | `{requires_review, review_id, latest_merges}` | Workflow done |
| `error` | `{message}` | Failure |

---

## 7. External Dependencies

| Service | Usage |
|---------|-------|
| **Neo4j** | Read CONCEPT nodes; apply merges via APOC |
| **PostgreSQL** | Review staging table (`ConceptNormalizationReviewItem`) |
| **OpenAI-compatible LLM** | Generation + validation of merge proposals |
| **LangGraph** | StateGraph workflow with iterative convergence |
| **LangSmith** (optional) | Trace LLM calls |

---

## 8. Module Connections

```
┌──────────────────────────────────────────────────────┐
│            Concept Normalization                      │
└────────────────────────┬─────────────────────────────┘
                         │
          Reads from:    │    Affects:
          ─────────      │    ────────
   Document Extraction   │    CONCEPT nodes
   (creates concepts)    │    MENTIONS edges
                         │    CONCEPT_RELATED edges
   Downstream users:     │
   ─────────────────     │
   Curriculum Mapper     │    (cleaner concept bank
   (MDA agent)           │     improves skill matching)
                         │
   Embeddings Module     │    (merged concepts affect
                         │     vector representations)
```
