# Lab Tutor - Copilot Instructions

## Project Overview
Lab Tutor is a knowledge graph builder that extracts concepts, relationships, and structured knowledge from educational DOCX documents using LangChain and Neo4j. The system processes technical transcripts through an LLM-based extraction pipeline and stores results in a graph database for semantic querying.

## Architecture

### Core Components
- **`knowledge_graph_builder/`**: Main extraction and ingestion pipeline
  - **`services/`**: Core business logic (extraction, embedding, Neo4j operations)
  - **`models/`**: Pydantic models for type-safe data structures
  - **`prompts/`**: LangChain prompt templates for extraction
  - **`utils/`**: File handling, output organization, document loading

### Data Flow
1. DOCX → `load_single_docx_document()` → LangChain Documents
2. Documents → `LangChainCanonicalExtractionService` → structured concepts/relationships
3. Extraction result → `organize_extraction_output()` → topic-based JSON files in `batch_output/`
4. JSON → `Neo4jService.create_graph_data_from_extraction()` → Neo4j graph nodes/relationships

### Graph Schema
- **Nodes**: `TOPIC` (document-level), `THEORY` (document with embeddings), `CONCEPT` (shared canonical concepts)
- **Relationships**: `TOPIC -[HAS_THEORY]-> THEORY`, `THEORY -[MENTIONS]-> CONCEPT`
- **Properties**: Topics have names; Theories have embeddings (1536-dim), compressed_text, keywords; Concepts have canonical names only
- CONCEPT nodes are **shared across documents** (no unique constraint, use MERGE)

## Development Workflows

### Running Extractions
```bash
# Single document (testing)
cd knowledge_graph_builder
python main.py path/to/document.docx

# Batch processing (all DOCX in directory)
python main_batch.py
```

### Database Operations
```bash
# Start Neo4j (required first)
docker compose up neo4j --build

# Access Neo4j Browser: http://localhost:7474
# Credentials: neo4j/password123

# Clear database via Cypher
docker compose exec neo4j cypher-shell -u neo4j -p password123
> MATCH (n) DETACH DELETE n;
```

### Environment Setup
1. Copy `.env.example` to `.env` in `knowledge_graph_builder/`
2. Required vars: `GOOGLE_API_KEY` (Gemini), `NEO4J_PASSWORD`, `XIAO_CASE_API_KEY` (embeddings)
3. Optional: `LANGSMITH_API_KEY`, `LANGCHAIN_TRACING_V2=true` for debugging

## Critical Conventions

### Pydantic Models Drive Everything
All data structures use Pydantic models (see `models/extraction_models.py`, `models/neo4j_models.py`):
- `CanonicalExtractionResult` for LLM extraction output
- `Neo4jGraphData`, `Neo4jNode`, `Neo4jRelationship` for database operations
- Never use raw dicts - always validate through Pydantic models

### LangChain Structured Output Pattern
Extraction uses LangChain's `with_structured_output()` with `json_mode`:
```python
self.extraction_chain = self.llm.with_structured_output(
    CanonicalExtractionResult,
    method="json_mode"
)
```
This ensures type-safe LLM responses matching Pydantic schemas.

### Topic-Based Output Organization
Files are organized by extracted topic (not filename):
- `batch_output/Big_Data_Concepts_and_Evolution/{filename}_extraction.json`
- Topic names are sanitized (spaces→underscores, max 50 chars)
- See `utils/output_utils.py` for organization logic

### LLM Validator Prompt Pattern (Anti-Perfectionism)
When creating validator/feedback prompts in iterative LLM workflows, prevent "hallucinated criticism":
```python
# ❌ BAD: Vague criteria leads to cosmetic feedback loop
"Decide if relationships need improvement"

# ✅ GOOD: Explicit convergence criteria with anti-perfectionism rules
"""
CRITICAL RULES:
- If semantically correct, APPROVE even if wording could be improved
- Do NOT suggest cosmetic improvements like "add more detail"
- Only provide feedback for FACTUALLY WRONG relationships
- "Good enough" is better than "perfect"

CONVERGENCE DECISION:
Set converged=true ONLY if:
  • ALL relationships approved (100%)
  • AND no feedback to provide
Set converged=false if ANY relationships rejected
  • Provide specific feedback for improvements
"""
```
**Why**: Validators will manufacture "improvements" to avoid converging unless explicitly told when to stop. Balance between quality (iterate when needed) and efficiency (don't iterate on cosmetic issues). See `simple_langgraph_service.py:_feedback_validator_node` for implementation.

### Service Initialization Pattern
Services accept optional dependencies for testing/flexibility:
```python
class IngestionService:
    def __init__(self, neo4j_service=None, embedding_service=None):
        self._neo4j_service = neo4j_service or Neo4jService()
        self._embedding_service = embedding_service or EmbeddingService()
```

## Common Tasks

### Adding New Relationship Types
1. Define in `utils/relationship_types.py`
2. Update Neo4j relationship creation in `services/neo4j_service.py`
3. Add Pydantic model in `models/neo4j_models.py` (e.g., `NewRelationshipProperties`)
4. Update LangGraph validation if using `services/simple_langgraph_service.py`

### Modifying Extraction Prompts
Edit `prompts/extraction_prompts.py`:
- `SYSTEM_INSTRUCTION`: Core extraction rules
- `TASK_INSTRUCTION`: Template for document processing
- `EXTRACTION_PROMPT_WITH_EXAMPLES`: Includes few-shot examples (preferred for better results)

### Debugging Extraction
Enable verbose mode in `LangChainCanonicalExtractionService`:
```python
service.set_debug_mode(verbose=True, enhanced_debug=True)
```
Use LangSmith tracing (set `LANGCHAIN_TRACING_V2=true`) for detailed LLM call inspection.

### Vector Search Setup
Neo4j vector indexes are created automatically in `Neo4jService.create_constraints_and_indexes()`:
- `theory_embedding_idx`: 1536 dimensions, cosine similarity
- `concept_embedding_idx`: Same configuration
Embeddings use OpenAI-compatible API via `services/embedding.py` (XiaoCase AI by default)

## Testing
No formal test suite currently. Test by:
1. Run `main.py` on a single small DOCX
2. Verify JSON output structure in `batch_output/{topic}/`
3. Check Neo4j Browser for correct graph structure
4. Use `run_simple_relationships.py` to validate relationship detection

## Common Pitfalls
- **Missing env vars**: Check `.env` exists and has all keys from `.env.example`
- **Neo4j connection errors**: Ensure `docker compose up neo4j` is running first
- **Empty extractions**: Check document has actual text content (use `docx2txt` to verify)
- **Duplicate concepts**: CONCEPT nodes use MERGE, not CREATE UNIQUE - this is intentional for cross-document sharing
- **Fetch the documentation website**: You can refer to langchain_docs.md and langgraph_docs.md before writing any code in langchain or langgraph because documentation always uses best practices.


##Do not generate readme files on every task you do.