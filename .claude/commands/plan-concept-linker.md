Implementation plan for the Concept Linker Agent (4th agent in Market Demand Analyst swarm).

Read the full plan: .github/prompts/plan-conceptLinker.prompt.md

## Summary
Add a Concept Linker agent that, after teacher approves skills for insertion, extracts relevant concepts for each skill and writes everything to Neo4j as MARKET_SKILL nodes with REQUIRES_CONCEPT relationships.

## New Tools
1. `extract_concepts_for_skills` — reads tool_store, queries Neo4j for chapter concepts, LLM matches existing + proposes new concepts
2. `insert_market_skills_to_neo4j` — creates JOB_POSTING nodes, MARKET_SKILL nodes, links to chapters/jobs/concepts

## Neo4j Schema
- MARKET_SKILL node (name, category, frequency, demand_pct, priority, status, target_chapter, rationale, source)
- JOB_POSTING node (title, company, url, site, search_term)
- Relationships: REQUIRES_CONCEPT, RELEVANT_TO_CHAPTER, SOURCED_FROM

## Swarm Integration
Curriculum Mapper → (after teacher approval) → Concept Linker
Add to graph.py: create agent, add handoff tools

$ARGUMENTS
