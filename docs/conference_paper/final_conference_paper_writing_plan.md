# Final Conference Paper Writing Plan

## Decision on Workflow

Use a two-stage workflow:

1. Draft and lock the paper structure, claims, figure placements, table contents, and citation plan in Markdown first.
2. Transfer the stabilized content into a duplicated conference template `.docx` at the end, preserving the original formatting and comments.

File roles:

- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/lab_tutor_conference_paper_working_template.docx` should remain the pristine backup copy of the official template.
- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/lab_tutor_conference_paper_working.docx` should be the only editable Word file for final layout.

This is the safer method for this project because:

- the official template has many embedded formatting comments that should not be disturbed
- the paper still needs structural decisions about section order, evidence placement, and wording scope
- diagrams, algorithms, and results still need selection and trimming before final Word insertion
- direct editing inside the template too early increases the risk of formatting drift

The `.docx` should therefore be treated as the final layout container, not the main planning workspace.

## Official Template Constraints

From the official template and embedded comments in [教育技术协会 英文论文模板 2026.docx](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/教育技术协会%20英文论文模板%202026.docx):

- title: generally no more than 30 words
- subtitle: optional
- authors: maximum 5, corresponding author marked
- abstract: 200-400 words
- keywords: 3-8, separated by semicolons
- paper length: 6,000-8,000 words for a long paper
- figures + tables: no more than 8 total
- references: at least 10, APA 7th
- headings: maximum third level
- body style: Times New Roman, 10.5 pt, first-line indentation, 1.2 line spacing
- first-level heading: bold, title case, 14 pt
- second-level heading: bold, title case, 12 pt
- third-level heading: bold italic, title case, 10.5 pt
- table title goes above the table
- figures/tables must be referenced in the main text
- no blank line is needed before the text following figures/tables
- formulas and side-by-side figures rely on table-based layout in the template and should not be reformatted casually

## Paper Story to Lock

The strongest defensible paper story is:

Higher education faces three linked problems: fragmented course knowledge, weak curriculum-market alignment, and high manual cost of resource construction. Lab Tutor addresses these problems with a knowledge-graph-centric multi-agent framework that structures course knowledge, aligns it with textbooks and labor-market skills, and supports downstream learning resources. A Big Data course case study shows that curriculum enrichment improves estimated curriculum-to-market alignment on a small held-out evaluation.

This keeps the paper:

- aligned with the professor's framework in [teacher_proposed_paper framework-Roma.docx](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/teacher_proposed_paper%20framework-Roma.docx)
- aligned with the codebase reality summarized in [agent_logic_current.md](/Users/khajievroma/Projects/lab_tutor/docs/agent_logic_current.md)
- aligned with the current experiment framing in [big_data_experiment_in_conference_paper.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/big_data_experiment_in_conference_paper.md)

## Recommended Final Outline

Use your cleaner five-section structure:

1. Introduction
2. Related Work
3. Methodology
4. Results
5. Conclusion

This still preserves the teacher's preferences, because the framework overview and the case-study design can both live inside `Methodology`.

### 1. Introduction

Purpose:

- present the curriculum-market mismatch problem
- present fragmentation of teaching knowledge
- present the cost of manual resource construction
- introduce the proposed system and case study

End with 3 contributions:

1. A knowledge-graph-centric multi-agent framework for intelligent curriculum resource construction.
2. A unified alignment pipeline connecting teacher materials, textbooks, market skills, and skill-linked learning resources.
3. A Big Data course case study showing improved estimated curriculum-to-market alignment under curriculum enrichment.

### 2. Related Work

Keep this compact and grouped into categories:

- knowledge graphs in education
- AI or multi-agent educational support systems
- curriculum-industry alignment and labor-market intelligence
- intelligent resource recommendation and personalized learning support

Important note:

The two research background markdown files strongly support the third category and part of the motivation, but they do **not** fully cover the academic literature needed for the first two categories. Additional academic citations will still be needed for knowledge graphs in education and multi-agent educational systems.

### 3. Methodology

Recommended subsections:

- 3.1 Framework Overview and Design Principles
- 3.2 Task 1: Document Extraction, Concept Structuring, and Embeddings
- 3.3 Task 2: Textbook Discovery and Curriculum Alignment
- 3.4 Task 3: Market-Demand Alignment
- 3.5 Task 4: Resource Curation and Student Learning Support
- 3.6 Human-AI Review and Quality Assurance
- 3.7 Big Data Case Study and Evaluation Design

`3.1 Framework Overview and Design Principles` should present the professor's three-layer model clearly before diving into the tasks.

#### 3.1 Framework Overview and Design Principles

Cover:

- the three educational problems
- the knowledge-graph-centric design
- the three-layer framework
- why human review is retained at key checkpoints

#### 3.2 Task 1: Document Extraction, Concept Structuring, and Embeddings

Sources:

- [agent_descriptions_for_proposal.md](/Users/khajievroma/Projects/lab_tutor/docs/agent_descriptions_for_proposal.md)
- [agent_logic_current.md](/Users/khajievroma/Projects/lab_tutor/docs/agent_logic_current.md)

Paper role:

- foundation of the course knowledge graph
- transcript-grounded curriculum memory

#### 3.3 Task 2: Textbook Discovery and Curriculum Alignment

Sources:

- [agent_descriptions_for_proposal.md](/Users/khajievroma/Projects/lab_tutor/docs/agent_descriptions_for_proposal.md)
- [agent_logic_current.md](/Users/khajievroma/Projects/lab_tutor/docs/agent_logic_current.md)
- [conference_paper_algorithm_drafts.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/conference_paper_algorithm_drafts.md)

Paper role:

- build the book-side skill bank
- align textbook-supported skills to teacher-owned course chapters

#### 3.4 Task 3: Market-Demand Alignment

Sources:

- [agent_descriptions_for_proposal.md](/Users/khajievroma/Projects/lab_tutor/docs/agent_descriptions_for_proposal.md)
- [agent_logic_current.md](/Users/khajievroma/Projects/lab_tutor/docs/agent_logic_current.md)
- [MARKET_DEMAND_ANALYST.md](/Users/khajievroma/Projects/lab_tutor/docs/MARKET_DEMAND_ANALYST.md)
- [conference_paper_algorithm_drafts.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/conference_paper_algorithm_drafts.md)
- [market_demand_algorithm.tex](/Users/khajievroma/Projects/lab_tutor/docs/market_demand_algorithm.tex)

Paper role:

- build the market-side skill bank
- classify skills as covered, gap, or new-topic-needed
- serve as the main evaluated layer in the case study

#### 3.5 Task 4: Resource Curation and Student Learning Support

Sources:

- [agent_descriptions_for_proposal.md](/Users/khajievroma/Projects/lab_tutor/docs/agent_descriptions_for_proposal.md)
- [agent_logic_current.md](/Users/khajievroma/Projects/lab_tutor/docs/agent_logic_current.md)
- [conference_paper_algorithm_drafts.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/conference_paper_algorithm_drafts.md)

Paper role:

- show how aligned skills lead to readings, videos, and student support
- keep implementation discussion concise

Important wording constraint:

The current codebase supports reading and video generation, but these are primarily surfaced through the student learning-path pipeline rather than as a fully mature teacher-facing workflow. The paper should state this carefully and avoid implying a finished standalone teacher-side resource workflow if that is not what the implementation currently delivers.

#### 3.6 Human-AI Review and Quality Assurance

Keep the checkpoints visible:

- book approval
- skill curation
- concept merge or concept-link review
- optional resource approval

#### 3.7 Big Data Case Study and Evaluation Design

Recommended subsections:

- 3.7.1 Big Data Course and Data Sources
- 3.7.2 Curriculum Variants
- 3.7.3 Job-Skill Evaluation Procedure
- 3.7.4 Evaluation Metrics
- 3.7.5 Resource Answerability Procedure

Key experimental framing from [big_data_experiment_in_conference_paper.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/big_data_experiment_in_conference_paper.md):

- `62` deduplicated raw jobs in the broad graph pool
- `28` strict-scope Big Data / Data Engineering jobs for the main benchmark
- strict-scope corpus split into `20` build jobs and `8` held-out jobs
- `7` student seed jobs and `55` student remaining jobs for the personalized case study
- evaluated jobs now use persisted job descriptions, so the current run extracts skills from raw job text

Safe research questions:

1. To what extent does the transcript-only curriculum cover skills required by relevant job postings?
2. How much does textbook and job-market enrichment improve estimated curriculum-to-market alignment?
3. To what extent do the retrieved readings and videos contain enough information to answer generated skill questions?

For `3.7.5 Resource Answerability Procedure`, describe the current notebook evaluation as:

- the actual visible Big Data learning path in the graph
- `61` course-path skills with `183` generated questions total
- one question per difficulty level per skill: `easy`, `medium`, `hard`
- a blind yes/no LLM judge that sees only the question and the hydrated reading/video evidence
- three evidence conditions: `readings`, `videos`, and `combined`
- `549` total judgments across the three modalities

Important wording constraint:

- this is a resource-sufficiency proxy, not a direct human learning study
- the judge estimates whether the retrieved materials contain enough information to answer the question
- it should be reported as answerability of the retrieved materials, not as measured student performance

### 4. Results

Recommended subsections:

- 4.1 Curriculum-to-Market Alignment Summary
- 4.2 Resource Answerability of Retrieved Learning Materials
- 4.3 Discussion and Limitations

Main course-level numeric results from [big_data_experiment_in_conference_paper.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/big_data_experiment_in_conference_paper.md):

- `KG`: coverage `0.2961`, average job-fit `0.2775`
- `KG + B_S`: coverage `0.3398`, average job-fit `0.3179`
- `KG + J_S`: coverage `0.4806`, average job-fit `0.4602`
- `KG + B_S + J_S`: coverage `0.4757`, average job-fit `0.4568`

Student-centered spillover results to mention:

- `KG`: coverage `0.2608`, average job-fit `0.2588`
- `KG + B_S`: coverage `0.2671`, average job-fit `0.2646`
- `KG + J_S`: coverage `0.4196`, average job-fit `0.4259`
- `KG + B_S + J_S`: coverage `0.4266`, average job-fit `0.4333`

Interpretation to emphasize:

- market enrichment explains most of the lift
- textbook enrichment adds smaller but still complementary value
- in the course-level benchmark, `KG + J_S` is the strongest held-out variant
- in the student case study, the skills extracted from `7` target job postings drive most of the spillover to the other `55` jobs
- the course-level held-out sample is still too small for strong threshold-based claims

Resource-answerability results from the notebook artifacts in `/backend/app/modules/student_learning_path/notebooks/artifacts`:

- `61` evaluated skills
- `183` total questions
- `549` yes/no answerability judgments
- overall answerable rate: `22.95%`
- by modality:
  - `readings`: `28.42%` (`52 / 183`)
  - `combined`: `27.32%` (`50 / 183`)
  - `videos`: `13.11%` (`24 / 183`)
- by difficulty:
  - `easy`: `36.07%`
  - `medium`: `26.23%`
  - `hard`: `6.56%`
- by modality and difficulty:
  - easy: readings `42.6%`, videos `21.3%`, combined `44.3%`
  - medium: readings `29.5%`, videos `18.0%`, combined `31.1%`
  - hard: readings `13.1%`, videos `0.0%`, combined `6.6%`
- by skill source:
  - book skills: `34.78%`
  - market skills: `15.79%`

Interpretation to emphasize in `4.2`:

- retrieved readings currently support more questions than retrieved videos
- the combined condition is only slightly better than readings alone, which suggests that current video evidence often adds little support
- answerability drops sharply with difficulty, especially for hard questions
- book-linked skills are better supported than market-derived skills, indicating that resource coverage is stronger for course-adjacent concepts than for newer labor-market demands

In `4.3 Discussion and Limitations`, include:

- educational significance of alignment-aware curriculum design
- why the system supports curriculum improvement and skill-oriented learning
- that this is a case study, not a universal benchmark
- that the evaluation measures estimated curriculum-to-market alignment, not employment outcomes
- that the held-out run is still small-sample
- that the student table is a personalized spillover analysis based on `7` target jobs rather than a held-out benchmark
- that the answerability analysis uses a blind LLM judge as a proxy for resource sufficiency, not a human-subject learning assessment

### 5. Conclusion

Keep it short:

- restate the problem
- restate the framework
- restate the case-study finding
- note future work on larger evaluation and richer student-facing deployment

## Figure, Table, and Algorithm Plan

The template allows at most 8 figures + tables total. Because you want only one diagram, use a much leaner plan.

Recommended budget:

- 1 figure
- 3 tables
- 2 algorithms in the main paper

### Main Figures

#### Figure 1. Answerable Questions by Difficulty and Modality

Purpose:

- the single strongest visual result for the current paper
- directly shows whether students could plausibly find answers in the retrieved materials
- best placed in Section 4.2

Use:

- the grouped bar chart from [resource_answerability_llm_judge.ipynb](/Users/khajievroma/Projects/lab_tutor/backend/app/modules/student_learning_path/notebooks/resource_answerability_llm_judge.ipynb)
- title: `Answerable Questions by Difficulty and Modality`
- x-axis: `easy`, `medium`, `hard`
- grouped bars: `readings`, `videos`, `combined`
- y-axis: answerable rate

Why this should be the only figure:

- it captures the downstream educational value of the full pipeline better than a framework diagram
- it is easier for reviewers to read quickly than a complex architecture figure
- the alignment results can be communicated clearly in tables without losing credibility

### Optional or Secondary Figures

#### Database Schema Figure

- [database_schema.png](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/database_schema.png) is useful as internal planning material
- in its current form it is too dense for the main paper
- if included, it should be redrawn as a simplified conceptual subgraph, not used raw

Recommendation:

Do **not** use the raw schema image as a main paper figure. Prefer a cleaner conceptual data model if a second system figure is needed.

#### UI Screenshot

- [UI_schreenshot_of_student_choosing_skills.png](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/UI_schreenshot_of_student_choosing_skills.png)

Assessment:

- useful as application context
- not necessary for proving the main claim
- should stay out of the main paper unless space remains or the conference strongly values interface demonstration

Best use:

- appendix
- presentation slide
- poster

#### Framework or Agent-Ecology Figure

Assessment:

- useful for a presentation or dissertation chapter
- not the best use of the single allowed figure slot in this paper

Best use:

- describe the framework concisely in Section 3
- rely on the two algorithms plus the methodology text instead of a second visual

### Tables

#### Table 1. Dataset Summary

Columns:

- course
- transcript documents
- chapters
- raw job postings
- retained job postings
- dropped job postings
- build jobs
- held-out jobs
- evaluated learning-path skills
- generated questions

#### Table 2. Main Experimental Results

Columns:

- variant
- demand-weighted skill coverage
- average job-fit score
- job-fit success rate at `0.60`

#### Table 3. Resource Answerability Results

Columns:

- difficulty
- readings yes count / rate
- videos yes count / rate
- combined yes count / rate

### Algorithms

Recommended for main paper:

- Algorithm 1: textbook-side skill-bank construction
- Algorithm 2: market-side skill-bank construction

Source:

- [conference_paper_algorithm_drafts.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/conference_paper_algorithm_drafts.md)

Placement:

- Algorithm 1 in Section 3.3
- Algorithm 2 in Section 3.4

Algorithm 3 recommendation:

- the reading/video retrieval algorithm is useful
- keep it for Section 4.4 only if space allows
- otherwise move it to appendix or supplementary material

## Research Markdown Files: How to Use Them

### 1. ChatGPT Deep Research File

Primary file:

- [chatgpt_deep_research.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/chatgpt_deep_research.md)

This is the stronger of the two background files for actual paper drafting because it is more structured and more clearly organized around claims, evidence, and citation categories.

#### Best themes to extract

- graduate transition friction and underemployment
- curriculum-market mismatch as a structural problem
- rapid skill change and curriculum recency risk
- employer preparedness gaps
- economic and social cost of mismatch
- need for structured, data-driven alignment systems

#### Best citation categories to reuse

- graduate outcomes: Eurostat, OECD, New York Fed, ILO
- underemployment persistence: Burning Glass Institute + Strada
- skill change velocity: World Economic Forum, Lightcast, LinkedIn
- employer preparedness gaps: NACE, AAC&U
- economic cost of mismatch: Economics Letters 2025 mismatch paper, OECD mismatch discussion
- employer talent shortage: ManpowerGroup

#### Claims this file can support well

- employment rate alone does not mean curriculum alignment
- graduate underemployment remains persistent and substantial
- labor-market skill requirements are changing quickly
- universities need more continuous and evidence-based alignment mechanisms
- curriculum mismatch has economic, institutional, and equity costs

#### Best use in the paper

- Introduction background paragraphs
- motivation at the start of Section 1
- part of Related Work under curriculum-industry alignment
- one sentence in Discussion on broader relevance

### 2. Gemini Deep Research File

Primary file:

- [Gemini_deep_research_on_the_project.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/Gemini_deep_research_on_the_project.md)

This file is useful mainly for themes, framing language, and identifying possible citation leads. It is less safe to use directly because several references are journalistic, blog-like, or secondary summaries rather than ideal conference-paper sources.

#### Best themes to extract

- structural bottlenecks in curriculum revision
- reliance on lagging indicators for curriculum updates
- fragmentation of academic knowledge across heterogeneous documents
- faculty workload and manual resource-construction burden
- shift toward skills-based hiring
- rationale for human-AI collaborative alignment systems

#### Claims this file can support if backed by strong source selection

- curriculum revision cycles are slower than market shifts
- fragmented course artifacts make systematic alignment difficult
- faculty time burden makes manual resource updating unsustainable
- employers increasingly rely on skills-first hiring logic
- intelligent alignment systems are becoming educationally necessary

#### Use with caution

Do **not** rely directly on weaker or non-academic references from this file in the final paper if stronger official or scholarly equivalents are available.

Prefer replacing or verifying these with:

- WEF
- LinkedIn Economic Graph
- NACE
- AAC&U
- Educause
- peer-reviewed higher-education or Industry 4.0 / Education 4.0 papers

#### Best use in the paper

- sharpening the wording of the problem statement
- expanding the "high manual cost of resource construction" motivation
- adding one paragraph on why skills-first hiring pressures universities to respond faster

## What the Research Notes Do Not Yet Cover Well

Still needed for the final paper:

- academic related work on knowledge graphs in education
- academic related work on multi-agent educational systems
- academic related work on graph-grounded resource recommendation or learning-path generation
- a final vetted APA 7th reference list built from primary or reputable scholarly sources

## Current Evidence Strength and Weak Points

### Strong

- clear three-layer framework
- current codebase supports the main system story
- two strong main result figures already exist
- algorithms for textbook and market alignment are already drafted
- experimental framing and limitation language are already written

### Weak or Risky

- raw database schema is too dense for direct paper use
- current system-architecture image is too crowded and not paper-ready
- UI screenshot is not central evidence
- resource-application layer is real but less mature as a teacher-facing flow
- the held-out evaluation is still small-sample, and the student-case table is a personalized spillover analysis built from `7` target jobs
- related work still needs stronger academic citations for knowledge-graph and multi-agent education literature

## Recommended Writing Order

Write in this order:

1. Section 1 Introduction
2. Section 3 Framework Overview
3. Section 4 Methodology and System Realization
4. Section 5 Case Study and Experimental Design
5. Section 6 Results
6. Section 7 Discussion and Limitations
7. Section 2 Related Work
8. Section 8 Conclusion
9. Abstract

Reason:

- the system story and case study need to be stabilized first
- related work and abstract are easier to tune after the claims are fixed

## Immediate Next Steps

1. Confirm the final section outline in this file.
2. Build a citation shortlist from the two research markdown files, keeping only strong sources.
3. Decide whether Figure 2 will be a simplified agent ecology figure or a simplified conceptual data model.
4. Draft the Introduction and Framework sections in Markdown.
5. Draft the task-by-task Methodology section with Algorithms 1 and 2 mapped into it.
6. Draft the experiment and results sections using the existing numbers and figures.
7. Only after the text is stable, move it into the duplicated `.docx` template and preserve all template formatting.
