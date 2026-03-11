# Concept Linker Agent — Implementation Plan

## Goal

Add a **Concept Linker** agent (4th agent in the Market Demand Analyst swarm) that, after the teacher approves skills for insertion, extracts relevant concepts for each skill and writes everything to Neo4j as `MARKET_SKILL` nodes with `REQUIRES_CONCEPT` relationships.

---

## Context

### Current Pipeline (3 agents)
1. **Job Analyst** — fetches jobs, teacher selects groups
2. **Skill Extractor** — LLM-extracts skills from job descriptions, deduplicates
3. **Curriculum Mapper** — maps skills to chapters, teacher approves final list

After step 3, `tool_store["selected_for_insertion"]` holds teacher-approved skills (e.g. 19 skills), but **no concepts are linked** and **nothing is written to Neo4j yet**.

### What's Available in `tool_store` at Handoff

#### `selected_for_insertion` — teacher-approved skills
Each item: `{name, category, target_chapter, rationale}`

#### `curriculum_mapping` — full mapping analysis
Each item: `{name, category, status ("covered"|"gap"|"new_topic_needed"), target_chapter, related_concepts: [str], priority ("high"|"medium"|"low"), reasoning}`

#### `selected_jobs` — full job postings (provenance source)
Each item:
- `title` — job title (e.g. "Big Data Engineer")
- `company` — company name (e.g. "Google")
- `description` — full job description text (up to 4000 chars, markdown)
- `url` — original job posting URL
- `site` — source platform ("indeed" | "linkedin")
- `search_term` — the query that found this job (e.g. "Big Data Engineer")

#### `extracted_skills` — all LLM-extracted skills with demand metrics
Each item: `{name, category, frequency, pct}`

### Existing Neo4j Write Patterns (in `CurriculumGraphRepository`)
- `create_skill_node(tx, skill_id, name, description)` → creates `BOOK_SKILL`
- `link_skill_to_chapter(tx, chapter_id, skill_id)`
- `link_skill_requires_concept(tx, skill_id, concept_name)`
- `merge_concept_node(tx, name, embedding, description)`
- `find_similar_concepts()` / `merge_similar_concepts()`

---

## Design Decisions (To Confirm)

- [ ] Use `MARKET_SKILL` label instead of `BOOK_SKILL` to distinguish market-sourced skills
- [ ] Store full provenance on each `MARKET_SKILL` node (see schema below)
- [ ] Link MARKET_SKILL → chapter via `RELEVANT_TO_CHAPTER` (not `HAS_SKILL` which is for book skills)
- [ ] Link MARKET_SKILL → source jobs via `SOURCED_FROM` relationship (preserving which companies demanded this skill)
- [ ] Reuse existing `CONCEPT` nodes when possible; create new ones only when no match exists
- [ ] Trigger: Concept Linker runs automatically after teacher approval (handoff from Curriculum Mapper)

---

## Architecture

### New Agent: `concept_linker`

**Role**: For each approved market skill, determine which concepts it requires by:
1. Looking at the chapter's existing concepts in Neo4j
2. Looking at relevant job description snippets
3. Using LLM to match existing concepts and propose new ones
4. Writing `MARKET_SKILL` nodes + `REQUIRES_CONCEPT` edges to Neo4j

### New Tools

#### 1. `extract_concepts_for_skills`
- **Input**: None (reads from `tool_store`)
- **Process**:
  1. Build a lookup from `extracted_skills` (for frequency/pct) and `curriculum_mapping` (for priority/status/reasoning/related_concepts)
  2. For each skill in `tool_store["selected_for_insertion"]`:
     - Enrich with frequency, pct, priority, status, reasoning from lookups
     - Get `target_chapter` from curriculum mapping
     - Query Neo4j for chapter's existing concepts via:
       `BOOK_CHAPTER-[:HAS_SECTION]->BOOK_SECTION-[:MENTIONS]->CONCEPT`
     - Gather relevant job description snippets from `tool_store["selected_jobs"]`:
       scan each job's `description` for the skill name (case-insensitive), extract a ~500-char window around each match
     - Send enriched context to LLM (see prompt below)
     - Parse JSON response
  3. Store results in `tool_store["skill_concepts"]`:
    ```python
    {
      "Apache Kafka": {
        "existing_concepts": ["stream processing", "distributed systems"],
        "new_concepts": [{"name": "event sourcing", "description": "..."}],
        "chapter_title": "Stream Processing",
        # Carried through for insert step:
        "category": "streaming",
        "frequency": 23,
        "demand_pct": 45.1,
        "priority": "high",
        "status": "gap",
        "rationale": "High demand, not covered in current syllabus",
        "reasoning": "Found in 23/51 postings, primarily data engineering roles",
        "source_job_urls": ["https://linkedin.com/...", "https://indeed.com/..."]
      }
    }
    ```
- **Output**: Summary string with per-skill counts for the agent to present as a table

#### 2. `insert_market_skills_to_neo4j`
- **Input**: None (reads from `tool_store["skill_concepts"]` + enrichment data from other stores)
- **Process**:
  - **Step A — Create JOB_POSTING nodes** (from `tool_store["selected_jobs"]`):
    - `MERGE (j:JOB_POSTING {url: $url}) SET j.title = $title, j.company = $company, j.site = $site, j.search_term = $search_term`
  - **Step B — Create MARKET_SKILL nodes** with full provenance:
    - Enrich each skill by cross-referencing `curriculum_mapping` (for priority, status, reasoning) and `extracted_skills` (for frequency, pct)
    - ```cypher
      MERGE (s:MARKET_SKILL {name: $name})
      SET s.category = $category,
          s.frequency = $frequency,
          s.demand_pct = $demand_pct,
          s.priority = $priority,
          s.status = $status,
          s.target_chapter = $target_chapter,
          s.rationale = $rationale,
          s.reasoning = $reasoning,
          s.source = 'market_demand',
          s.created_at = datetime()
      ```
  - **Step C — Link MARKET_SKILL → BOOK_CHAPTER**:
    - `MATCH (ch:BOOK_CHAPTER) WHERE ch.title = $target_chapter MERGE (s)-[:RELEVANT_TO_CHAPTER]->(ch)`
  - **Step D — Link MARKET_SKILL → JOB_POSTING** (which jobs mentioned this skill):
    - Scan `tool_store["selected_jobs"]` descriptions for skill name mentions
    - `MATCH (j:JOB_POSTING {url: $url}) MERGE (s)-[:SOURCED_FROM]->(j)`
  - **Step E — Link MARKET_SKILL → CONCEPT**:
    - For each existing concept: `MATCH (c:CONCEPT {name: $name}) MERGE (s)-[:REQUIRES_CONCEPT]->(c)`
    - For each new concept: `MERGE (c:CONCEPT {name: $name}) SET c.description = $desc` then `MERGE (s)-[:REQUIRES_CONCEPT]->(c)`
  - Store insertion summary in `tool_store["insertion_results"]`
- **Output**: Summary of what was written (X skills, Y job postings, Z concept links, W new concepts)

### New Prompt: `CONCEPT_LINKER_PROMPT`

```
You are the Concept Linker — the final agent in the Market Demand Analyst pipeline.
Your role: map approved market skills to knowledge-graph concepts, then persist everything to Neo4j.

## YOUR CONTEXT
The teacher has already approved a set of market skills for insertion into the curriculum knowledge graph.
These skills were extracted from real job postings and mapped to textbook chapters.
You now need to determine which foundational CONCEPTS each skill requires before writing to the database.

## WORKFLOW (follow exactly)
1. IMMEDIATELY call `extract_concepts_for_skills` — do NOT speak or narrate first.
2. Once results are ready, present a concise summary table to the teacher:
   | Skill | Chapter | Existing Concepts Matched | New Concepts Proposed |
   Show totals at the bottom. Flag any skill with 0 concept matches as ⚠️.
3. Ask the teacher: "Shall I proceed with writing these to the knowledge graph?"
4. On confirmation, call `insert_market_skills_to_neo4j`.
5. Report final results: how many MARKET_SKILL nodes, JOB_POSTING nodes, concept links, and new concepts were created.

## RULES
- Your FIRST action MUST be a tool call. Never greet, narrate, or explain before acting.
- Present data in tables, not walls of text.
- If a skill has zero concept matches, suggest the teacher review it — don't silently proceed.
- Do NOT modify the approved skill list. Your job is concept linking, not curation.
```

### LLM Prompt for Concept Extraction (inside `extract_concepts_for_skills`)

This is the internal prompt sent to the LLM per skill (or per batch). Uses structured output guidance.

```
You are an expert curriculum analyst. Your task is to determine which foundational
concepts a market-demanded skill requires, given the context of a university textbook chapter.

## INPUT

Skill: "{skill_name}"
Category: "{skill_category}"
Mapped to chapter: "{chapter_title}"
Teacher's rationale: "{rationale}"
Market demand: appeared in {frequency} of {total_jobs} analyzed job postings ({demand_pct}%)

## CHAPTER'S EXISTING CONCEPTS
(These are concepts already in the knowledge graph for this chapter. Use EXACT names when referencing them.)

{concept_list}

## EVIDENCE FROM JOB POSTINGS
(Excerpts from real job descriptions that mention this skill. Use these to understand
what the industry expects someone with this skill to know.)

{job_snippets}

## TASK

1. **Existing concepts**: Which of the chapter's existing concepts does this skill REQUIRE
   as prerequisites or closely depend on? Select ONLY concepts with a genuine dependency —
   not just topical similarity. Use the EXACT concept names from the list above.

2. **New concepts**: Are there foundational concepts that this skill clearly requires
   which do NOT exist in the chapter yet? Only propose a new concept if:
   - It appears across multiple job postings (not a one-off technology)
   - It represents a teachable, well-defined concept (not a product name or brand)
   - It is not already covered by an existing concept under a different name
   For each new concept, provide a concise academic description (1-2 sentences).

## OUTPUT FORMAT
Return ONLY valid JSON, no commentary:
```json
{
  "existing_concepts": ["concept_name_1", "concept_name_2"],
  "new_concepts": [
    {"name": "concept_name", "description": "One-line academic description"}
  ]
}
```

## GUIDELINES
- Prefer matching existing concepts over creating new ones (avoid duplication).
- A skill typically requires 2-6 concepts. 0 is suspicious; >8 is likely over-linking.
- New concepts should be framework-agnostic and curriculum-appropriate (e.g. "stream processing"
  not "Kafka Streams API").
```

---

## Swarm Integration

### Handoff Chain Update
```
Curriculum Mapper → (after teacher approval) → Concept Linker
```

### In `graph.py`
- Add `concept_linker` agent via `create_agent()`
- Add `transfer_to_concept_linker` handoff tool to Curriculum Mapper's toolset
- Concept Linker gets: `extract_concepts_for_skills`, `insert_market_skills_to_neo4j`, `transfer_to_job_analyst` (for final handoff back)

### Tool Lists in `tools.py`
```python
CONCEPT_LINKER_TOOLS = [extract_concepts_for_skills, insert_market_skills_to_neo4j]
```

---

## Neo4j Schema Changes

### New Node: `MARKET_SKILL`
```cypher
(:MARKET_SKILL {
  name: "Apache Kafka",                  // skill name (unique key for MERGE)
  category: "streaming",                 // skill category from extraction
  frequency: 23,                         // how many jobs mentioned this skill
  demand_pct: 45.1,                      // % of analyzed jobs requiring it
  priority: "high",                      // from curriculum mapping
  status: "gap",                         // "gap" | "new_topic_needed" (from mapping)
  target_chapter: "Stream Processing",   // chapter teacher mapped it to
  rationale: "High demand, not covered", // teacher's rationale for inclusion
  reasoning: "Found in 23/51 jobs...",   // mapper's analysis reasoning
  source: "market_demand",               // fixed label for provenance
  created_at: datetime()                 // insertion timestamp
})
```

### New Node: `JOB_POSTING` (provenance)
```cypher
(:JOB_POSTING {
  title: "Big Data Engineer",
  company: "Google",
  url: "https://linkedin.com/jobs/...",
  site: "linkedin",                      // "indeed" | "linkedin"
  search_term: "Big Data Engineer"       // query that found this job
})
```

### New Relationships
```cypher
(:MARKET_SKILL)-[:REQUIRES_CONCEPT]->(:CONCEPT)
(:MARKET_SKILL)-[:RELEVANT_TO_CHAPTER]->(:BOOK_CHAPTER)
(:MARKET_SKILL)-[:SOURCED_FROM]->(:JOB_POSTING)    // which jobs demanded this skill
```

### Why `JOB_POSTING` Nodes?
Storing jobs as nodes (not just properties) lets us:
- Query "which companies need skill X?" via `(:MARKET_SKILL)-[:SOURCED_FROM]->(:JOB_POSTING)`
- Reuse job nodes across multiple skills (many skills come from the same posting)
- Track provenance: every skill traces back to real job postings

---

## Implementation Steps

1. **Add `CONCEPT_LINKER_PROMPT`** to `prompts.py`
2. **Add `extract_concepts_for_skills` tool** to `tools.py`
   - Neo4j read: fetch chapter concepts
   - LLM call: concept extraction/matching
   - Store in `tool_store["skill_concepts"]`
3. **Add `insert_market_skills_to_neo4j` tool** to `tools.py`
   - Neo4j write: MERGE MARKET_SKILL, MERGE CONCEPT, create relationships
4. **Add `CONCEPT_LINKER_TOOLS`** export in `tools.py`
5. **Update `graph.py`**:
   - Import new prompt + tools
   - Create concept_linker agent
   - Add handoff from curriculum_mapper → concept_linker
   - Add handoff from concept_linker → job_analyst (return to coordinator)
6. **Test end-to-end** with the existing pipeline data
7. **Verify Neo4j** — query for MARKET_SKILL nodes and their REQUIRES_CONCEPT edges

---

## Open Questions

- Should the Concept Linker also compute embeddings for new concepts (for future similarity search)?
- Should we batch the LLM calls (multiple skills per call) or process one skill at a time?
  - **Recommendation**: Batch 3-5 skills per LLM call to reduce latency while keeping context windows manageable.
- Do we need a rollback mechanism if Neo4j write partially fails?
  - **Recommendation**: Use a single Neo4j transaction for all writes. If it fails, nothing is committed.
- ~~Should MARKET_SKILL nodes store the original job posting URLs as provenance?~~ → **Decided**: Yes, via `SOURCED_FROM` relationship to `JOB_POSTING` nodes.
