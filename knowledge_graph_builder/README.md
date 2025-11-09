# Knowledge Graph Builder

This module extracts concepts from educational documents and builds a semantic knowledge graph in Neo4j using LLM-powered extraction and relationship detection.

## Overview

The knowledge graph builder provides **two main services**:

1. **📚 Service 1: Concept Extraction** - Extract concepts from DOCX documents in `unstructured_script/`
2. **🔗 Service 2: Relationship Detection** - Find semantic relationships between concepts using LangGraph

The repository includes pre-extracted data from **38 Big Data course documents** ready to load.

## Quick Start

### Option A: Load Pre-Extracted Data (Fastest ⚡)

Use the 38 already-processed documents:

```bash
# 1. Start Neo4j (from project root)
cd /Users/khajievroma/Projects/lab_tutor
docker-compose up -d

# 2. Go to knowledge_graph_builder directory
cd knowledge_graph_builder

# 3. Install dependencies
uv sync  # or: pip install -e .

# 4. Load pre-extracted data into Neo4j
python scripts/ingest_ready_data.py --clear
```

### Option B: Run Both Services (Full Pipeline 🚀)

Extract from documents AND detect relationships:

```bash
# Prerequisites: Set up environment variables (see below)

# Run both services
python run_extraction_and_linking.py --all --clear
```

### Option C: Run Services Individually

```bash
# Service 1 only: Extract concepts from DOCX files
python run_extraction_and_linking.py --extract

# Service 2 only: Detect relationships (requires concepts in DB)
python run_extraction_and_linking.py --link
```

## Directory Structure

```
knowledge_graph_builder/
├── unstructured_script/       # Source DOCX files (38 documents)
├── batch_output/              # Pre-extracted concepts (38 topics)
│   └── {Topic_Name}/
│       └── {filename}_extraction.json
├── output/
│   └── final.json            # Normalized concepts & relationships
├── services/                  # ⭐ Core Services
│   ├── ingestion.py          # SERVICE 1: Concept extraction
│   ├── enhanced_langgraph_service.py  # SERVICE 2: Relationship detection
│   ├── extraction_langchain.py        # LLM extraction logic
│   ├── neo4j_service.py      # Neo4j database operations
│   └── embedding.py          # Vector embeddings (optional)
├── scripts/
│   ├── ingest_ready_data.py  # Load pre-extracted data into Neo4j
│   └── run_extraction_and_linking.py  # ⭐ Main entry point for both services
├── models/                    # Pydantic data models
│   ├── extraction_models.py
│   ├── neo4j_models.py
│   └── langgraph_state_models.py
├── prompts/                   # LLM prompt templates
│   ├── extraction_prompts.py
│   ├── concept_normalization_prompts.py
│   └── enhanced_relationship_prompts.py
└── utils/                     # Utility functions
    ├── doc_utils.py          # Document loading
    └── output_utils.py       # File organization
```

## Data Files

### batch_output/
Contains 38 pre-extracted JSON files, each with:
- **topic**: The educational topic name
- **summary**: Brief summary of the content
- **keywords**: Key terms from the document
- **concepts**: Array of concepts with definitions and evidence

Example structure:
```json
{
  "topic": "Big Data Concepts",
  "concepts": [
    {
      "name": "Big data",
      "definition": "Large, hard-to-manage volumes of data",
      "text_evidence": "..."
    }
  ]
}
```

### output/final.json
Contains normalized and enhanced knowledge graph data:
- **concept_merges**: Canonical forms of duplicate concepts (e.g., "PCA" → "Principal Component Analysis")
- **relationships**: Semantic relationships between concepts (USED_FOR, RELATED_TO, IS_A, PART_OF)

---

## Using the Services

### Service 1: Concept Extraction (`services/ingestion.py`)

Extracts concepts from DOCX files and saves them to `batch_output/`.

#### Command Line Usage

```bash
# Extract all DOCX files from unstructured_script/
python run_extraction_and_linking.py --extract

# Extract single file
python run_extraction_and_linking.py --extract --file unstructured_script/document.docx

# Clear database first, then extract
python run_extraction_and_linking.py --extract --clear
```

#### Programmatic Usage

```python
from services.ingestion import IngestionService

# Initialize service
ingestion = IngestionService()

# Process single document
result = ingestion.process_single_document(
    docx_path="unstructured_script/Big_Data_Concepts.docx",
    output_dir="batch_output",
    insert_to_neo4j=True
)

print(f"Topic: {result['topic_name']}")
print(f"Saved to: {result['topic_folder']}")

# Process entire directory (batch)
batch_result = ingestion.process_batch_documents(
    input_directory="unstructured_script",
    output_directory="batch_output",
    clear_database=False
)

print(f"Processed {batch_result['successful']} / {batch_result['total_files']} files")
```

**What it does:**
1. Loads DOCX files from `unstructured_script/`
2. Uses LangChain + Google Gemini to extract concepts
3. Saves JSON files to `batch_output/{Topic_Name}/`
4. Creates `TOPIC` and `CONCEPT` nodes in Neo4j
5. Creates `HAS_CONCEPT` relationships

---

### Service 2: Relationship Detection (`services/enhanced_langgraph_service.py`)

Detects semantic relationships between concepts using LangGraph workflows.

#### Command Line Usage

```bash
# Detect relationships for all concepts in database
python run_extraction_and_linking.py --link

# Customize iterations and output file
python run_extraction_and_linking.py --link --max-iterations 10 --output-file my_results.json
```

#### Programmatic Usage

```python
from services.neo4j_service import Neo4jService
from services.enhanced_langgraph_service import EnhancedRelationshipService
from models.langgraph_state_models import WorkflowConfiguration

# Initialize services
neo4j = Neo4jService()

# Configure workflow
config = WorkflowConfiguration(
    max_iterations=5,
    verbose_logging=True,
    relationship_types={
        "USED_FOR": "Indicates practical application or purpose",
        "RELATED_TO": "General semantic or contextual connection",
        "IS_A": "Taxonomic relationship (subtype/supertype)",
        "PART_OF": "Component or compositional relationship"
    }
)

# Run relationship detection
service = EnhancedRelationshipService(neo4j, config)
relationships, output_path, stats = service.detect_relationships(
    output_file="final.json"
)

# Print results
print(f"Found {stats['total_valid_relationships']} relationships")
print(f"Found {stats['total_concept_merges']} concept merges")
print(f"Iterations: {stats['total_iterations']}")
print(f"Saved to: {output_path}")

# Sample relationships
for rel in relationships[:5]:
    print(f"{rel.s} --[{rel.rel}]--> {rel.t}")
    print(f"  Reasoning: {rel.r}")
```

**What it does:**
1. Fetches all `CONCEPT` nodes from Neo4j
2. Uses LangGraph workflow to iteratively:
   - Find similar concepts and merge them (normalization)
   - Generate semantic relationships
   - Validate quality (binary: valid/weak)
   - Accumulate high-quality results
3. Converges when no weak relationships are found
4. Saves results to `output/final.json`

---

### Running Both Services Together

```bash
# Extract concepts AND detect relationships
python run_extraction_and_linking.py --all --clear

# With custom options
python run_extraction_and_linking.py --all \
    --input-dir unstructured_script \
    --output-dir batch_output \
    --max-iterations 10 \
    --clear
```

---

## Ingestion Script

The `scripts/ingest_ready_data.py` script handles two-stage ingestion:

### Stage 1: Batch Output
- Loads raw concept extractions from `batch_output/`
- Creates TOPIC and CONCEPT nodes
- Creates HAS_CONCEPT relationships

### Stage 2: Normalized Concepts
- Applies concept merges (e.g., "PCA" → "Principal Component Analysis")
- Creates concept relationships (USED_FOR, RELATED_TO)

### Usage

```bash
# Full ingestion (both stages)
python scripts/ingest_ready_data.py

# Clear database and reload
python scripts/ingest_ready_data.py --clear

# Stage 1 only (batch output)
python scripts/ingest_ready_data.py --batch-only

# Stage 2 only (normalized concepts)
python scripts/ingest_ready_data.py --final-only
```

## Environment Variables

Create a `.env` file in the `knowledge_graph_builder/` directory:

```bash
# Neo4j Connection (required for both services)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password123

# Service 1: Concept Extraction
# Uses Google Gemini for LLM-based extraction
GOOGLE_API_KEY=your_gemini_api_key_here

# Service 2: Relationship Detection
# Uses OpenAI GPT-4 for relationship generation
XIAO_CASE_API_KEY=your_openai_api_key_here
XIAO_CASE_API_BASE=https://api.xiaocaseai.com/v1
```

**Note**: If you only want to use the pre-extracted data (`scripts/ingest_ready_data.py`), you only need the Neo4j credentials.

## Development

### Adding New Documents

To extract concepts from new documents:

1. Place DOCX files in `unstructured_script/` directory
2. Set up environment variables (Google API key required)
3. Run extraction service:
   ```bash
   python run_extraction_and_linking.py --extract
   ```
4. Results will be saved to `batch_output/{Topic_Name}/`

### Service Architecture

**Main Services:**
- **`IngestionService`** (`services/ingestion.py`): Document processing and concept extraction pipeline
- **`EnhancedRelationshipService`** (`services/enhanced_langgraph_service.py`): LangGraph-based relationship detection with quality control

**Supporting Services:**
- **`Neo4jService`** (`services/neo4j_service.py`): Database operations, queries, constraints
- **`LangChainCanonicalExtractionService`** (`services/extraction_langchain.py`): LLM-based concept extraction
- **`EmbeddingService`** (`services/embedding.py`): Vector embeddings for concepts (optional)

## Dependencies

Managed via `pyproject.toml`:

- `langchain` & `langchain-neo4j`: LLM orchestration and Neo4j integration
- `langgraph`: Graph-based LLM workflows
- `python-docx`: Document parsing
- `openai`: LLM API access
- `pydantic`: Data validation

Install with:
```bash
uv sync  # Fast, recommended
# or
pip install -e .
```

## Complete Example Workflow

Here's a complete example showing both services in action:

```python
#!/usr/bin/env python3
"""
Complete workflow example: Extract concepts and build relationships
"""
from services.ingestion import IngestionService
from services.neo4j_service import Neo4jService
from services.enhanced_langgraph_service import EnhancedRelationshipService
from models.langgraph_state_models import WorkflowConfiguration

# Step 1: Extract concepts from documents
print("Step 1: Extracting concepts from documents...")
ingestion = IngestionService()

result = ingestion.process_batch_documents(
    input_directory="unstructured_script",
    output_directory="batch_output",
    clear_database=True  # Start fresh
)

print(f"✅ Extracted concepts from {result['successful']} documents")
print(f"   Output saved to: batch_output/")

# Step 2: Detect relationships between concepts
print("\nStep 2: Detecting relationships between concepts...")
neo4j = Neo4jService()

# Configure relationship detection
config = WorkflowConfiguration(
    max_iterations=5,
    verbose_logging=True,
    relationship_types={
        "USED_FOR": "Indicates practical application or purpose",
        "RELATED_TO": "General semantic or contextual connection",
        "IS_A": "Taxonomic relationship (subtype/supertype)",
        "PART_OF": "Component or compositional relationship"
    }
)

# Run relationship detection
service = EnhancedRelationshipService(neo4j, config)
relationships, output_path, stats = service.detect_relationships(
    output_file="final.json"
)

print(f"✅ Detected {stats['total_valid_relationships']} relationships")
print(f"✅ Merged {stats['total_concept_merges']} duplicate concepts")
print(f"   Results saved to: {output_path}")

# Step 3: Query the knowledge graph
print("\nStep 3: Querying the knowledge graph...")

# Get all concepts
all_concepts = neo4j.get_all_concepts()
print(f"Total concepts in graph: {len(all_concepts)}")

# Get database statistics
db_stats = neo4j.get_database_stats()
print("\nDatabase Statistics:")
for key, value in db_stats.items():
    print(f"  {key}: {value}")

print("\n✅ Knowledge graph is ready!")
print("   Access Neo4j Browser at: http://localhost:7474")
```

**Running this example:**
```bash
# Save the code above to a file
python my_workflow.py

# Or use the provided script
python run_extraction_and_linking.py --all --clear
```

---

## Troubleshooting

### Import errors
```bash
# Ensure you're in the knowledge_graph_builder directory
cd knowledge_graph_builder

# Install dependencies
uv sync
```

### Neo4j connection errors
```bash
# Check Neo4j is running
docker-compose ps

# Test connection
python -c "from services.neo4j_service import Neo4jService; Neo4jService()"
```

### Ingestion fails
```bash
# Clear database and try again
python scripts/ingest_ready_data.py --clear

# Check Neo4j logs
docker-compose logs neo4j
```

### Service 1 (Extraction) fails
```bash
# Check if GOOGLE_API_KEY is set
python -c "import os; print(os.getenv('GOOGLE_API_KEY'))"

# Test extraction service
python -c "from services.extraction_langchain import LangChainCanonicalExtractionService; service = LangChainCanonicalExtractionService()"
```

### Service 2 (Relationship Detection) fails
```bash
# Check if XIAO_CASE_API_KEY is set
python -c "import os; print(os.getenv('XIAO_CASE_API_KEY'))"

# Verify concepts exist in database
python -c "from services.neo4j_service import Neo4jService; neo4j = Neo4jService(); print(f'Concepts: {len(neo4j.get_all_concepts())}')"
```

### "No concepts found in database"
This means Service 2 cannot find any concepts to link. Run Service 1 first:
```bash
python run_extraction_and_linking.py --extract
# OR load pre-extracted data:
python scripts/ingest_ready_data.py
```

---

## Additional Resources

- **ARCHITECTURE_SUMMARY.md** - Detailed architecture documentation
- **QUICK_START.md** - Quick reference guide
- **COMPREHENSIVE_RESEARCH_REPORT.md** - Research and design decisions
- **diagrams/** - Workflow visualizations (Mermaid diagrams)

---

## License

Internal educational project.

