# Knowledge Graph Builder - Architecture Summary

## What Happened to main.py?

The old `main.py` and `main_batch.py` files were **deleted** and their functionality was **reorganized** into a more modular structure. The two main services you mentioned are still there, just in different locations.

## Current Architecture

### 📦 Service 1: Data Extraction from unstructured_script folder

**Location**: `services/ingestion.py` → `IngestionService` class

**Key Methods**:
- `process_single_document(docx_path, ...)` - Extracts concepts from a single DOCX file
- `process_batch_documents(input_directory, ...)` - Batch processes all DOCX files in a directory

**How it works**:
1. Loads DOCX files from `unstructured_script/` directory
2. Uses `LangChainCanonicalExtractionService` to extract concepts
3. Saves extracted concepts to `batch_output/{Topic_Name}/` as JSON files
4. Optionally inserts into Neo4j database

**How to Run**:
```python
from services.ingestion import IngestionService

# Create service instance
ingestion = IngestionService()

# Option 1: Process single document
result = ingestion.process_single_document(
    docx_path="unstructured_script/document.docx",
    output_dir="batch_output",
    insert_to_neo4j=True
)

# Option 2: Process entire directory (batch)
result = ingestion.process_batch_documents(
    input_directory="unstructured_script",
    output_directory="batch_output",
    clear_database=False
)
```

---

### 🔗 Service 2: Linking CONCEPT Nodes (Relationship Detection)

**Location**: `services/enhanced_langgraph_service.py` → `EnhancedRelationshipService` class

**What it does**:
- Finds similar concepts and creates canonical forms (e.g., "PCA" → "Principal Component Analysis")
- Detects semantic relationships between concepts (USED_FOR, RELATED_TO, etc.)
- Uses LangGraph for iterative quality-controlled workflow
- Binary validation (valid/weak) with convergence detection

**Key Methods**:
- `run_workflow(concepts)` - Main entry point for relationship detection
- Uses LangGraph state machine with:
  - Generation node (finds relationships)
  - Validation node (filters weak relationships)
  - Convergence checker (stops when quality is high)

**How to Run**:
```python
from neo4j_database import Neo4jService
from services.enhanced_langgraph_service import EnhancedRelationshipService
from models.langgraph_state_models import WorkflowConfiguration

# Initialize services
neo4j = Neo4jService()
config = WorkflowConfiguration()
relationship_service = EnhancedRelationshipService(neo4j, config)

# Get all concepts from database
concepts = neo4j.get_all_concept_names()

# Run relationship detection workflow
result = relationship_service.run_workflow(concepts)

# Results are automatically saved to iteration_logs/ and output/
```

---

## Current File Organization

```
knowledge_graph_builder/
├── neo4j_database/               # Shared Neo4j utilities
│   └── neo4j_service.py          # Database operations
├── services/
│   ├── ingestion.py               # SERVICE 1: Document extraction
│   ├── enhanced_langgraph_service.py  # SERVICE 2: Concept linking/relationships
│   ├── extraction_langchain.py    # LLM-based concept extraction
│   └── embedding.py               # Vector embeddings
│
├── scripts/
│   └── ingest_ready_data.py       # Loads pre-extracted data into Neo4j
│
├── models/
│   ├── extraction_models.py       # Pydantic models for extraction
│   ├── langgraph_state_models.py  # State models for relationship workflow
│   └── neo4j_models.py            # Neo4j data models
│
├── prompts/
│   ├── extraction_prompts.py
│   ├── concept_normalization_prompts.py
│   └── enhanced_relationship_prompts.py
│
├── batch_output/                  # Extracted concepts (38 documents)
├── output/                        # Normalized concepts & relationships
└── unstructured_script/           # Source DOCX files (38 files)
```

---

## How to Use the System

### Option A: Load Pre-Extracted Data (Quickest)
If you just want to populate Neo4j with the existing data:

```bash
cd knowledge_graph_builder
python scripts/ingest_ready_data.py --clear
```

This loads:
1. **Stage 1**: All concepts from `batch_output/` (38 documents already extracted)
2. **Stage 2**: Normalized concepts and relationships from `output/final.json`

### Option B: Extract From Documents (Full Pipeline)
If you want to re-extract from the DOCX files:

```python
from services.ingestion import IngestionService

ingestion = IngestionService()

# Extract all documents in unstructured_script/
result = ingestion.process_batch_documents(
    input_directory="unstructured_script",
    output_directory="batch_output",
    clear_database=True
)
```

### Option C: Run Relationship Detection
After concepts are in the database, detect relationships:

```python
from neo4j_database import Neo4jService
from services.enhanced_langgraph_service import EnhancedRelationshipService
from models.langgraph_state_models import WorkflowConfiguration

# Setup
neo4j = Neo4jService()
config = WorkflowConfiguration(
    max_iterations=5,
    batch_size=10,
    verbose_logging=True
)

# Run relationship detection
service = EnhancedRelationshipService(neo4j, config)
concepts = neo4j.get_all_concept_names()
result = service.run_workflow(concepts)

print(f"Found {len(result['valid_relationships'])} valid relationships")
print(f"Found {len(result['concept_merges'])} concept merges")
```

---

## Key Differences from Old main.py

| Old Structure | New Structure |
|--------------|---------------|
| `main.py` - Single document | `IngestionService.process_single_document()` |
| `main_batch.py` - Batch processing | `IngestionService.process_batch_documents()` |
| Relationship detection in main | `EnhancedRelationshipService` (separate service) |
| Manual workflow | LangGraph state machine with convergence |
| All in one script | Modular services |

---

## Environment Variables Required

Create a `.env` file in `knowledge_graph_builder/`:

```bash
# Neo4j Connection
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password123

# For Extraction (Service 1)
GOOGLE_API_KEY=your_gemini_api_key

# For Relationship Detection (Service 2)
XIAO_CASE_API_KEY=your_openai_api_key
XIAO_CASE_API_BASE=https://api.xiaocaseai.com/v1
```

---

## Summary

✅ **Service 1 (Extraction)**: Still exists in `services/ingestion.py`
✅ **Service 2 (Linking)**: Still exists in `services/enhanced_langgraph_service.py`
✅ Both services are more modular and easier to use independently
✅ Pre-extracted data is available in `batch_output/` and `output/`
✅ Main entry point is now `scripts/ingest_ready_data.py` for loading data

The functionality hasn't been lost - it's been **reorganized into better-structured services**!

