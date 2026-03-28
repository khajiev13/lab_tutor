# Lab Tutor — Agent System Reference

> **A Knowledge Graph-Centric Multi-Agent Platform for Intelligent Curriculum Resource Construction**

## System Overview

The platform operates in two stages:

**Stage 1 — Knowledge Graph Construction**: Instructors upload course materials (PDFs, DOCX, slides). The platform extracts concepts, definitions, and evidence, generates semantic embeddings, and writes everything into a Neo4j course knowledge graph — turning passive files into structured, queryable knowledge.

**Stage 2 — Agent-Driven Curriculum Enrichment**: Four interconnected AI agents enrich and refine the graph in a connected pipeline.

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Resource Application Layer                    │
│  Personalized Recommendations │ Curriculum Improvement  │
│  Intelligent Teaching Assistance                        │
└─────────────────────────────────────────────────────────┘
                         ↑
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Knowledge Alignment Layer                     │
│  Textbook-Curriculum │ Market-Curriculum │ Resource-Skill│
└─────────────────────────────────────────────────────────┘
                         ↑
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Knowledge Foundation Layer                    │
│  Course Knowledge Graph │ Concept Normalization │ Vectors│
└─────────────────────────────────────────────────────────┘
```

---

## Stage 1 — Document Extraction & Embeddings

**Not an agent — a prerequisite service.** Runs before any agent is invoked.

### Document Extraction Service

| | |
|---|---|
| **Input** | PDF / DOCX / TXT uploaded by instructor |
| **Output** | `TEACHER_UPLOADED_DOCUMENT → MENTIONS → CONCEPT` in Neo4j |
| **Status tracking** | SQL: `PENDING → PROCESSED → FAILED` |

Downloads files from cloud storage, parses them, then uses LLM structured output (Pydantic-constrained) to extract:
- Document topic and summary
- Named concepts with canonical name, definition, and verbatim textual evidence

Every extraction requires textual evidence from the source — claims without grounding are rejected. This is the first layer of hallucination suppression.

### Embeddings Service

| | |
|---|---|
| **Model** | OpenAI text-embedding (2048-dimensional) |
| **Change detection** | SHA-256 hash of content + model name — skips recomputation if unchanged |
| **Parallelism** | Thread pool for concurrent embedding calls |
| **Output** | Vector stored on `CONCEPT` and `DOCUMENT` nodes in Neo4j |

Enables vector similarity search and retrieval-augmented generation across the entire knowledge base.

---

## Agent 1 — Curricular Alignment Architect (CAA)

**Problem**: How can instructors efficiently identify which textbooks best support the course, and understand how each chapter maps to learning objectives?

**Module**: `backend/app/modules/curricular_alignment_architect/`

**Framework**: LangGraph multi-phase workflow

### Pipeline

```
Course context
     │
     ▼
1. Discovery ──── Google Books API + Tavily API (parallel, 10-12 queries)
     │             Fuzzy deduplication by title
     ▼
2. Multi-Criteria Scoring ── ReAct reasoning loop (≤5 iterations/book)
     │                        7-dimension weighted scoring:
     │                        • Topic Alignment      30%
     │                        • Pedagogical Structure 20%
     │                        • Scope Coverage       15%
     │                        • Publisher Reputation  15%
     │                        • Author Credentials   10%
     │                        • Currency             10%
     │                        • Practical Value
     ▼
3. [INSTRUCTOR REVIEW] ── Ranked candidates presented
     │                     Instructor selects ≤5 books to adopt
     ▼
4. Download & Storage ── Search for accessible PDF, download, store in Azure Blob
     ▼
5. Chapter-Level Analysis ── Parallel chapter processing
     │                        Extracts: concepts, skills, relationships
     ▼
Neo4j: BOOK → CHAPTER → SECTION → CONCEPT / SKILL
```

**Human-in-the-loop checkpoints**: 3 (book selection, download confirmation, extraction review)

**Key outputs**:
- Instructor-approved textbook library in cloud storage
- Chapter-skill mappings in the knowledge graph
- Initial **skill vocabulary** for the downstream agents

---

## Agent 2 — Market Demand Analyst (MDA)

**Problem**: How can a university course remain aligned with real industry expectations instead of becoming isolated from the evolving job market?

**Module**: `backend/app/modules/marketdemandanalyst/`

**Framework**: LangGraph 3-agent swarm (Supervisor + Curriculum Mapper + Concept Linker)

### Pipeline

```
Job search terms
     │
     ▼
1. Job Discovery (Supervisor Agent)
     │  └─ Indeed, LinkedIn parallel scraping
     │  └─ Deduplication by normalized title + company
     │  └─ Group by role type
     ▼
[INSTRUCTOR REVIEW] ── Selects relevant job categories
     │
     ▼
2. Skill Extraction
     │  └─ Parallel batches: 5 jobs/batch, 5 concurrent workers
     │  └─ LLM extracts skills with synonym canonicalization
     │     ("k8s" → "Kubernetes", "ML" → "Machine Learning")
     │  └─ Demand frequency scoring
     │  └─ Priority classification:
     │     • High:   ≥40% of postings
     │     • Medium: 15-40%
     │     • Low:    <15%
     ▼
[INSTRUCTOR REVIEW] ── Confirms skill extraction results
     │
     ▼
3. Curriculum Mapping (Curriculum Mapper Agent)
     │  └─ Compares every market skill vs. course knowledge graph
     │  └─ Coverage status per skill:
     │     • Covered         — already taught
     │     • Partially Covered — gaps exist
     │     • Entirely Missing  — not in curriculum
     ▼
4. Concept Linking (Concept Linker Agent)
     │  └─ Determines underlying concepts each skill requires (2-6 per skill)
     │  └─ Writes: MARKET_SKILL → REQUIRES_CONCEPT
     ▼
[INSTRUCTOR REVIEW] ── Approves before persistence
     │
     ▼
Neo4j: MARKET_SKILL nodes + coverage relationships + concept links
```

**Human-in-the-loop checkpoints**: 4

**Key outputs**:
- Evidence-based curriculum-market gap analysis
- Market skills enriching the knowledge graph with coverage status
- Priority-ranked skill demand data for curriculum reform decisions

---

## Agent 3 — Textual Resource Analyst (TRA)

**Problem**: Once the platform knows which skills exist in the curriculum and which the market demands, how do we find the best written materials to teach each skill?

**Status**: Architecture designed; implementation in progress.

### Pipeline

```
All identified skills (from CAA + MDA)
     │
     ▼
1. Skill Profile Construction
     └─ Skill name + synonyms
     └─ Related concepts (from knowledge graph)
     └─ Course level (introductory / intermediate / advanced)
     └─ Chapter context (from textbook analysis)
     │
     ▼
2. Contextualized Search
     └─ Generate diverse queries per skill across resource types:
        tutorials, documentation, articles
     └─ Search: Tavily, DuckDuckGo, Serper (parallel)
     └─ Deduplicate by URL normalization
     └─ Semantic similarity filtering
     │
     ▼
3. Quality Evaluation (5-dimension scoring)
     └─ Recency           — publication/update date
     └─ Relevance         — vector similarity to skill profile
     └─ Pedagogical Quality — clarity + structural completeness
     └─ Depth             — coverage thoroughness
     └─ Source Authority  — platform reputation, author credibility
     │
     ▼
4. Selection: top 3-5 resources per skill, varied by type
     │
     ▼
[INSTRUCTOR REVIEW] ── Optional approval before save
     │
     ▼
Neo4j: RESOURCE → TEACHES → SKILL → REQUIRES_CONCEPT
```

**Key outputs**: Curated, ranked library of online learning materials linked to every skill — connecting "what to learn" with "where to learn it."

---

## Agent 4 — Video Agent

**Problem**: Written materials alone are not always the most effective way to learn a technical skill. How can the platform automatically find the best video content for every curriculum skill?

**Status**: Architecture designed; implementation in progress.

### Pipeline

```
All identified skills (from CAA + MDA)
     │
     ▼
1. Contextualized Query Generation
     └─ Skill profile (same as TRA)
     └─ Queries targeted at video content with recency filters
     │
     ▼
2. Multi-Platform Search (parallel)
     └─ YouTube
     └─ Online course providers (Coursera, edX, etc.)
     └─ Deduplicate by URL normalization
     │
     ▼
3. Quality Evaluation (5-dimension scoring)
     └─ Recency           — upload/update date
     └─ Relevance         — semantic match to skill
     └─ Pedagogical Quality — explanation clarity, structure
     └─ Depth             — topic thoroughness
     └─ Source Authority  — official channel vs. personal upload
     │
     ▼
4. Selection: top 3-5 videos per skill
     └─ Variety: short tutorial, full lecture, live coding walkthrough
     │
     ▼
[INSTRUCTOR REVIEW] ── Approval before persistence
     │
     ▼
Neo4j: VIDEO → TEACHES → SKILL + CONCEPT links
```

**Key outputs**: Curated, ranked library of educational videos linked to every skill — giving students multiple learning pathways for each topic.

---

## End-to-End Pipeline

```
Instructor uploads course materials
         │
         ▼
Document Extraction + Embeddings
(unstructured files → structured knowledge graph)
         │
         ▼
Curricular Alignment Architect
(builds the skill vocabulary from approved textbooks)
         │
         ▼
Market Demand Analyst
(aligns curriculum skills with industry reality)
         │
         ▼
Textual Resource Analyst + Video Agent (parallel)
(finds the best way to teach each skill)
         │
         ▼
Enriched Knowledge Graph
(ready for: personalized recommendations, gap analysis,
 intelligent Q&A, learning path generation)
```

---

## Summary Table

| Agent | Input | Output | Key Technique | HiTL Checkpoints |
|---|---|---|---|---|
| Document Extraction | PDF/DOCX/TXT | Concepts + vectors in graph | LLM structured output, SHA-256 caching | None |
| Curricular Alignment Architect | Course objectives | Textbook chapters + skills | ReAct scoring loop, parallel web search, fuzzy match | 3 |
| Market Demand Analyst | Job search terms | Market skills aligned to curriculum | 3-agent swarm, parallel extraction, coverage mapping | 4 |
| Textual Resource Analyst | Identified skills | Curated ranked text resources | Contextualized search, 5-dimension scoring | 1 (optional) |
| Video Agent | Identified skills | Curated ranked video resources | Multi-platform search, 5-dimension scoring | 1 (optional) |

## Design Principles

**Hallucination suppression**: All extractions require verbatim textual evidence. Dual-validation checks both internal consistency (evidence in source) and external consistency (alignment with course scope).

**Human-in-the-loop at critical nodes**: The system never persists AI-generated content to the knowledge graph without instructor confirmation at key checkpoints. Automation handles discovery and scoring; humans make the final call.

**Graph as single source of truth**: Every agent writes results back to Neo4j. The knowledge graph is the integration point — not a separate database per agent, but one shared semantic model that accumulates and connects all findings.

**Parallelism throughout**: Web searches, chapter analyses, job scraping, skill extractions, and resource searches all run concurrently to minimize wall-clock time.
