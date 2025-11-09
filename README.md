# Lab Tutor - Knowledge Graph System

A knowledge graph system for Big Data educational content, built with Neo4j and Python.

## Quick Start for Developers

### Prerequisites
- Docker and Docker Compose
- Python 3.12+
- `uv` package manager (recommended) or `pip`

### 1. Start Neo4j Database

```bash
docker-compose up -d
```

Wait 30 seconds for Neo4j to fully initialize. You can check the logs:

```bash
docker-compose logs -f neo4j
```

### 2. Install Python Dependencies

```bash
cd knowledge_graph_builder

# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

### 3. Load Knowledge Graph Data

The repository includes pre-extracted knowledge graph data ready to ingest:

```bash
# From the knowledge_graph_builder directory
python scripts/ingest_ready_data.py
```

This will:
- Load raw concept extractions from `batch_output/` (38 documents)
- Apply concept normalizations and create relationships from `output/final.json`
- Takes approximately 2-3 minutes

#### Ingestion Options

```bash
# Clear and reload all data
python scripts/ingest_ready_data.py --clear

# Only load batch output (raw concepts)
python scripts/ingest_ready_data.py --batch-only

# Only load normalized concepts & relationships (requires batch already loaded)
python scripts/ingest_ready_data.py --final-only

# Show help
python scripts/ingest_ready_data.py --help
```

### 4. Access Neo4j Browser

- **URL**: http://localhost:7474
- **Username**: `neo4j`
- **Password**: `password123`

Try these queries to explore the graph:

```cypher
// Count all nodes and relationships
MATCH (n) RETURN labels(n) AS type, count(n) AS count

// Show topics
MATCH (t:TOPIC) RETURN t.name, size((t)-[:HAS_CONCEPT]->()) AS concepts

// Show concept relationships
MATCH (c1:CONCEPT)-[r]->(c2:CONCEPT) 
RETURN c1.name, type(r), c2.name 
LIMIT 25
```

## Access Information

- **Neo4j Browser**: http://localhost:7474
- **Bolt Connection**: bolt://localhost:7687
- **Credentials**: 
  - Username: `neo4j`
  - Password: `password123`

## Useful Commands

```bash
# Build and start services
docker-compose up -d --build

# View logs
docker-compose logs -f neo4j

# Stop services
docker-compose down

# Stop and remove volumes (WARNING: This will delete your data)
docker-compose down -v

# Access Neo4j shell
docker-compose exec neo4j cypher-shell -u neo4j -p password123
```

## Project Structure

```
lab_tutor/
├── knowledge_graph_builder/    # Knowledge graph extraction and ingestion
│   ├── batch_output/           # Pre-extracted concepts from 38 documents (committed)
│   ├── output/                 # Normalized concepts and relationships (committed)
│   │   └── final.json         # Final normalized knowledge graph data
│   ├── scripts/               # User-facing scripts
│   │   └── ingest_ready_data.py  # Main ingestion script
│   ├── services/              # Core services (Neo4j, extraction, etc.)
│   ├── models/                # Pydantic models
│   ├── prompts/               # LLM prompts for extraction
│   └── utils/                 # Utility functions
├── docker-compose.yml         # Docker services configuration
└── README.md                  # This file
```

## Knowledge Graph Schema

The knowledge graph contains:

- **TOPIC** nodes: Educational topics (e.g., "Big Data Concepts")
- **CONCEPT** nodes: Individual concepts with definitions
- **HAS_CONCEPT** relationships: Links topics to their concepts
- **USED_FOR** relationships: Functional relationships between concepts
- **RELATED_TO** relationships: Semantic relationships between concepts

## Configuration

Environment variables can be configured via `.env` file or `docker-compose.yml`:

- `NEO4J_AUTH`: Neo4j credentials (default: `neo4j/password123`)
- `NEO4J_HTTP_PORT`: HTTP port for Neo4j Browser (default: `7474`)
- `NEO4J_BOLT_PORT`: Bolt protocol port (default: `7687`)

## Troubleshooting

### Neo4j won't start
```bash
# Check logs
docker-compose logs neo4j

# Restart with clean volumes
docker-compose down -v
docker-compose up -d
```

### Ingestion fails with connection error
```bash
# Ensure Neo4j is running and healthy
docker-compose ps

# Check Neo4j health
curl http://localhost:7474
```

### Clear and reload data
```bash
cd knowledge_graph_builder
python scripts/ingest_ready_data.py --clear
```

## Development

This project uses:
- **Neo4j**: Graph database
- **LangChain**: LLM orchestration (for future extraction tasks)
- **Python 3.12+**: Core language
- **uv**: Fast Python package manager

## Adding New Services

When adding new services, add them to the `docker-compose.yml` file and ensure they use the `lab_tutor_network` network to communicate with Neo4j.
