# Curriculum Knowledge Graph — Implementation Plan

## Overview

Build a feature that lets a teacher select a ranked book from the overview tab and construct a curriculum knowledge graph in Neo4j. The graph transfers extracted data (chapters, sections, concepts, skills) from PostgreSQL into Neo4j, merges duplicate concepts via cosine similarity, and links the curriculum to the existing course graph.

### Key Decisions

- **Merging approach**: Application-level (NOT APOC triggers — unavailable on Aura)
- **Skill scope**: `SECTION → SKILL → CONCEPT` (skills stored per chapter in `skills_json` but reference section-level concepts)
- **Status tracking**: New `CURRICULUM_BUILT` value on `ExtractionRunStatus` enum
- **Embedding model**: `text-embedding-v4` (2048-dim, cosine) — same model in both PostgreSQL and Neo4j
- **Chapter summary embeddings**: Generated at build time via the existing `EmbeddingService` and stored on `BOOK_CHAPTER` nodes for semantic search over curriculum structure

---

## Step 1 — Add `CURRICULUM_BUILT` to `ExtractionRunStatus`

**File**: `backend/app/modules/curricularalignmentarchitect/models.py`

Add after the existing `agentic_completed` value:

```python
CURRICULUM_BUILT = "curriculum_built"
```

---

## Step 2 — Neo4j Constraints & Indexes

**File**: `backend/app/core/neo4j.py` → `initialize_constraints_and_indexes()`

Add uniqueness constraints for new labels:

```cypher
CREATE CONSTRAINT curriculum_id IF NOT EXISTS FOR (cur:CURRICULUM) REQUIRE cur.id IS UNIQUE;
CREATE CONSTRAINT book_chapter_id IF NOT EXISTS FOR (ch:BOOK_CHAPTER) REQUIRE ch.id IS UNIQUE;
CREATE CONSTRAINT book_section_id IF NOT EXISTS FOR (s:BOOK_SECTION) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT book_skill_id IF NOT EXISTS FOR (sk:BOOK_SKILL) REQUIRE sk.id IS UNIQUE;
```

Add a vector index for chapter summary embeddings:

```cypher
CREATE VECTOR INDEX book_chapter_summary_vector_idx IF NOT EXISTS
FOR (ch:BOOK_CHAPTER) ON (ch.summary_embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 2048, `vector.similarity_function`: 'cosine'}};
```

> `CONCEPT` already has a uniqueness constraint on `name` and a vector index on `embedding`.

---

## Step 3 — Neo4j Node Schema

| Label | Properties | ID Pattern |
|---|---|---|
| `CURRICULUM` | `id`, `book_title`, `authors`, `course_id`, `created_at` | `cur_{selected_book_id}` |
| `BOOK_CHAPTER` | `id`, `title`, `chapter_index`, `summary`, `summary_embedding` | `cur_{id}_ch_{chapter_index}` |
| `BOOK_SECTION` | `id`, `title`, `section_index`, `page_start`, `page_end` | `cur_{id}_ch_{ci}_sec_{si}` |
| `BOOK_SKILL` | `id`, `name`, `description` | `cur_{id}_ch_{ci}_sk_{skill_index}` |
| `CONCEPT` | `name`, `embedding`, `description`, `aliases`, `merge_count` | (existing, MERGE on `toLower(name)`) |

---

## Step 4 — Neo4j Relationship Schema

```
(:CLASS)-[:HAS_CURRICULUM]->(:CURRICULUM)
(:CURRICULUM)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)
(:BOOK_CHAPTER)-[:NEXT_CHAPTER]->(:BOOK_CHAPTER)        -- linked list for ordering
(:BOOK_CHAPTER)-[:HAS_SECTION]->(:BOOK_SECTION)
(:BOOK_SECTION)-[:NEXT_SECTION]->(:BOOK_SECTION)        -- linked list within chapter
(:BOOK_SECTION)-[:COVERS_CONCEPT]->(:CONCEPT)            -- props: relevance, text_evidence
(:BOOK_CHAPTER)-[:HAS_SKILL]->(:BOOK_SKILL)
(:BOOK_SKILL)-[:REQUIRES_CONCEPT]->(:CONCEPT)
```

### Concept Merge Flow

After all concepts are batch-inserted via `MERGE (c:CONCEPT {name: toLower(name)})`:

1. For each newly created/matched concept with an embedding, query the vector index:
   ```cypher
   CALL db.index.vector.queryNodes('concept_embedding_vector_idx', 5, $embedding)
   YIELD node, score
   WHERE score >= 0.92 AND node <> $self
   ```
2. Merge similar concepts using `apoc.refactor.mergeNodes([self, node], {properties: "combine", mergeRels: true})`.
3. Update `aliases` and `merge_count` on the surviving node.

---

## Step 5 — Backend Service: PostgreSQL → Neo4j Transfer

**New module**: `backend/app/modules/curricularalignmentarchitect/curriculum_graph/`

### `repository.py` — Neo4j data access

```python
class CurriculumGraphRepository:
    """All Neo4j write operations for curriculum graph construction."""

    def create_curriculum_node(self, tx, curriculum_id, book_title, authors, course_id) -> None
    def link_curriculum_to_class(self, tx, course_id, curriculum_id) -> None
    def create_chapter_nodes(self, tx, curriculum_id, chapters: list[dict]) -> None  # includes summary_embedding
    def link_chapters_linked_list(self, tx, curriculum_id) -> None
    def create_section_nodes(self, tx, chapter_id, sections: list[dict]) -> None
    def link_sections_linked_list(self, tx, chapter_id) -> None
    def merge_concept_node(self, tx, name, embedding, description) -> None
    def create_covers_concept_rel(self, tx, section_id, concept_name, relevance, text_evidence) -> None
    def create_skill_node(self, tx, skill_id, name, description) -> None
    def link_skill_to_chapter(self, tx, chapter_id, skill_id) -> None
    def link_skill_requires_concept(self, tx, skill_id, concept_name) -> None
    def find_similar_concepts(self, tx, embedding, threshold=0.92, top_k=5) -> list
    def merge_similar_concepts(self, tx, node_id_a, node_id_b) -> None
```

### `service.py` — Orchestration (generator for SSE)

```python
class CurriculumGraphService:
    """Reads from PostgreSQL, writes to Neo4j, yields SSE progress events.

    Uses EmbeddingService (from app.modules.embeddings.embedding_service)
    to embed chapter summaries at build time.
    """

    async def build_curriculum(self, course_id, run_id, selected_book_id, db) -> AsyncGenerator[dict, None]:
        # 1. Validate run status (must be BOOK_PICKED or agentic_completed)
        # 2. Load selected book + chapters + sections + concepts from PostgreSQL
        # 3. yield {"event": "progress", "step": "embedding_chapter_summaries"}
        # 4. Embed all chapter summaries in one batch via EmbeddingService.embed_documents()
        #    (reuses existing batching/retry/parallelism — ~12 texts, single API call)
        # 5. yield {"event": "progress", "step": "creating_curriculum_node"}
        # 6. Create CURRICULUM node, link to CLASS
        # 7. Create BOOK_CHAPTER nodes (with summary_embedding) + NEXT_CHAPTER linked list
        # 8. For each chapter:
        #    a. Create BOOK_SECTION nodes + NEXT_SECTION linked list
        #    b. For each section's concepts:
        #       - MERGE CONCEPT node (toLower name, set embedding)
        #       - Create COVERS_CONCEPT rel with relevance + evidence
        #    c. Parse skills_json, create BOOK_SKILL nodes
        #    d. Link SKILL → CONCEPT via REQUIRES_CONCEPT
        #    e. yield progress per chapter
        # 9. Run similarity-based concept merging pass
        # 10. Update ExtractionRunStatus → CURRICULUM_BUILT
        # 11. yield {"event": "complete", "curriculum_id": ...}
```

**Data loading query** (PostgreSQL):

```python
# Load chapters for the selected book's extraction run
chapters = db.query(BookChapter).filter(
    BookChapter.extraction_run_id == run_id
).order_by(BookChapter.chapter_index).all()

# For each chapter, eager-load sections → concepts
for chapter in chapters:
    sections = db.query(BookSection).filter(
        BookSection.chapter_id == chapter.id
    ).order_by(BookSection.section_index).all()

    for section in sections:
        concepts = db.query(BookConcept).filter(
            BookConcept.section_id == section.id
        ).all()
```

---

## Step 6 — API Endpoint (SSE Streaming)

**File**: `backend/app/modules/curricularalignmentarchitect/api_routes/analysis.py`

```python
@router.post("/courses/{course_id}/analysis/{run_id}/build-curriculum/{selected_book_id}")
async def build_curriculum(
    course_id: int,
    run_id: int,
    selected_book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream curriculum graph construction progress via SSE."""
    service = CurriculumGraphService()

    async def sse_generator():
        async for event in service.build_curriculum(course_id, run_id, selected_book_id, db):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
```

---

## Step 7 — Frontend: "Build Curriculum" Button

**File**: `frontend/src/features/book-selection/components/visualization/chapter-analysis/overview-tab.tsx`

Add below the ranked book cards section:

- **Button**: "Build Curriculum Graph" (disabled if no book selected or already built)
- **AlertDialog** (shadcn): Confirmation with book title, concept/skill counts
- **Progress overlay**: Shows SSE events as a step list with check marks
- **Success state**: Replace button with "Curriculum Built ✓" badge

---

## Step 8 — Frontend: API Function

**File**: `frontend/src/features/book-selection/api.ts`

```typescript
export function buildCurriculumSSE(
  courseId: number,
  runId: number,
  selectedBookId: number,
  onProgress: (event: CurriculumBuildEvent) => void,
  onComplete: (event: CurriculumCompleteEvent) => void,
  onError: (error: Error) => void,
): () => void {
  const url = `${API_BASE}/book-selection/courses/${courseId}/analysis/${runId}/build-curriculum/${selectedBookId}`;
  // Use fetch + ReadableStream to consume SSE
  // Return abort function
}
```

---

## Step 9 — Frontend: Context Update

**File**: `frontend/src/features/book-selection/components/visualization/chapter-analysis/context.tsx`

Add to `ChapterAnalysisProvider`:

```typescript
// New state
const [isBuildingCurriculum, setIsBuildingCurriculum] = useState(false);
const [curriculumBuildProgress, setCurriculumBuildProgress] = useState<BuildEvent[]>([]);
const [curriculumBuilt, setCurriculumBuilt] = useState(false);

// New action
const buildCurriculum = useCallback((selectedBookId: number) => {
  setIsBuildingCurriculum(true);
  buildCurriculumSSE(courseId, runId, selectedBookId,
    (event) => setCurriculumBuildProgress(prev => [...prev, event]),
    (event) => { setCurriculumBuilt(true); setIsBuildingCurriculum(false); },
    (error) => { setIsBuildingCurriculum(false); /* toast error */ },
  );
}, [courseId, runId]);
```

---

## File Inventory

| # | Path | Action |
|---|---|---|
| 1 | `backend/app/modules/curricularalignmentarchitect/models.py` | Edit — add enum value |
| 2 | `backend/app/core/neo4j.py` | Edit — add constraints |
| 3 | `backend/app/modules/curricularalignmentarchitect/curriculum_graph/__init__.py` | Create |
| 4 | `backend/app/modules/curricularalignmentarchitect/curriculum_graph/repository.py` | Create |
| 5 | `backend/app/modules/curricularalignmentarchitect/curriculum_graph/service.py` | Create |
| 6 | `backend/app/modules/curricularalignmentarchitect/api_routes/analysis.py` | Edit — add endpoint |
| 7 | `frontend/src/features/book-selection/api.ts` | Edit — add SSE function |
| 8 | `frontend/src/features/book-selection/components/visualization/chapter-analysis/context.tsx` | Edit — add state/actions |
| 9 | `frontend/src/features/book-selection/components/visualization/chapter-analysis/overview-tab.tsx` | Edit — add button + dialog |
