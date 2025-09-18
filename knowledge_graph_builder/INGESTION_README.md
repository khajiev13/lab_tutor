# Neo4j Data Ingestion Scripts

This directory contains scripts to ingest extracted Neo4j-ready data into the Neo4j database. These scripts are particularly useful when setting up the Docker container on a new machine and need to restore previously extracted knowledge graph data.

## Quick Start

### For Docker Users (Recommended)
```bash
# Simple automatic ingestion
./ingest_data.sh

# Or directly with Python
python docker_ingest.py
```

### For Manual Control
```bash
# Full ingestion with detailed output
python ingest_extracted_data.py

# Clear database and ingest
python ingest_extracted_data.py --clear-db
```

## Files Overview

### 1. `ingest_data.sh` ⭐ **Recommended**
**Shell script with multiple modes**

Simple interface that wraps the Python scripts:
- `./ingest_data.sh` - Auto-detect and ingest (Docker-friendly)
- `./ingest_data.sh --full` - Full ingestion with detailed output  
- `./ingest_data.sh --clear` - Clear database and ingest
- `./ingest_data.sh --help` - Show help

### 2. `docker_ingest.py`
**Docker-friendly automatic ingestion**

Designed for container environments:
- ✅ Waits for Neo4j to be ready
- ✅ Checks if database already has data
- ✅ Auto-finds production_output directory
- ✅ Simple logging for container monitoring

### 3. `ingest_extracted_data.py`
**Full-featured ingestion with CLI options**

Advanced control with command-line arguments:
- ✅ Custom directory support
- ✅ Database clearing option
- ✅ Detailed progress reporting
- ✅ Comprehensive error handling

## Expected Directory Structure

```
production_output/
├── Topic_Name_1/
│   └── neo4j_ready/
│       ├── document1_neo4j.json
│       └── document2_neo4j.json
├── Topic_Name_2/
│   └── neo4j_ready/
│       └── document3_neo4j.json
└── ...
```

## Docker Integration Examples

### Option 1: Manual Execution (Simplest)
```bash
# Start your containers
docker-compose up -d

# Run ingestion inside the container
docker exec -it your_container_name ./ingest_data.sh
```

### Option 2: Add to docker-compose.yml
```yaml
services:
  neo4j:
    # ... your existing neo4j config ...
  
  data-ingestion:
    build:
      context: ./knowledge_graph_builder
    depends_on:
      neo4j:
        condition: service_healthy
    volumes:
      - ./knowledge_graph_builder/production_output:/app/production_output
    command: ["./ingest_data.sh"]
    networks:
      - your_network
    restart: "no"  # Run once and exit
```

### Option 3: Container Startup Script
Add to your main container's startup:
```dockerfile
COPY ingest_data.sh /app/
RUN chmod +x /app/ingest_data.sh
CMD ["./ingest_data.sh", "&&", "your-main-command"]
```

## Usage Examples

### Basic Usage
```bash
# Auto-detect and ingest (safest option)
./ingest_data.sh

# Check what would be ingested
python ingest_extracted_data.py --output-dir production_output
```

### Advanced Usage
```bash
# Force complete re-ingestion
./ingest_data.sh --clear

# Ingest from custom directory
python ingest_extracted_data.py --output-dir /path/to/custom/data --clear-db

# Docker container with custom data location
docker run -v /host/data:/app/production_output your_image ./ingest_data.sh
```

## Connection Configuration

Scripts use environment variables or defaults:
- `NEO4J_URI` (default: `bolt://localhost:7687`)
- `NEO4J_USERNAME` (default: `neo4j`)  
- `NEO4J_PASSWORD` (default: `password`)

## Troubleshooting

### Common Issues

**"Neo4j connection failed"**
```bash
# Check if Neo4j is running
docker ps | grep neo4j

# Check connection details
echo $NEO4J_URI $NEO4J_USERNAME
```

**"No topic folders found"**
```bash
# Verify directory structure
ls -la production_output/*/neo4j_ready/

# Check for JSON files
find production_output -name "*.json" -path "*/neo4j_ready/*"
```

**"Database already contains data"**
```bash
# Clear and re-ingest
./ingest_data.sh --clear

# Or manually clear
python ingest_extracted_data.py --clear-db
```

### Logging Symbols
- ✅ Success
- ⚠️  Warning  
- ❌ Error
- 📊 Statistics
- 🔌 Connection
- 📁 Directory operations

## Data Format

The scripts expect Neo4j-ready JSON files with this structure:
```json
{
  "nodes": [
    {
      "id": "unique_id",
      "label": "NODE_TYPE", 
      "properties": { "key": "value" }
    }
  ],
  "relationships": [
    {
      "relationship_type": "RELATIONSHIP_TYPE",
      "from_node_id": "source_id",
      "to_node_id": "target_id"
    }
  ]
}
```

## Best Practices

1. **Always use `./ingest_data.sh`** for simplicity
2. **Let the script auto-detect** existing data
3. **Use `--clear` only when necessary** (data loss risk)
4. **Check logs** for any warnings or errors
5. **Verify ingestion** by checking database stats

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Verify your directory structure matches the expected format
3. Ensure Neo4j is running and accessible
4. Check the detailed logs for specific error messages
