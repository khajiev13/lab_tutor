---
description: Write, test, or debug Neo4j Cypher queries. Use for knowledge graph ingestion scripts, schema exploration, new relationships, or vector similarity queries. Always checks live schema first.
---

# Neo4j Cypher Workflow

## Step 1 — Get live schema
// turbo
Use mcp__neo4j-database__get_neo4j_schema to fetch current node labels, relationship types, and properties.
// capture: LIVE_SCHEMA

## Step 2 — Understand the task
> Using $LIVE_SCHEMA, identify:
> - Which nodes and relationships are involved
> - Whether this is a read query, write query, or both
> - Whether batch processing is needed (UNWIND pattern)
> - Whether vector similarity is involved

## Step 3 — Write query
Role: Neo4j Cypher Specialist
Use the `neo4j-cypher` skill.

Rules (non-negotiable):
- No nested OPTIONAL MATCH — use WITH + COLLECT pattern instead
- MERGE for all node/relationship upserts (idempotency)
- UNWIND for all batch writes
- Parameterize all values — no string formatting in Cypher
- Verify labels against $LIVE_SCHEMA before using

## Step 4 — Test as read first
// turbo
Run a dry-run version of the query as a MATCH/RETURN to verify it targets the right data before writing.
Use mcp__neo4j-database__read_neo4j_cypher
// capture: DRY_RUN_RESULT

> Review $DRY_RUN_RESULT. If wrong data or empty results, fix the query before writing.

## Step 5 — Execute write
> Only after dry-run confirms correct targeting.
Use mcp__neo4j-database__write_neo4j_cypher
// capture: WRITE_RESULT

> Report: nodes created/merged, relationships created/merged, row count.

## Step 6 — Verify
// turbo
Run a verification MATCH query to confirm the data is correctly stored.
Use mcp__neo4j-database__read_neo4j_cypher
