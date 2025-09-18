# Docker Setup for Neo4j Data Ingestion

This guide explains how to set up automatic data ingestion when running your Docker container on a new machine.

## 🚀 Quick Setup

### Step 1: Copy Your Data
When moving to a new machine, ensure you have:
```
knowledge_graph_builder/
├── production_output/          # Your extracted data
│   ├── Topic_1/neo4j_ready/
│   ├── Topic_2/neo4j_ready/
│   └── ...
├── ingest_data.sh             # Main ingestion script
├── docker_ingest.py           # Docker-friendly script
└── ingest_extracted_data.py   # Full-featured script
```

### Step 2: Start Your Containers
```bash
docker-compose up -d
```

### Step 3: Run Data Ingestion
```bash
# Option A: Simple automatic ingestion
docker exec -it lab_tutor_neo4j ./ingest_data.sh

# Option B: Full control with detailed output
docker exec -it lab_tutor_neo4j ./ingest_data.sh --full

# Option C: Force re-ingestion (clears database first)
docker exec -it lab_tutor_neo4j ./ingest_data.sh --clear
```

## 🔧 Automatic Integration Options

### Option 1: Add Init Container to docker-compose.yml
```yaml
services:
  neo4j:
    build: 
      context: ./neo4j_database
      dockerfile: Dockerfile
    container_name: lab_tutor_neo4j
    ports:
      - "${NEO4J_HTTP_PORT:-7474}:7474"
      - "${NEO4J_BOLT_PORT:-7687}:7687"
    environment:
      NEO4J_AUTH: ${NEO4J_AUTH:-neo4j/password123}
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - neo4j_import:/import
      - neo4j_plugins:/plugins
    restart: unless-stopped
    networks:
      - lab_tutor_network
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p $${NEO4J_AUTH##*/} 'RETURN 1' || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  # Add this service for automatic data ingestion
  neo4j-data-loader:
    build:
      context: ./knowledge_graph_builder
      dockerfile: Dockerfile.ingestion
    depends_on:
      neo4j:
        condition: service_healthy
    volumes:
      - ./knowledge_graph_builder/production_output:/app/production_output:ro
    environment:
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USERNAME: neo4j
      NEO4J_PASSWORD: password123
    command: ["./ingest_data.sh"]
    networks:
      - lab_tutor_network
    restart: "no"  # Run once and exit

volumes:
  neo4j_data:
    driver: local
  neo4j_logs:
    driver: local
  neo4j_import:
    driver: local
  neo4j_plugins:
    driver: local

networks:
  lab_tutor_network:
    driver: bridge
    name: lab_tutor_network
```

### Option 2: Create Dockerfile.ingestion
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install required packages
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

# Copy ingestion scripts and services
COPY ingest_data.sh docker_ingest.py ingest_extracted_data.py ./
COPY services/ ./services/
COPY utils/ ./utils/

# Make shell script executable
RUN chmod +x ingest_data.sh

# Default command
CMD ["./ingest_data.sh"]
```

### Option 3: Startup Script in Main Container
Add to your main application's Dockerfile:
```dockerfile
# Copy ingestion scripts
COPY knowledge_graph_builder/ingest_data.sh /app/
COPY knowledge_graph_builder/docker_ingest.py /app/
COPY knowledge_graph_builder/services/ /app/services/
COPY knowledge_graph_builder/utils/ /app/utils/

# Make executable
RUN chmod +x /app/ingest_data.sh

# Modify your startup command
CMD ["/app/ingest_data.sh", "&&", "your-main-application"]
```

## 📋 What the Scripts Do

### Automatic Detection
1. **Wait for Neo4j** - Ensures database is ready before attempting ingestion
2. **Check existing data** - Skips ingestion if database already contains data
3. **Find data directory** - Automatically locates `production_output` folder
4. **Validate structure** - Ensures data is in the expected format

### Data Processing
1. **Create constraints** - Sets up database indexes and constraints
2. **Process topics** - Ingests each topic folder sequentially  
3. **Handle errors** - Continues processing even if some files fail
4. **Report results** - Provides detailed statistics and error reporting

## 🔍 Monitoring and Logs

### Check Ingestion Status
```bash
# View container logs
docker logs lab_tutor_neo4j

# Check database contents
docker exec -it lab_tutor_neo4j cypher-shell -u neo4j -p password123 "MATCH (n) RETURN labels(n), count(n)"
```

### Expected Output
```
✅ Found 6 topic folders with neo4j_ready data
🔌 Connected to Neo4j at bolt://localhost:7687
📊 Database is empty - ready for data ingestion
🚀 Starting data ingestion...
✅ Successfully processed: Topic_1
✅ Successfully processed: Topic_2
...
🎉 Data ingestion completed successfully!
📊 Final stats: 44 nodes, 39 relationships
```

## 🛠️ Troubleshooting

### Common Issues

**Container can't connect to Neo4j**
```bash
# Check if Neo4j is running
docker ps | grep neo4j

# Check network connectivity
docker exec -it your_container ping neo4j
```

**No data directory found**
```bash
# Verify volume mount
docker exec -it your_container ls -la /app/production_output

# Check directory structure
docker exec -it your_container find /app/production_output -name "*.json"
```

**Permission errors**
```bash
# Fix script permissions
docker exec -it your_container chmod +x /app/ingest_data.sh

# Check file ownership
docker exec -it your_container ls -la /app/
```

## 🎯 Best Practices

1. **Always use volume mounts** for your data directory
2. **Set proper environment variables** for Neo4j connection
3. **Use health checks** to ensure Neo4j is ready
4. **Monitor logs** during first setup
5. **Test with a small dataset** first
6. **Keep backups** of your production_output directory

## 📦 Complete Example

Here's a complete working example:

```yaml
# docker-compose.yml
version: '3.8'
services:
  neo4j:
    build: 
      context: ./neo4j_database
      dockerfile: Dockerfile
    container_name: lab_tutor_neo4j
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/password123
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p password123 'RETURN 1' || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    networks:
      - lab_tutor_network

  data-ingestion:
    build:
      context: ./knowledge_graph_builder
      dockerfile: Dockerfile.ingestion
    depends_on:
      neo4j:
        condition: service_healthy
    volumes:
      - ./knowledge_graph_builder/production_output:/app/production_output:ro
    environment:
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USERNAME: neo4j
      NEO4J_PASSWORD: password123
    networks:
      - lab_tutor_network
    restart: "no"

volumes:
  neo4j_data:
networks:
  lab_tutor_network:
```

Then simply run:
```bash
docker-compose up -d
```

The data will be automatically ingested when the containers start! 🎉
