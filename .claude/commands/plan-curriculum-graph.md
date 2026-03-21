Implementation plan for the Curriculum Knowledge Graph feature.

Read the full plan: .github/prompts/plan-curriculumKnowledgeGraph.prompt.md

## Summary
Build a feature that lets a teacher select a ranked book and construct a curriculum knowledge graph in Neo4j. Transfers extracted data (chapters, sections, concepts, skills) from PostgreSQL into Neo4j, merges duplicate concepts via cosine similarity, and links the curriculum to the existing course graph.

## Key Decisions
- Merging: Application-level (NOT APOC triggers — unavailable on Aura)
- Skill scope: SECTION → SKILL → CONCEPT
- Status tracking: CURRICULUM_BUILT enum value
- Embedding model: text-embedding-v4 (2048-dim, cosine)

## Steps
1. Add CURRICULUM_BUILT to ExtractionRunStatus
2. Neo4j constraints & indexes
3. Node schema (CURRICULUM, BOOK_CHAPTER, BOOK_SECTION, BOOK_SKILL, CONCEPT)
4. Relationship schema + concept merge flow
5. Backend service: PostgreSQL → Neo4j transfer (curriculum_graph/ module)
6. API endpoint (SSE streaming)
7. Frontend: "Build Curriculum" button
8. Frontend: API function (SSE consumer)
9. Frontend: Context update

$ARGUMENTS
