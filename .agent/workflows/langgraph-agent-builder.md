---
description: Build or modify one of the four Lab Tutor AI agents (Curricular Alignment Architect, Market Demand Analyst, Textual Resource Analyst, Video Agent). Use for new LangGraph nodes, tools, state schema changes, HiTL interrupts, or LangSmith tracing setup.
---

# LangGraph Agent Builder Workflow

## Step 1 — Load agent context in parallel
// parallel

### Codebase Reader
Task: Read the target agent's module directory. Summarize:
- Current StateGraph structure (nodes, edges, entry/exit points)
- State schema (TypedDict fields)
- Existing tool signatures and docstrings
- HiTL interrupt points (interrupt() calls)
- LangSmith project name
// capture: AGENT_CONTEXT

### Graph Schema Reader
Task: Use mcp__neo4j-database__get_neo4j_schema to get current schema.
Identify which nodes/relationships this agent reads from or writes to.
// capture: GRAPH_CONTEXT

### LangSmith Reader
Task: Use mcp__langsmith__list_projects to find the Lab Tutor project.
Use mcp__langsmith__fetch_runs to get the last 5 runs of this agent and summarize any errors or patterns.
// capture: LANGSMITH_CONTEXT

## Step 2 — Skill load
Load these skills before implementing:
- `langgraph-fundamentals` — StateGraph, nodes, edges, Send, streaming
- `langgraph-human-in-the-loop` — interrupt(), Command(resume=...), approval flows
- `langgraph-persistence` — checkpointers, thread_id, memory Store

## Step 3 — Design (Planning mode)
> Using $AGENT_CONTEXT, $GRAPH_CONTEXT, $LANGSMITH_CONTEXT, outline:
> - State schema additions/changes
> - New nodes and their responsibilities
> - Edge logic and conditional routing
> - Tool signatures (docstrings are the LLM's instructions — make them precise)
> - HiTL interrupt points
> - Neo4j writes needed
> WAIT FOR APPROVAL before implementing.

## Step 4 — Implement in parallel
// parallel

### Tools & State Agent
Role: LangGraph Specialist
Task: Implement state schema updates and new tool functions.
- Clear docstrings on every tool
- Tool factories for DB-injected dependencies
- Pydantic validation on tool outputs before storing to state
// capture: TOOLS_DONE

### Graph & Nodes Agent
Role: LangGraph Specialist
Task: Implement new nodes and updated graph structure.
- interrupt() + Command(resume=...) for HiTL
- Streaming support
- Error handling: retry transient, surface unrecoverable to HiTL
// capture: GRAPH_DONE

### Neo4j Agent
// if graph writes are needed
Task: Write Cypher for all new graph writes.
// run workflow: neo4j-cypher
// capture: NEO4J_DONE

## Step 5 — Verify
// turbo
cd backend && LAB_TUTOR_DATABASE_URL="postgresql://khajievroma@localhost:5432/lab_tutor_test" uv run pytest -v -k "agent"
// retry: 2
// capture: TEST_RESULT

## Step 6 — Ship
// if TEST_RESULT is green
// run workflow: github-push
