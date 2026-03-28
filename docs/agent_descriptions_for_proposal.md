PART 1 — OVERALL RESEARCH IDEA


The core idea of this research is to design, build, and evaluate a graph-centered educational intelligence platform for computer science courses. A Course Knowledge Graph serves as the central "memory" and "content backbone" of the system, capturing the semantic structure of every course — its topics, chapters, concepts, skills, textbooks, and their interrelationships. Around this graph, the platform layers automated extraction, quality control, curriculum alignment, market enrichment, and teaching resource curation services, all coordinated through multi-agent AI workflows with instructor oversight.

The platform works in two main stages. First, it prepares the raw materials: course documents are uploaded, concepts and relationships are extracted from them, and semantic vector representations are generated for similarity-based search. This transforms passive teaching files into a structured, searchable course knowledge graph. Second, four AI agent systems — each addressing a distinct problem — enrich and refine this graph in a connected pipeline:

Stage 1: Knowledge Graph Construction. Instructors upload course materials (lectures, slides, textbooks). The platform extracts concepts, definitions, and evidence from these documents, generates semantic embeddings, and writes the results into a course knowledge graph — turning unstructured files into organized, queryable knowledge.

Stage 2: Agent-Driven Curriculum Enrichment. Four interconnected AI agents operate on the knowledge graph:

1. Curricular Alignment Architect. Discovers candidate textbooks from the web, evaluates them against the course objectives, and — after instructor approval — downloads and analyzes selected books at the chapter level, extracting the concrete skills each chapter can teach.

2. Market Demand Analyst. Collects real job postings, extracts the skills employers demand, and aligns each one against the curriculum skills identified by the first agent — classifying every market skill as already covered, partially covered, or entirely missing.

3. Textual Resource Analyst. Takes every identified skill — from both textbook analysis and market-demand analysis — and curates the best online learning materials (tutorials, documentation, articles) to teach each one.

4. Video Agent. Complements the Textual Resource Analyst by finding the best educational video content for each identified skill — searching platforms such as YouTube and online course providers, then ranking candidates on relevance, recency, pedagogical quality, and source authority.

Together, these agents form an end-to-end pipeline: textbook analysis builds the skill vocabulary → market analysis aligns it with industry reality → text and video resource curation finds the best way to teach each skill.

At every critical decision point, the system pauses for instructor review and approval, ensuring that all AI-generated proposals are validated by a human expert before being finalized.

Future Layer: Tutoring and Personalization. The enriched, cleaned, and market-aligned knowledge graph — together with semantic embeddings and curated teaching resources — establishes the foundation for future student-facing features: graph-grounded question answering, cognitive diagnosis, knowledge tracing, and personalized learning recommendations.


---


PART 2 — RESEARCH METHODS (DETAILED AGENT DESCRIPTIONS)


Task 1: Document Extraction and Embeddings

Document Extraction Service

This service processes teacher-uploaded course materials (PDF, DOCX, TXT) by downloading files from cloud storage, parsing them, and applying LLM-driven structured extraction to identify the topic, summary, keywords, and concrete concepts within each document. Each extracted concept includes its canonical name, a definition, and verbatim textual evidence from the source material. The results are written into the knowledge graph as TEACHER_UPLOADED_DOCUMENT → MENTIONS → CONCEPT relationships, transforming passive files into structured, queryable knowledge assets. The service tracks processing status in SQL (PENDING → PROCESSED → FAILED) and serves as the entry point for all subsequent enrichment workflows.

Embeddings Service

Following document extraction, this service computes high-dimensional vector embeddings (2048-dimensional by default, using OpenAI's text-embedding model) for both documents and individual concept mentions. It employs content-change detection via SHA-256 hashing — if neither the text nor the embedding model has changed since the last run, recomputation is skipped. Embedding generation is parallelized via a thread pool for efficiency. The resulting vectors are stored on knowledge graph nodes, making the entire knowledge base searchable via vector similarity and enabling downstream retrieval-augmented generation.

Expected Outcome: A high-quality course knowledge graph and a semantic retrieval substrate ready for downstream alignment and enrichment.


---


Task 2: Textbook Discovery and Curriculum Alignment (Curricular Alignment Architect)

Problem: How can instructors efficiently identify which textbooks best support the intended curriculum and understand how each chapter maps to course objectives?

Method: This agent implements a multi-phase LangGraph workflow that automates the entire textbook evaluation cycle:

1. Discovery — The agent generates 10–12 diverse search queries from the course description and objectives, then searches Google Books and Tavily APIs in parallel. Results are deduplicated via fuzzy title matching.

2. Multi-Criteria Scoring — Each candidate textbook is evaluated through a ReAct reasoning loop (up to 5 iterations per book) against seven weighted criteria: topic relevance (30%), pedagogical structure (20%), scope coverage (15%), publisher reputation (15%), author credentials (10%), currency (10%), and practical value.

3. Instructor Review (Human-in-the-Loop) — The workflow pauses to present ranked results. The instructor selects which books to adopt (up to five). Only after this human checkpoint does the agent proceed.

4. Download and Storage — The agent searches for accessible copies, downloads validated PDFs, and stores them in cloud storage.

5. Chapter-Level Analysis — Each book is segmented into chapters. Multiple chapters are analyzed in parallel, identifying key concepts, skills, and relationships, which are written into the knowledge graph as BOOK → CHAPTER → SECTION → CONCEPT.

Expected Outcome: A library of instructor-approved textbooks with chapter-level curriculum alignment data and a skill vocabulary derived from each book's content.


---


Task 3: Market-Demand Alignment (Market Demand Analyst)

Problem: How can a university course remain aligned with real industry expectations instead of becoming isolated from the evolving job market?

Method: This agent employs a 3-agent LangGraph swarm with a Supervisor, a Curriculum Mapper, and a Concept Linker working in coordinated sequence:

1. Job Discovery — The Supervisor agent collects job postings from major employment platforms (Indeed, LinkedIn) using parallel scraping, deduplicates by normalized title and company, and groups results by role type. The instructor selects which job categories are relevant.

2. Skill Extraction — Selected job descriptions are processed in parallel batches (groups of 5 jobs, up to 5 concurrent workers). The LLM extracts concrete, actionable skills with synonym canonicalization (e.g., "k8s" → "Kubernetes"). Each skill receives a demand frequency score and a priority classification (high: 40% or above, medium: 15–40%, low: below 15%).

3. Curriculum Mapping — The Curriculum Mapper agent autonomously compares every extracted market skill against the existing course knowledge graph — checking which skills are already covered, which are partially covered (gaps), and which are entirely missing.

4. Concept Linking — The Concept Linker agent determines the underlying concepts each skill requires (constrained to 2–6 concepts per skill) and writes MARKET_SKILL → REQUIRES_CONCEPT relationships into the knowledge graph.

5. Instructor Approval — At every critical stage, the instructor reviews and approves results before the system persists them to the knowledge graph.

Expected Outcome: An evidence-based alignment between curriculum content and industry demand, with approved market skills enriching the course knowledge graph.


---


Task 4: Teaching Resource Curation (Textual Resource Analyst)

Problem: Once the platform knows what skills the curriculum can teach and what additional skills the market demands, how do we find the best available materials to actually teach each skill?

Method: This agent takes every identified skill — from both textbook analysis and market-demand analysis — and systematically curates the best online learning materials:

1. Contextualized Search — For each skill, the agent constructs a profile including related concepts, course level, and chapter context, then generates diverse search queries targeting different resource types (tutorials, documentation, articles).

2. Multi-Source Collection and Filtering — The agent searches multiple web sources in parallel, collects candidates, removes duplicates, and applies semantic similarity filtering.

3. Quality Evaluation and Ranking — Each candidate is scored on five criteria: recency, relevance, pedagogical quality, depth, and source authority. The top 3–5 resources per skill are selected, ensuring variety in resource types.

Expected Outcome: A curated, scored library of online learning resources linked to every skill in the curriculum — connecting "what to learn" with "where to learn it."

Status: Architecture designed; implementation in progress.


---


Task 5: Video Resource Curation (Video Agent)

Problem: Written materials alone are not always the most effective way to learn a technical skill. Students benefit from video explanations, live coding walkthroughs, and structured course lectures. How can the platform automatically identify the best video content for every skill in the curriculum?

Method: The Video Agent mirrors the structure of the Textual Resource Analyst but targets video platforms and online course providers:

1. Contextualized Query Generation — For each skill, the agent builds a search profile (skill name, linked concepts, course level) and generates targeted queries for video content, including recency filters to prioritize current material.

2. Multi-Platform Search — The agent searches video platforms (e.g., YouTube) and online course providers in parallel, collecting candidate videos and structured course segments. Duplicates are removed by URL normalization.

3. Quality Evaluation and Ranking — Each candidate is evaluated on five criteria: recency, relevance, pedagogical quality, depth, and source authority (e.g., official channel vs. personal upload). The top 3–5 videos per skill are selected, ensuring variety in format (short tutorial, full lecture, live coding).

4. Knowledge Graph Storage — Approved video resources are written into the knowledge graph as VIDEO nodes linked to their corresponding SKILL and CONCEPT nodes, making them available for future retrieval and student recommendation.

Expected Outcome: A curated, ranked library of educational video content linked to every skill in the curriculum — complementing text resources and giving students multiple learning pathways for each topic.

Status: Architecture designed; implementation in progress.


---


Summary

Task 1 — Document Extraction and Embeddings
  Input: PDF/DOCX/TXT files
  Output: Concepts and vectors in the knowledge graph
  Key Technique: LLM extraction, SHA-256 change detection, parallel embedding
  Instructor Oversight: None

Task 2 — Curricular Alignment Architect
  Input: Course context and objectives
  Output: Textbook chapters and skills in the knowledge graph
  Key Technique: Parallel web search, ReAct scoring loop, fuzzy matching
  Instructor Oversight: 3 review checkpoints

Task 3 — Market Demand Analyst
  Input: Job search terms
  Output: Market skills aligned to curriculum
  Key Technique: Multi-agent swarm, parallel skill extraction, coverage mapping
  Instructor Oversight: 4 review checkpoints

Task 4 — Textual Resource Analyst
  Input: Identified skills
  Output: Curated and ranked learning resources
  Key Technique: Contextualized search, multi-criteria ranking
  Instructor Oversight: Approval before save

Task 5 — Video Agent
  Input: Identified skills
  Output: Curated and ranked video resources
  Key Technique: Multi-platform video search, multi-criteria ranking
  Instructor Oversight: Approval before save

Pipeline flow: Document extraction → Embeddings → Textbook analysis builds the skill vocabulary → Market analysis aligns it with industry reality → Text and video resource curation finds the best way to teach each skill.
