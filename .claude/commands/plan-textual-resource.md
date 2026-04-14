Implementation plan for the Textual Resource Analyst notebook prototype.

Read the full plan: .github/prompts/plan-textualResourceAnalyst.prompt.md

## Summary
Build a prototype notebook that finds the best online reading materials for each course skill (BOOK_SKILL + MARKET_SKILL) using a 3-stage hybrid pipeline: query generation → multi-source search → embedding filter + LLM rubric.

## Algorithm
1. Context + Query Generation — LLM generates 4-6 diverse queries per skill
2. Multi-Source Search + Embedding Filter — Tavily + DDG + Serper in parallel, deduplicate, embed, keep top-15 by cosine similarity
3. LLM Evaluation + Ranking — 5-criterion rubric (Recency 0.25, Relevance 0.25, Pedagogy 0.20, Depth 0.15, Source Quality 0.15), select top 3-5 per skill

## Neo4j Schema
- New node: READING (url, title, scores, resource_type, published_date)
- New rels: (SKILL)-[:HAS_READING]->(READING), (READING)-[:COVERS_CONCEPT]->(CONCEPT)

$ARGUMENTS
