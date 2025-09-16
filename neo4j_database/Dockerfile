FROM neo4j:latest

# Set default environment variables
ENV NEO4J_AUTH=neo4j/password123
ENV NEO4J_dbms_memory_heap_initial__size=512m
ENV NEO4J_dbms_memory_heap_max__size=1G
ENV NEO4J_dbms_memory_pagecache_size=512m

# Install APOC plugin
ENV NEO4J_PLUGINS='["apoc"]'
ENV NEO4J_apoc_export_file_enabled=true
ENV NEO4J_apoc_import_file_enabled=true
ENV NEO4J_apoc_import_file_use__neo4j__config=true

# Expose Neo4j ports
EXPOSE 7474 7687

# Default volumes for data persistence
VOLUME ["/data", "/logs", "/import", "/plugins"]