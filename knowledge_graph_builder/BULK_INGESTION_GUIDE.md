# Bulk Ingestion Guide for Simplified Relationship-Centric Approach

This guide explains how to perform bulk ingestion using the simplified relationship-centric approach where MENTIONS relationships store only essential properties: `local_definition` and `source_file`.

## Overview

The simplified relationship-centric approach provides:
- **Clean provenance**: Every definition is traceable to its source document
- **Contextual definitions**: Multiple definitions per concept from different sources
- **Simplified structure**: Only essential relationship properties
- **Performance**: Direct relationship traversal without complex property arrays

## Relationship Structure

```cypher
(THEORY)-[:MENTIONS {
  local_definition: "exact definition from document",
  source_file: "document_name.docx"
}]->(CONCEPT)
```

## Available Scripts

### 1. Bulk Ingest Existing Files (`scripts/bulk_ingest_existing_files.py`)

Ingests all existing Neo4j-ready JSON files from the production_output directory.

**Usage:**
```bash
# Dry run to see what would be processed
python scripts/bulk_ingest_existing_files.py --dry-run

# Ingest all files (preserves existing data)
python scripts/bulk_ingest_existing_files.py

# Clear database and ingest all files (fresh start)
python scripts/bulk_ingest_existing_files.py --clear-db

# Use custom directory
python scripts/bulk_ingest_existing_files.py --base-dir custom_output
```

**Features:**
- Analyzes file structures (enhanced vs legacy)
- Shows progress and statistics
- Handles both old and new file formats
- Optional database clearing

### 2. Bulk Re-process DOCX Files (`scripts/bulk_reprocess_docx_files.py`)

Re-processes all DOCX files to generate new Neo4j-ready JSON files with enhanced relationship properties.

**Usage:**
```bash
# Dry run to see what would be processed
python scripts/bulk_reprocess_docx_files.py --dry-run

# Re-process all DOCX files
python scripts/bulk_reprocess_docx_files.py --output-dir enhanced_output

# Re-process and automatically ingest to Neo4j
python scripts/bulk_reprocess_docx_files.py --output-dir enhanced_output --ingest

# Clear database, re-process, and ingest (complete refresh)
python scripts/bulk_reprocess_docx_files.py --output-dir enhanced_output --ingest --clear-db
```

**Features:**
- Finds DOCX files automatically
- Estimates processing time
- Generates enhanced Neo4j-ready files
- Optional automatic ingestion
- Progress tracking with ETA

## Recommended Workflows

### Scenario 1: Quick Start with Existing Files

If you want to quickly populate the database with existing processed files:

```bash
# 1. Clear database and ingest existing files
cd knowledge_graph_builder
python scripts/bulk_ingest_existing_files.py --clear-db

# 2. Check results
python -c "
from services.neo4j_service import Neo4jService
neo4j = Neo4jService()
stats = neo4j.get_database_stats()
for k, v in stats.items(): print(f'{k}: {v}')
"
```

### Scenario 2: Complete Refresh with Enhanced Structure

If you want to re-process everything with the new enhanced relationship structure:

```bash
# 1. Re-process all DOCX files and ingest (this will take ~2-3 hours for 39 files)
cd knowledge_graph_builder
python scripts/bulk_reprocess_docx_files.py \
  --output-dir enhanced_output \
  --ingest \
  --clear-db

# 2. Verify enhanced relationships
python -c "
from services.neo4j_service import Neo4jService
neo4j = Neo4jService()
result = neo4j.query('''
  MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
  RETURN c.name, r.local_definition, r.source_file
  LIMIT 3
''')
for row in result:
  print(f'Concept: {row[\"c.name\"]}')
  print(f'Definition: {row[\"r.local_definition\"]}')
  print(f'Source: {row[\"r.source_file\"]}')
  print()
"
```

### Scenario 3: Hybrid Approach

If you want to use existing files but also generate some enhanced ones:

```bash
# 1. Ingest existing files first
python scripts/bulk_ingest_existing_files.py --clear-db

# 2. Re-process specific important documents
python scripts/bulk_reprocess_docx_files.py \
  --output-dir enhanced_output \
  --ingest \
  --base-dir unstructured_script
```

## File Structure Analysis

The bulk ingestion scripts can distinguish between:

- **Enhanced files**: Have MENTIONS relationships with `local_definition` and `source_file` properties
- **Legacy files**: Have basic MENTIONS relationships without enhanced properties

Both types work with the current system, but enhanced files provide richer provenance and querying capabilities.

## Performance Considerations

### Processing Time Estimates
- **Existing file ingestion**: ~1-2 seconds per file (39 files = ~1-2 minutes)
- **DOCX re-processing**: ~2-3 minutes per file (39 files = ~2-3 hours)

### Memory and Storage
- Each processed document generates ~50-200KB of JSON data
- Neo4j database size: ~10-50MB for 39 documents
- Enhanced relationships add minimal storage overhead

## Monitoring and Verification

### Check Database Statistics
```python
from services.neo4j_service import Neo4jService
neo4j = Neo4jService()
stats = neo4j.get_database_stats()
print(f"CONCEPT nodes: {stats['CONCEPT nodes']}")
print(f"MENTIONS relationships: {stats['MENTIONS relationships']}")
```

### Verify Enhanced Relationships
```cypher
// Check for enhanced MENTIONS relationships
MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
WHERE exists(r.local_definition) AND exists(r.source_file)
RETURN count(*) as enhanced_mentions

// Sample enhanced relationships
MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
WHERE exists(r.local_definition)
RETURN c.name, r.local_definition, r.source_file
LIMIT 5
```

### Query Examples with Enhanced Structure
```cypher
// Get all definitions of a specific concept
MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT {name: "MapReduce"})
RETURN r.local_definition, r.source_file

// Find concepts mentioned in a specific document
MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
WHERE r.source_file = "intro_course.docx"
RETURN c.name, r.local_definition

// Count mentions per document
MATCH (t:THEORY)-[r:MENTIONS]->(c:CONCEPT)
RETURN r.source_file, count(*) as concept_count
ORDER BY concept_count DESC
```

## Troubleshooting

### Common Issues
1. **Neo4j connection errors**: Ensure Neo4j is running on bolt://localhost:7687
2. **File not found errors**: Check file paths and permissions
3. **Memory errors**: Process files in smaller batches if needed
4. **LLM API errors**: Check API keys and rate limits

### Recovery Strategies
- Use `--dry-run` to test before actual processing
- Process files in smaller batches if needed
- Keep backups of important Neo4j-ready JSON files
- Use database exports before major operations

## Next Steps

After bulk ingestion, you can:
1. Explore the knowledge graph with Cypher queries
2. Use vector similarity search for concept discovery
3. Build applications using the Neo4j graph data
4. Add more sophisticated relationship properties as needed
