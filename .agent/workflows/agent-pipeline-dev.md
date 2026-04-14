---
description: Develop or modify one of the four Lab Tutor AI agents (Curricular Alignment Architect, Market Demand Analyst, Textual Resource Analyst, Video Agent). Use when adding new agent nodes, tools, state schemas, or LangGraph workflow steps.
---

# AI Agent Development Workflow

Structured development for Lab Tutor's LangGraph agents.

## Step 1 — Load context in parallel
// parallel

### Schema Agent
Task: Read the current Neo4j schema via MCP tool and summarize:
- Relevant node labels and relationships for this agent's domain
- Any missing nodes/relationships that the new feature will need
// capture: GRAPH_SCHEMA

### Codebase Agent
Task: Read the target agent's module directory and summarize:
- Current state schema (TypedDict fields)
- Existing nodes and edges in the StateGraph
- Current tools and their signatures
- LangSmith project name
// capture: CURRENT_IMPL

## Step 2 — Design phase (Planning mode)
> Using $GRAPH_SCHEMA and $CURRENT_IMPL, produce:
> - Updated state schema additions
> - New node names and responsibilities
> - Edge logic changes
> - Tool signatures (with docstrings — the LLM reads these)
> - HiTL interrupt points if needed
> WAIT FOR APPROVAL before implementing.

## Step 3 — Implement in parallel
// parallel

### State & Tools Agent
Role: LangGraph Specialist
Task: Implement:
- State schema updates
- New tool functions with clear docstrings
- Tool factories for DB-injected tools
Use the `langgraph-fundamentals` skill.
// capture: TOOLS_DONE

### Graph & Nodes Agent
Role: LangGraph Specialist
Task: Implement:
- New node functions
- Updated graph edges and conditional routing
- interrupt() + Command(resume=...) for HiTL nodes
- Streaming support where applicable
Use the `langgraph-human-in-the-loop` skill.
// capture: GRAPH_DONE

### Neo4j Write Agent
Role: Neo4j Specialist
Task: Implement Cypher queries for any new graph writes:
- MERGE patterns for idempotency
- UNWIND for batch writes
- Verify against live schema via MCP
Use the `neo4j-cypher` skill.
// capture: NEO4J_DONE

## Step 4 — Integration check
// turbo
cd backend && LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v -k "agent"
// retry: 2
// capture: TEST_RESULT

## Step 5 — Push via github-push workflow
// if TEST_RESULT is all green
// run workflow: github-push
