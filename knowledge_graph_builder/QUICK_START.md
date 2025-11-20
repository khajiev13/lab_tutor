# Quick Start Guide - Knowledge Graph Builder

## Summary

✅ **Your two main services are still here!**
- The old `main.py` and `main_batch.py` were reorganized into modular services
- All functionality is preserved and improved

---

## The Two Main Services

### 🔵 Service 1: Extract Concepts from Documents
**Location**: `services/ingestion.py`

Extracts concepts from DOCX files in the `unstructured_script/` folder and saves them to `batch_output/`.

### 🔵 Service 2: Link CONCEPT Nodes  
**Location**: `services/enhanced_langgraph_service.py`

Detects relationships between concepts and creates semantic links in Neo4j.

---

## Quick Commands

### 🚀 Option 1: Use Pre-Extracted Data (Fastest)
Load the 38 already-processed documents into Neo4j:

```bash
cd knowledge_graph_builder
python scripts/ingest_ready_data.py --clear
```

### 🚀 Option 2: Run Both Services  
Extract from documents AND detect relationships:

```bash
cd knowledge_graph_builder
python run_extraction_and_linking.py --all
```

### 🚀 Option 3: Run Services Separately

**Extract concepts only:**
```bash
python run_extraction_and_linking.py --extract
```

**Detect relationships only:**
```bash
python run_extraction_and_linking.py --link
```

**Extract single file:**
```bash
python run_extraction_and_linking.py --extract --file unstructured_script/document.docx
```

---

## What Each Service Does

### Service 1: Concept Extraction
```
unstructured_script/*.docx 
    ↓
[LangChain LLM Extraction]
    ↓
batch_output/{Topic}/*_extraction.json
    ↓
Neo4j (TOPIC → CONCEPT nodes)
```

**Creates**:
- `TOPIC` nodes (one per document)
- `CONCEPT` nodes (extracted terms with definitions)
- `HAS_CONCEPT` relationships

### Service 2: Relationship Detection
```
Neo4j CONCEPT nodes
    ↓
[LangGraph Workflow]
    ↓
output/final.json
    ↓
Neo4j (CONCEPT → CONCEPT relationships)
```

**Creates**:
- Concept merges (e.g., "PCA" → "Principal Component Analysis")
- Semantic relationships (`USED_FOR`, `RELATED_TO`, `IS_A`, `PART_OF`)

---

## File Locations

| What | Where |
|------|-------|
| Source documents (38 DOCX files) | `unstructured_script/` |
| Extracted concepts (38 topics) | `batch_output/` |
| Normalized relationships | `output/final.json` |
| Service 1 code | `services/ingestion.py` |
| Service 2 code | `services/enhanced_langgraph_service.py` |
| **New main entry point** | `run_extraction_and_linking.py` |
| Load pre-extracted data | `scripts/ingest_ready_data.py` |

---

## Environment Setup

Create `.env` file in `knowledge_graph_builder/`:

```bash
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password123

# For Service 1 (Extraction)
GOOGLE_API_KEY=your_gemini_api_key

# For Service 2 (Relationship Detection)
XIAO_CASE_API_KEY=your_openai_api_key
XIAO_CASE_API_BASE=https://api.xiaocaseai.com/v1
```

---

## Full Example Workflow

```bash
# 1. Start Neo4j
cd /Users/khajievroma/Projects/lab_tutor
docker-compose up -d

# 2. Go to knowledge_graph_builder
cd knowledge_graph_builder

# 3. Install dependencies (if needed)
uv sync

# 4. OPTION A: Load pre-extracted data (recommended for quick start)
python scripts/ingest_ready_data.py --clear

# 4. OPTION B: Re-extract everything from documents
python run_extraction_and_linking.py --all --clear

# 5. Access Neo4j Browser
open http://localhost:7474
# Username: neo4j
# Password: password123
```

---

## Programmatic Usage

```python
from services.ingestion import IngestionService
from neo4j_database import Neo4jService
from services.enhanced_langgraph_service import EnhancedRelationshipService
from models.langgraph_state_models import WorkflowConfiguration

# === SERVICE 1: Extract concepts ===
ingestion = IngestionService()

# Single document
result = ingestion.process_single_document(
    docx_path="unstructured_script/document.docx",
    output_dir="batch_output",
    insert_to_neo4j=True
)

# Batch processing
result = ingestion.process_batch_documents(
    input_directory="unstructured_script",
    output_directory="batch_output",
    clear_database=True
)

# === SERVICE 2: Detect relationships ===
neo4j = Neo4jService()
config = WorkflowConfiguration(
    max_iterations=5,
    verbose_logging=True,
    relationship_types={
        "USED_FOR": "Practical application",
        "RELATED_TO": "Semantic connection",
        "IS_A": "Taxonomic relationship",
        "PART_OF": "Compositional relationship"
    }
)

service = EnhancedRelationshipService(neo4j, config)
relationships, output_path, stats = service.detect_relationships()

print(f"Found {stats['total_valid_relationships']} relationships")
print(f"Saved to: {output_path}")
```

---

## Troubleshooting

### "No concepts found in database"
→ Run Service 1 first to extract concepts

### "GOOGLE_API_KEY not found"
→ Add API key to `.env` file

### "Neo4j connection failed"
→ Start Neo4j: `docker-compose up -d`

### "enhanced_langgraph_service.py is empty"
→ Already fixed! The file was accidentally deleted and has been restored.

---

## Summary

✅ **main.py replaced by**: `run_extraction_and_linking.py`  
✅ **Service 1** (Extraction): `services/ingestion.py`  
✅ **Service 2** (Linking): `services/enhanced_langgraph_service.py`  
✅ **Quick data load**: `scripts/ingest_ready_data.py`  

All your original functionality is preserved and enhanced!

