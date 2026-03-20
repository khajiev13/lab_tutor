Implementation plan for the Skill Finder + Skill Cleaner agents and :SKILL label unification.

Read the full plan: .github/prompts/plan-skillCuratorAgent.prompt.md

## Summary
1. Replace current Supervisor-driven fetch/extract flow with a new Skill Finder swarm agent
2. Supervisor becomes lightweight orchestrator
3. Add shared :SKILL label to both BOOK_SKILL and MARKET_SKILL
4. New Skill Cleaner agent runs after Mapper — compares market vs book skills per chapter, drops redundant ones
5. Concept Linker only processes final cleaned skills

## Pipeline Flow
```
Supervisor (search terms)
  → Skill Finder (fetch → groups → extract → merge → teacher picks)
  → Mapper (map curated skills to chapters)
  → Skill Cleaner (compare per-chapter vs existing book skills)
  → Concept Linker (extract concepts for final clean skills)
  → Supervisor (write to DB after teacher confirmation)
```

## Phases
1. Skill Finder Agent (move tools from Supervisor, add new tools)
2. Skill Merging (extractor subgraph — LLM merge node)
3. Skill Cleaner Agent (compare_and_clean per chapter)
4. Neo4j Schema — add :SKILL label
5. Swarm Assembly & Testing

$ARGUMENTS
