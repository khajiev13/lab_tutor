# Lab Tutor Agent Logic (Current Codebase)

This document consolidates the current implementation logic across the Lab Tutor codebase, based on direct code inspection and focused sub-agent exploration.

It is intended as a clean, paper-friendly reference for:

- what each agent or pipeline currently does
- how the agents work together
- where the two skill banks come from
- how readings and videos are actually generated today
- which parts are teacher-facing versus student-facing

This reflects the current repository state, not older proposal text or outdated README summaries.

---

## 1. High-Level System Story

Lab Tutor is a graph-centered curriculum intelligence platform.

At a high level, the implemented flow is:

1. Teachers upload course documents.
2. The system extracts document concepts and creates a transcript-grounded course graph.
3. Teachers build a course chapter structure from those extracted documents.
4. The Curricular Alignment Architect discovers and analyzes textbooks, then extracts `BOOK_SKILL` nodes from selected books.
5. The Market Demand Analyst discovers job-market skills, compares them to the curriculum, removes redundant ones, and inserts `MARKET_SKILL` nodes.
6. These two outputs become the two central skill banks:
   - `Book Skill Bank`
   - `Market Skill Bank`
7. Later, students select skills from those banks.
8. The Student Learning Path pipeline generates:
   - readings
   - videos
   - questions

Important implementation detail:

- Readings and videos are **not** generated during teacher-side bank creation.
- They are generated later by the student-side learning-path workflow.

---

## 2. Core Graph and Storage Model

The system uses three main storage layers.

### 2.1 Neo4j

Neo4j is the knowledge-graph projection and the main semantic structure used by downstream agents.

Important node families include:

- `CLASS`
- `COURSE_CHAPTER`
- `TEACHER_UPLOADED_DOCUMENT`
- `CONCEPT`
- `BOOK`
- `BOOK_CHAPTER`
- `BOOK_SECTION`
- `BOOK_SKILL`
- `MARKET_SKILL`
- `JOB_POSTING`
- `READING_RESOURCE`
- `VIDEO_RESOURCE`

Important relationship families include:

- `HAS_COURSE_CHAPTER`
- `INCLUDES_DOCUMENT`
- `MENTIONS`
- `CANDIDATE_BOOK`
- `HAS_CHAPTER`
- `HAS_SECTION`
- `HAS_SKILL`
- `MAPPED_TO`
- `REQUIRES_CONCEPT`
- `SOURCED_FROM`
- `HAS_READING`
- `HAS_VIDEO`

### 2.2 PostgreSQL

PostgreSQL stores operational state and workflow metadata.

Key examples:

- book selection sessions
- discovered/scored books
- selected books
- extraction runs
- chapter analysis rows
- skill JSON payloads
- Market Demand Analyst thread snapshots
- LangGraph checkpoints

### 2.3 Azure Blob Storage

Azure Blob stores uploaded or downloaded book PDFs and uploaded course files.

---

## 3. Stage A: Document Extraction and Course Graph Construction

This stage turns raw teacher documents into structured curriculum context.

### 3.1 Document Extraction Service

The document extraction service processes teacher-uploaded course files, currently focusing on text-like content such as TXT and DOCX in the production flow.

Its responsibilities are:

1. download the uploaded file from blob storage
2. parse the file content
3. run structured LLM extraction
4. extract:
   - topic
   - summary
   - keywords
   - concepts
5. write graph data into Neo4j as:
   - `TEACHER_UPLOADED_DOCUMENT`
   - `DOCUMENT -> MENTIONS -> CONCEPT`

Each concept carries semantic provenance such as extracted name, evidence, and definition.

### 3.2 Embeddings

After extraction, embeddings are generated for document content and concept mentions.

This creates the semantic retrieval substrate used by downstream logic.

### 3.3 Output of This Stage

This stage creates the transcript-grounded curriculum memory used later by:

- the chapter planner
- the Market Demand Analyst
- student learning-path generation

---

## 4. Stage B: Teacher Curriculum Planner

Before book and market skills are attached to the curriculum, teachers build a course chapter scaffold.

### 4.1 What It Does

The planner:

1. loads extracted teacher documents from Neo4j
2. uses an LLM to propose a course chapter plan
3. lets the teacher manually refine the assignment of documents to chapters
4. writes:
   - `CLASS -> HAS_COURSE_CHAPTER -> COURSE_CHAPTER`
   - `COURSE_CHAPTER -> INCLUDES_DOCUMENT -> TEACHER_UPLOADED_DOCUMENT`

### 4.2 Why It Matters

This planner is foundational because:

- `COURSE_CHAPTER` nodes are the target structure for later skill alignment
- both book skills and market skills are mapped into this teacher-owned chapter scaffold

Important conceptual rule:

- chapters come from teacher documents
- books and market analysis add skills to that structure

---

## 5. Stage C: Curricular Alignment Architect

The Curricular Alignment Architect is the textbook-focused enrichment pipeline.

Its logic is split across several subflows.

## 5.1 Book Discovery and Scoring

The first subflow is the book-selection workflow.

### What It Does

It:

1. loads course context
2. generates 10 to 12 search queries for textbooks
3. fans out search across:
   - Google Books
   - Tavily
4. extracts candidate books from search results
5. deduplicates books by fuzzy title matching
6. runs a per-book research and scoring loop

### Scoring Logic

Each candidate book is scored through an LLM-assisted research loop using multiple criteria such as:

- topic relevance
- structural alignment
- scope
- author / publisher quality
- freshness
- practical usefulness

### Persistence

This phase persists into PostgreSQL:

- sessions
- discovered book candidates
- scored books

### Human-in-the-Loop

This phase pauses for teacher review.

Teachers:

- inspect discovered/scored books
- choose which books to continue with

## 5.2 Book Selection, Download, and Manual Upload

After review, the teacher selects a small set of books.

The service then:

1. tries to find downloadable PDFs
2. validates PDFs
3. supports manual upload fallback when auto-download fails
4. stores the resolved book file in Azure Blob
5. creates selected-book records in PostgreSQL

This is another explicit human-in-the-loop checkpoint.

## 5.3 PDF Extraction and Chunking Analysis

There is a chunking / extraction analysis path that:

1. downloads selected PDFs
2. extracts chapter structure via a robust multi-strategy PDF extraction module
3. stores chapters in PostgreSQL
4. chunks chapter text
5. embeds chunks
6. scores book chunks against course concepts

This path is primarily about:

- book-content coverage analysis
- summaries
- concept scoring

It is not the main place where `BOOK_SKILL` nodes are created.

## 5.4 Agentic Chapter Extraction

The actual `BOOK_SKILL` creation happens in the agentic chapter extraction path.

This pipeline:

1. loads already extracted chapters from SQL
2. fans out one worker per book chapter
3. for each chapter:
   - extracts practical skills
   - extracts inline prerequisite concepts
   - generates chapter summaries
   - runs a judge pass
   - optionally revises once
4. persists chapter outputs

### Important Output

For each chapter, it writes:

- `BOOK_SKILL` nodes
- `BOOK_SKILL -> REQUIRES_CONCEPT -> CONCEPT`
- `BOOK -> BOOK_CHAPTER -> HAS_SKILL -> BOOK_SKILL`

This is the stage that creates the book-side skill vocabulary.

## 5.5 Book Skill Mapping

After `BOOK_SKILL`s are extracted, a separate mapping flow aligns them to the teacher-created curriculum scaffold.

This flow:

1. loads `COURSE_CHAPTER`s
2. loads `BOOK_CHAPTER`s and their `BOOK_SKILL`s
3. uses an LLM to map book skills to the most appropriate course chapters
4. writes:
   - `BOOK_SKILL -> MAPPED_TO -> COURSE_CHAPTER`

### Why This Matters

This mapping step is what lets the teacher-facing curriculum page present the `Book Skill Bank` as curriculum-relevant rather than as raw isolated textbook output.

## 5.6 Curricular Alignment Architect Summary

The full teacher-side textbook logic is:

1. discover books
2. score books
3. teacher selects books
4. download or upload PDFs
5. extract book chapters
6. run agentic chapter skill extraction
7. create `BOOK_SKILL`s and prerequisite concepts
8. map those skills into `COURSE_CHAPTER`s
9. expose them as the `Book Skill Bank`

---

## 6. Stage D: Market Demand Analyst

The Market Demand Analyst enriches the curriculum with job-market skills.

Important note:

- the README summary is outdated
- the current implementation is a **5-agent swarm plus a non-agent extraction subgraph**

## 6.1 Real Agent Topology

The current chain is:

1. `Supervisor`
2. `Skill Finder`
3. `Curriculum Mapper`
4. `Skill Cleaner`
5. `Concept Linker`

Additionally, there is a non-agent LangGraph extraction subgraph:

- `skill_extractor_subgraph`

## 6.2 Agent Responsibilities

### Supervisor

The `Supervisor` is the only teacher-facing orchestrator inside the swarm.

It:

- proposes job-search direction
- coordinates handoffs
- receives final outputs
- supports re-entry if the teacher changes direction

### Skill Finder

The `Skill Finder` is responsible for the upstream market collection logic.

It:

1. fetches jobs from Indeed and LinkedIn
2. deduplicates jobs
3. groups them by normalized title
4. helps the teacher choose relevant job groups
5. triggers the extraction subgraph
6. presents extracted skills by category
7. records the teacher’s curated selection

### Extraction Subgraph

This is not an LLM chat agent but a fan-out / fan-in programmatic workflow.

It:

1. fans out one branch per selected job posting
2. extracts actionable skills from each posting
3. aggregates raw skill candidates
4. merges semantically similar skills into canonical competency statements
5. computes:
   - frequency
   - percent-of-jobs demand

This produces the `extracted_skills` set.

### Curriculum Mapper

The `Curriculum Mapper` aligns teacher-approved market skills against the current curriculum graph.

It:

1. loads the exact curated skills
2. reads course chapters from Neo4j
3. inspects chapter details and concepts
4. checks skill coverage against:
   - `BOOK_SKILL`
   - existing `MARKET_SKILL`
   - `CONCEPT`
5. classifies each curated skill as:
   - `covered`
   - `gap`
   - `new_topic_needed`
6. assigns target chapters where needed
7. saves one mapping row per curated skill

### Skill Cleaner

The `Skill Cleaner` removes redundancy.

It:

1. loads mapped market skills by chapter
2. loads existing chapter skills
3. compares proposed market skills against already-covered skills in that chapter
4. drops only those that overlap too strongly
5. keeps truly additive competencies

This step is important because the Market Demand Analyst should not flood the curriculum with rephrased copies of skills already covered by textbook analysis.

### Concept Linker

The `Concept Linker` finalizes the graph insertion.

It:

1. derives prerequisite concepts for each approved market skill
2. reuses existing concepts where possible
3. creates new concepts when needed
4. inserts `MARKET_SKILL` nodes
5. links them to:
   - `COURSE_CHAPTER`
   - `JOB_POSTING`
   - `CONCEPT`

This creates:

- `MARKET_SKILL -> MAPPED_TO -> COURSE_CHAPTER`
- `MARKET_SKILL -> SOURCED_FROM -> JOB_POSTING`
- `MARKET_SKILL -> REQUIRES_CONCEPT -> CONCEPT`

## 6.3 Human-in-the-Loop in the Market Flow

Teacher input is still central.

Key checkpoints include:

- approving search terms
- selecting job groups
- curating the extracted skills
- reviewing final outcomes through the UI

The later mapping, cleaning, and concept-linking stages are largely autonomous once the curated skill set is fixed.

## 6.4 Persistence

The Market Demand Analyst uses two persistence layers.

### LangGraph Checkpointing

Conversation / swarm checkpoint state uses `AsyncPostgresSaver`.

### UI-Facing Thread Snapshot

The working pipeline snapshot is also persisted into a dedicated PostgreSQL JSON state table.

The working runtime store includes data such as:

- fetched jobs
- grouped jobs
- selected jobs
- extracted skills
- curated skills
- curriculum mapping
- cleaned skills
- concept-link results
- insertion stats

## 6.5 Market Demand Analyst Summary

The real current logic is:

1. fetch jobs
2. teacher chooses job groups
3. extract and merge market skills
4. teacher curates relevant skills
5. map each curated skill to the curriculum
6. remove redundant ones
7. link concepts
8. insert final `MARKET_SKILL`s into Neo4j
9. expose them as the `Market Skill Bank`

---

## 7. The Two Central Skill Banks

These are the central midpoint outputs of the teacher-side enrichment pipeline.

## 7.1 Book Skill Bank

The `Book Skill Bank` is produced from:

1. selected textbooks
2. chapter-level skill extraction
3. `BOOK_SKILL` creation
4. mapping into `COURSE_CHAPTER`s

Its visible structure in the UI is:

- book
- chapter
- extracted book skills

## 7.2 Market Skill Bank

The `Market Skill Bank` is produced from:

1. job posting collection
2. per-job skill extraction
3. teacher curation
4. curriculum mapping
5. redundancy cleaning
6. concept linking
7. final insertion as `MARKET_SKILL`

Its visible structure in the UI is:

- job posting
- associated market skills
- status such as covered / gap / new topic
- demand percentage

## 7.3 Why These Banks Matter

Together, these banks define:

- what the course can currently teach from textbooks
- what the market is asking for

This makes them the conceptual center of the whole system.

---

## 8. Teacher-Facing UI Outputs

The teacher-facing curriculum page currently presents three major views plus a changelog.

## 8.1 Transcripts Tab

This tab shows transcript-derived `COURSE_CHAPTER`s and their linked uploaded documents.

It reflects the teacher-owned curriculum scaffold.

## 8.2 Book Skills Tab

This tab shows the `Book Skill Bank`:

- books
- chapters
- extracted skills

## 8.3 Market Skills Tab

This tab shows the `Market Skill Bank`:

- job postings
- mapped market skills
- category
- priority
- coverage status
- demand

## 8.4 Agent Changelog

The curriculum UI also surfaces a market-skill changelog, especially around inserted market skills and their status.

## 8.5 Important UI Limitation

The data model already supports:

- readings
- videos

However, the current teacher-side curriculum page does **not** fully expose those resources as a primary teacher workflow.

Those resources are mainly surfaced later in the student-facing learning-path interface.

---

## 9. Stage E: Reading Agent and Video Agent (Current Reality)

The old docs understate what is implemented, but the current code also differs from the idealized “standalone teacher agent” framing.

## 9.1 What Is Implemented

Both resource pipelines are real.

### Textual Resource Analyst

The reading pipeline:

1. receives a skill profile
2. generates search queries
3. searches for text-based resources
4. filters and ranks them
5. returns top reading resources

It is configured to prioritize:

- tutorials
- documentation
- articles
- guides

### Video Agent / Visual Content Evaluator

The video pipeline:

1. receives a skill profile
2. generates YouTube-focused search queries
3. searches for educational videos
4. scores them by:
   - recency
   - concept coverage
   - pedagogy
   - depth
   - production quality
5. returns top video resources

## 9.2 What Is Not Implemented as a Standalone Teacher Flow

There is **not yet** a separate teacher-facing top-level workflow where a teacher explicitly runs a “reading agent page” or “video agent page” as a primary production path.

Instead:

- the reading and video services are currently used inside the student learning-path builder

So the implementation status is:

- resource generation logic exists
- standalone teacher-facing resource-agent product flow is still incomplete

---

## 10. Stage F: Student Learning Path

This is where readings, videos, and questions are currently generated in practice.

## 10.1 Trigger

Students:

1. browse the two skill banks
2. select skills and optionally job postings
3. click `Build My Learning Path`

That action triggers the learning-path LangGraph pipeline.

## 10.2 Learning Path Orchestrator

The student learning-path graph does the following:

1. loads selected skills
2. checks whether each skill already has:
   - readings
   - videos
   - questions
3. fans out one worker per skill needing work
4. aggregates results

This means resource generation is incremental and avoids duplicate work.

## 10.3 Per-Skill Worker Logic

For each selected skill, the worker may run up to three pipelines.

### Readings

If the skill lacks readings:

- call the Textual Resource Analyst
- write `HAS_READING`

### Videos

If the skill lacks videos:

- call the video pipeline
- write `HAS_VIDEO`

### Questions

If the skill lacks questions:

- generate three multiple-choice questions
- persist them for the skill

## 10.4 Student Learning Path Output

The result is a personalized path containing:

- selected skills
- curated readings
- curated videos
- generated questions

This is the current main user-visible place where resource generation appears end-to-end.

---

## 11. Question Generation

Question generation is implemented as a separate service but is currently orchestrated by the student learning-path pipeline.

For each skill, it generates:

- exactly 3 multiple-choice questions
- easy
- medium
- hard

The question generator uses only the skill metadata:

- skill name
- description
- concepts
- course level

It does not require a specific reading or video as source material.

---

## 12. End-to-End Logic Across Agents

The system can be summarized as two connected layers.

## 12.1 Teacher-Side Enrichment Layer

This layer builds the curriculum knowledge base and the two skill banks.

Flow:

1. teacher uploads course files
2. document extraction builds concepts
3. embeddings support semantic retrieval
4. teacher chapter planner creates `COURSE_CHAPTER`s
5. Curricular Alignment Architect builds the `Book Skill Bank`
6. Market Demand Analyst builds the `Market Skill Bank`

## 12.2 Student-Side Personalization Layer

This layer consumes the two skill banks.

Flow:

1. student selects skills from the two banks
2. student learning path orchestrates per-skill work
3. reading resources are generated
4. video resources are generated
5. questions are generated
6. a personalized path is returned

---

## 13. Important Corrections to Older Documentation

Based on the current codebase, several old simplifications are no longer accurate.

### Correction 1

The Market Demand Analyst is **not** the older 3-agent design in current implementation.

It is now:

- 5 swarm agents
- plus a non-agent extraction subgraph

### Correction 2

The reading and video pipelines are **implemented**, but they are not currently the main teacher-facing generation step.

They are primarily triggered through the student learning-path workflow.

### Correction 3

`BOOK_SKILL`s are not created during book discovery itself.

They are created later during chapter-level agentic book analysis.

### Correction 4

Teacher-created `COURSE_CHAPTER`s are the structural anchor of the curriculum.

Books and market analysis enrich that scaffold rather than replacing it.

---

## 14. Practical Paper Framing

If this is used in the conference paper, the cleanest framing is:

1. **Knowledge Graph Construction**
   - document extraction
   - concept extraction
   - embeddings
   - teacher chapter planning

2. **Teacher-Side Curriculum Enrichment**
   - Curricular Alignment Architect -> `Book Skill Bank`
   - Market Demand Analyst -> `Market Skill Bank`

3. **Student-Side Personalization**
   - Student Learning Path
   - Textual Resource Analyst
   - Video Agent
   - Question Generator

This framing matches the implemented logic more closely than older proposal text.

---

## 15. Short Agent-by-Agent Summary

### Document Extraction Service

Turns uploaded teacher files into graph documents, summaries, and concepts.

### Embeddings Service

Adds vector searchability to documents and concepts.

### Teacher Curriculum Planner

Builds the `COURSE_CHAPTER` scaffold from teacher documents.

### Curricular Alignment Architect

Discovers books, scores them, processes selected textbooks, extracts `BOOK_SKILL`s, and maps them into course chapters.

### Market Demand Analyst

Collects job postings, extracts market skills, maps them against the curriculum, removes redundancy, and inserts `MARKET_SKILL`s.

### Textual Resource Analyst

Finds and ranks text-based learning resources for a skill.

### Video Agent / Visual Content Evaluator

Finds and ranks video learning resources for a skill.

### Question Generator

Creates three difficulty-graded MCQs per skill.

### Student Learning Path

Consumes selected skills from the two banks and orchestrates resource + question generation into a personalized path.

---

## 16. Final Takeaway

The implemented system is best understood as:

- a teacher-side graph-enrichment platform that produces two central skill banks
- followed by a student-side personalization pipeline that generates readings, videos, and questions from those banks

In that sense:

- the `Book Skill Bank` captures textbook-supported competencies
- the `Market Skill Bank` captures labor-market-driven competencies
- the downstream learning-path pipeline converts both into actionable learning resources

That is the current end-to-end logic of the codebase.
