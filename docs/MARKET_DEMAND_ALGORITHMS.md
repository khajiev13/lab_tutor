# Market Demand Analyst — Algorithms, Formulas & Decision Criteria

> **Companion to**: `MARKET_DEMAND_ANALYST.md`
> **Scope**: Detailed algorithms, scoring formulas, deduplication logic, classification criteria, and LLM prompt engineering patterns used by the system.

---

## 1. Job Fetching & Deduplication

### 1.1 Multi-Source Scraping Strategy

```
Input:  search_terms = "term₁, term₂, ..., termₙ"
        sites = {Indeed, LinkedIn}
        results_per_site = k (default 15)

For each (termᵢ, siteⱼ):
    Scrape top-k postings from siteⱼ matching termᵢ
    Filter: hours_old ≤ 72h

Total raw results ≤ n × 2 × k
```

### 1.2 Deduplication Algorithm

Jobs are deduplicated by a **composite key** of normalized title and company:

```
dedup_key(job) = lowercase(trim(job.title)) + "|" + lowercase(trim(job.company))
```

**Filter criteria** — A job is discarded if:
- `description` is empty, `"None"`, or `len(description) < 50`
- `dedup_key` has been seen before (first occurrence wins)

### 1.3 Title Normalization & Grouping

Jobs are grouped by **normalized title** to cluster similar roles:

```
SENIORITY_PREFIXES = {
    "senior", "sr.", "junior", "jr.", "lead",
    "principal", "staff", "entry-level", "mid-level"
}

normalize(title) = title_case(
    regex_strip("^(SENIORITY_PREFIXES)\s+", title)
)
```

**Example**:
| Raw Title | Normalized |
|-----------|-----------|
| Senior Data Engineer | Data Engineer |
| sr. Data Engineer | Data Engineer |
| Staff Data Engineer | Data Engineer |
| Data Scientist | Data Scientist |

Groups are **sorted by count descending** and assigned stable 1-based indices.

---

## 2. Parallel Skill Extraction

### 2.1 Batching Strategy

```
Input:  selected_jobs = [job₁, job₂, ..., jobₘ]
        batch_size = 5
        max_workers = min(⌈m / batch_size⌉, 5)

Batches:
    B₁ = [job₁ ... job₅]
    B₂ = [job₆ ... job₁₀]
    ...
    Bₖ = [job₅(ₖ₋₁)+₁ ... jobₘ]    where k = ⌈m / 5⌉
```

Each batch is processed **concurrently** via `ThreadPoolExecutor`.

### 2.2 Per-Batch LLM Extraction

For each batch $B_i$:

1. **Truncate** each job description to 3,000 characters
2. **Format** prompt with all batch descriptions
3. **LLM call** with `temperature=0` → JSON array of `{name, category}`
4. **Parse** response, strip markdown fences if present, fallback to `[]` on error

### 2.3 Cross-Batch Aggregation (Fan-In)

```
For each batch Bᵢ result:
    For each skill s in Bᵢ:
        canonical = lowercase(s.name)
        if canonical not seen in this batch:
            skill_counter[canonical] += 1    # counts batches, not mentions
            skill_categories[canonical] ← s.category  (first-write wins)
            name_map[canonical] ← s.name               (preserve first casing)
```

### 2.4 Frequency & Demand Percentage

For each unique skill $s$:

$$
\text{frequency}(s) = \text{number of batches where } s \text{ appeared}
$$

$$
\text{demand\_pct}(s) = \frac{\text{frequency}(s)}{m} \times 100
$$

where $m$ = total number of selected jobs.

> **Note**: Frequency counts **batches** (groups of 5 jobs), not individual job mentions. A skill appearing in all 5 jobs within a single batch counts as 1. This slightly underestimates true frequency but avoids over-weighting large batches.

### 2.5 Synonym Canonicalization

The LLM prompt instructs canonical name merging:

| Raw Input | Canonical Output |
|-----------|-----------------|
| k8s | Kubernetes |
| Postgres | PostgreSQL |
| AWS | Amazon Web Services |
| JS | JavaScript |

This is **soft canonicalization** (LLM-driven, not rule-based). The `lowercase()` dedup catches remaining case variants.

---

## 3. Curriculum Coverage Analysis

### 3.1 Skill Coverage Classification

For each extracted market skill $s$, the system queries Neo4j for matches:

```cypher
-- Exact BOOK_SKILL match
MATCH (sk:BOOK_SKILL) WHERE toLower(sk.name) CONTAINS toLower($skill_name)

-- Exact CONCEPT match
MATCH (c:CONCEPT) WHERE toLower(c.name) = toLower($skill_name)

-- Related CONCEPT match (partial)
MATCH (c:CONCEPT) WHERE toLower(c.name) CONTAINS toLower($skill_name)
  AND toLower(c.name) <> toLower($skill_name)
```

### 3.2 Classification Criteria

| Status | Symbol | Criteria |
|--------|--------|----------|
| **Covered** | ✓ | Exact match in BOOK_SKILL **or** exact match in CONCEPT |
| **Partial** | ~ | No exact match, but related CONCEPT names contain the skill name |
| **New** | ✗ | No match of any kind in the knowledge graph |

### 3.3 Curriculum Mapping Decision Matrix

The Curriculum Mapper produces a mapping for each skill:

| Input Factor | Used For |
|-------------|----------|
| Skill name + category | Semantic matching to chapter topics |
| Frequency / demand_pct | Priority assignment |
| Chapter section concepts | Determining best-fit chapter |
| Existing BOOK_SKILL nodes | Detecting covered skills |

**Output per skill**:

```json
{
    "name": "skill name",
    "category": "category",
    "status": "covered | gap | new_topic_needed",
    "target_chapter": "Chapter N: Title",
    "related_concepts": ["concept1", "concept2"],
    "priority": "high | medium | low",
    "reasoning": "Why this mapping was chosen"
}
```

### 3.4 Priority Assignment Criteria

Based on market demand frequency:

$$
\text{priority}(s) = \begin{cases}
\textbf{high} & \text{if demand\_pct}(s) \geq 40\% \\
\textbf{medium} & \text{if } 15\% \leq \text{demand\_pct}(s) < 40\% \\
\textbf{low} & \text{if demand\_pct}(s) < 15\%
\end{cases}
$$

> These thresholds are **soft guidelines** in the LLM prompt, not hard-coded. The Curriculum Mapper agent applies judgment based on the overall skill distribution.

### 3.5 Chapter Fitness Heuristic

The mapper determines target chapters through **hierarchical exploration**:

```
1. list_chapters()
   → Overview: chapter titles, section counts, existing skill counts

2. Semantic pre-filter: select chapters whose titles are topically
   related to the market skill (LLM reasoning)

3. get_chapter_details(selected_chapters)
   → Sections with concept counts, existing BOOK_SKILL nodes

4. get_section_concepts(relevant_sections)
   → Concept-level detail for fine-grained matching

5. Decision: skill S → chapter C if:
   a. C already has related BOOK_SKILLs in the same domain
   b. C's sections cover prerequisite concepts for S
   c. S fits the pedagogical scope of C (level-appropriate)
   d. If no chapter fits → status = "new_topic_needed"
```

---

## 4. Concept Extraction & Linking

### 4.1 Per-Skill Concept Analysis

For each teacher-approved skill $s$:

```
Input:
    skill_name, category, target_chapter, rationale
    chapter_concepts  ← Neo4j query (all concepts in target chapter)
    job_snippets      ← text window extraction from job descriptions

Output:
    existing_concepts: [names of chapter concepts this skill requires]
    new_concepts:      [{name, description}]  (to be created)
```

### 4.2 Job Snippet Extraction

For evidence gathering, the system finds relevant excerpts:

```python
For each job in selected_jobs:
    Match skill_name (case-insensitive) in job.description
    If found at position p:
        snippet = description[p - 250 : p + 250]  # 500-char window
    Stop after 5 snippets
```

### 4.3 Concept Selection Criteria

The LLM is instructed to follow these rules:

| Rule | Description |
|------|-------------|
| **Prefer existing** | Match existing chapter concepts before proposing new ones |
| **Genuine dependency** | Only link concepts the skill truly requires, not topically similar |
| **Cardinality bounds** | 2–6 concepts per skill (0 is suspicious; >8 is over-linking) |
| **Cross-posting validation** | New concepts must appear across multiple job postings |
| **Teachability** | New concepts must be well-defined and teachable (not product names) |
| **Framework-agnostic** | Prefer "stream processing" over "Kafka Streams API" |

### 4.4 Concept Extraction Quality Formula

For validating concept extraction quality across all skills:

$$
\text{coverage\_ratio} = \frac{\sum_s |\text{existing\_concepts}(s)|}{\sum_s (|\text{existing\_concepts}(s)| + |\text{new\_concepts}(s)|)}
$$

- **Ideal range**: $0.5 \leq \text{coverage\_ratio} \leq 0.85$
- **Too high** ($> 0.85$): May indicate the skill isn't truly new
- **Too low** ($< 0.5$): Chapter may not be the right fit

---

## 5. Neo4j Write Strategy

### 5.1 Write Order (Atomic per session)

```
Step A: MERGE JOB_POSTING nodes (by url)
   → Idempotent: won't duplicate on re-run

Step B: MERGE MARKET_SKILL nodes (by name)
   → SET all provenance properties
   → Idempotent: updates properties on re-run

Step C: MERGE (BOOK_CHAPTER)-[:HAS_SKILL]->(MARKET_SKILL)
   → Links skill to its target chapter

Step D: MERGE (MARKET_SKILL)-[:SOURCED_FROM]->(JOB_POSTING)
   → Links each skill to jobs that evidenced it

Step E: MERGE (MARKET_SKILL)-[:REQUIRES_CONCEPT]->(CONCEPT)
   → For existing concepts: just create relationship
   → For new concepts: MERGE node + SET description + create relationship
```

### 5.2 Idempotency Guarantees

All writes use `MERGE` (not `CREATE`), ensuring:
- **Re-running** the pipeline for the same skill updates properties, doesn't duplicate
- **Partial failure** is safe: re-run will fill in missing relationships
- **MARKET_SKILL** nodes are distinguishable from **BOOK_SKILL** nodes by label

### 5.3 Cleanup Algorithm

The `delete_market_skills` tool performs cascading cleanup:

```
1. DETACH DELETE matching MARKET_SKILL nodes
   (removes all attached relationships)

2. Find orphaned JOB_POSTING nodes:
   MATCH (j:JOB_POSTING)
   WHERE NOT EXISTS { (j)<-[:SOURCED_FROM]-() }
   DETACH DELETE j

Orphan cleanup ensures JOB_POSTINGs don't accumulate
across multiple analysis sessions.
```

---

## 6. Human-in-the-Loop Decision Points

The system has **4 mandatory teacher checkpoints**:

| Checkpoint | Phase | Teacher Action | Blocks |
|-----------|-------|----------------|--------|
| **CP1**: Group Selection | Phase 1 | Choose which job groups to analyze | Skill Extraction |
| **CP2**: Extraction Start | Phase 1 | Confirm selected groups before extraction | Handoff to Extractor |
| **CP3**: Skill Approval | Phase 4 | Review, edit, remove skills from gap list | Concept Linking |
| **CP4**: Insertion Approval | Phase 4 | Final approval before Neo4j write | Neo4j Insert |

```
          CP1         CP2              CP3              CP4
    ──────┼───────────┼────────────────┼────────────────┼──────▶
    fetch  select    handoff   extract+map    approve   insert
    jobs   groups    →extractor  (auto)       skills    →neo4j
```

---

## 7. Error Handling & Resilience

### 7.1 Neo4j Connection Strategy

```
_neo4j_driver_cache ── global cached driver
    ↓
max_connection_lifetime = 5 min  (rotate before Aura idles)
    ↓
On SessionExpired:
    1. Clear cache (force_new=True)
    2. Re-raise exception (caller retries)
    3. Next call creates fresh driver
```

### 7.2 LLM Extraction Fault Tolerance

```
For batch Bᵢ failure:
    1. Record error: "Batch i: ErrorType: message"
    2. Continue with remaining batches
    3. Report failure count in final summary

The pipeline does NOT stop on partial batch failure.
Results degrade gracefully (fewer extracted skills).
```

### 7.3 JSON Parsing Resilience

```
LLM response → strip markdown fences (```json ... ```)
             → json.loads()
             → validate is list
             → fallback: return []
```

---

## 8. Complexity Analysis

### 8.1 Time Complexity

| Operation | Complexity | Bottleneck |
|-----------|-----------|------------|
| Job fetching | $O(n \times 2)$ network calls | HTTP scraping latency |
| Deduplication | $O(j)$ where $j$ = total raw jobs | Hash set lookup |
| Title grouping | $O(j)$ | Regex + dict insert |
| Skill extraction | $O(\lceil j/5 \rceil)$ LLM calls, **parallelized** | LLM API latency |
| Coverage check | $O(s)$ Neo4j queries where $s$ = unique skills | Graph query latency |
| Concept extraction | $O(s')$ LLM calls (sequential) | s' = approved skill count |
| Neo4j write | $O(s' + p + c)$ Cypher statements | p = job postings, c = concepts |

### 8.2 Space Complexity

| Store | Upper Bound |
|-------|------------|
| `fetched_jobs` | ~$n \times k \times 2$ job objects (~4KB each) |
| `extracted_skills` | ~$s$ skill objects (~100B each) |
| `skill_concepts` | ~$s' \times (c_e + c_n)$ concept mappings |
| LLM context window | Bounded by prompt design (descriptions truncated to 3KB) |

---

## 9. LLM Prompt Design Patterns

### 9.1 Agent Prompt Structure

All agent prompts follow the same template:

```
# Role
[Identity and expertise description]

# Context / Current State
[Injected runtime data — curriculum context, etc.]

# Your Tools
[Numbered tool list with descriptions]

# Workflow / Process
[Step-by-step instructions in numbered order]

# Rules
[Behavioral constraints and guardrails]
```

### 9.2 Extraction Prompts

| Prompt | Input | Output Format | Temperature |
|--------|-------|--------------|-------------|
| `_BATCH_EXTRACTION_PROMPT` | 5 job descriptions (3KB each) | `[{name, category}]` | 0 |
| `_CONCEPT_EXTRACTION_PROMPT` | Skill + chapter concepts + job snippets | `{existing_concepts, new_concepts}` | 0 |

### 9.3 Prompt Injection Prevention

- Job descriptions are **never shown to the teacher** in the conversation
- Descriptions are **truncated to 3,000–4,000 characters**
- LLM extraction runs in **separate, non-conversational calls** (not part of the agent loop)
- System prompts use **structured output constraints** ("Return ONLY valid JSON")

---

## 10. Evaluation Metrics

For assessing system effectiveness post-deployment:

### 10.1 Skill Discovery Quality

$$
\text{precision}_{skills} = \frac{|\text{teacher approved skills}|}{|\text{total extracted skills}|}
$$

$$
\text{signal-to-noise} = \frac{|\text{gap skills (useful)}|}{|\text{covered skills (redundant)}| + |\text{irrelevant skills (removed)}|}
$$

### 10.2 Concept Linking Accuracy

$$
\text{existing\_concept\_accuracy} = \frac{|\text{correctly linked existing concepts}|}{|\text{total linked existing concepts}|}
$$

$$
\text{new\_concept\_necessity} = \frac{|\text{new concepts teacher kept}|}{|\text{total new concepts proposed}|}
$$

### 10.3 Curriculum Coverage Delta

$$
\Delta\text{coverage} = \frac{|\text{skills}_{after}| - |\text{skills}_{before}|}{|\text{market skills}_{total}|} \times 100\%
$$

Measures the improvement in market-relevant skill coverage after running the pipeline.
