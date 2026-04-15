# Lab Tutor Conference Paper Master Draft

> Update note (2026-03-31): the notebook now uses a two-table evaluation design and the latest artifact has already been written.
> The current evaluation snapshot is `62` deduplicated raw jobs, `28` strict-scope main jobs, `20` build jobs, `8` held-out jobs, `7` student seed jobs, and `55` student remaining jobs.
> Use [big_data_experiment_in_conference_paper.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/big_data_experiment_in_conference_paper.md) as the current source of truth for the evaluation method.

This file is the content-first workspace for the conference paper.

Workflow rule:

- Draft and revise all section content here first.
- Keep `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/lab_tutor_conference_paper_working_template.docx` as the untouched backup copy of the official template.
- Move stable text into `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/lab_tutor_conference_paper_working.docx` only after the structure, claims, figures, and tables are locked.

Why this is the safer method:

- the official template contains embedded comments and fragile layout patterns for formulas, side-by-side figures, and table formatting
- the paper still needs section-level decisions about task ordering, evidence placement, and citation support
- Markdown is better for restructuring and drafting without damaging Word styles

Citation note for this draft:

- this Markdown draft uses both repository materials and externally supplied sources from the chat context
- some in-text citations are currently written as source-name placeholders for drafting speed
- they will be normalized into final APA 7 references before migration into the Word template

Source policy for the final paper:

- use peer-reviewed journal and conference papers as the default citation backbone
- use official statistical or institutional reports only for current macro indicators and labor statistics
- do not use vendor blogs, news articles, marketing pages, or generic commentary as final references

## Template Constraints

- Title: no more than 30 words
- Authors: maximum 5, corresponding author marked
- Abstract: 200-400 words
- Keywords: 3-8, separated by semicolons
- Long paper target: 6,000-8,000 words
- Figures + tables: no more than 8 total
- References: at least 10, APA 7th
- Maximum heading depth: third level only
- Body formatting must follow the Word template exactly

## Template-Aware Markdown Rules

Even though this file is only a drafting surface, the structure here should already obey the conference template.

- Keep the final paper in five top-level sections only:
  - Introduction
  - Related Work
  - Methodology
  - Results
  - Conclusion
- Keep heading depth to three levels maximum when writing actual prose.
- Plan for front matter in this order:
  - Title
  - optional subtitle
  - author line
  - affiliation line
  - corresponding-author line
  - abstract
  - keywords
- Plan for back matter in this order:
  - acknowledgement if needed
  - references
  - author short bio if required by submission workflow
- Every figure and table must be called out in the body text before or near where it appears.
- Table titles go above the table.
- Avoid overloading the paper with visuals just because we have them available.
- Treat Markdown headings and notes as a planning device only; final typography comes from the Word template.

## Paper Backbone

One-sentence story:

> Higher education lacks a scalable way to organize course knowledge, align it with textbooks and labor-market skills, and connect those gaps to learning resources; therefore, we propose a knowledge-graph-centric multi-agent framework and evaluate it through a Big Data course case study.

Three contribution claims:

1. A knowledge-graph-centric multi-agent framework for intelligent curriculum resource construction.
2. A unified alignment pipeline connecting transcript knowledge, textbook skills, market skills, and skill-linked learning resources.
3. A Big Data case study showing improved estimated curriculum-to-market alignment under curriculum enrichment.

Safe claim language:

- use `case study`, `small-sample held-out evaluation`, and `estimated curriculum-to-market alignment`
- do not claim employment outcomes or hiring success

## Working Reference Ledger

Use stable draft IDs in this Markdown file so every important claim can be traced before we convert the bibliography to APA 7.

Draft annotation rule:

- use inline markers such as `[REF-1]` or `[REF-2; REF-3]`
- these are drafting aids only
- later they will become normal author-year citations and final APA 7 references

### Sources Already Approved for Current Drafting

- `REF-1`
  - Eurostat. Employment rates of recent graduates.
  - URL: `https://ec.europa.eu/eurostat/statistics-explained/SEPDF/cache/44912.pdf`
  - Use for: recent tertiary graduate employment rates in the EU, definition notes, cross-country context

- `REF-2`
  - Federal Reserve Bank of New York. The labor market for recent college graduates.
  - URL: `https://www.newyorkfed.org/research/college-labor-market`
  - Use for: recent U.S. graduate unemployment and underemployment

- `REF-3`
  - International Labour Organization. Global Employment Trends for Youth 2024 executive summary.
  - URL: `https://www.ilo.org/sites/default/files/2024-08/GET_2024_ExecSum_EN_0.pdf`
  - Use for: global youth labor-market transition context

- `REF-4`
  - World Economic Forum. The Future of Jobs Report 2025, skills outlook.
  - URL: `https://www.weforum.org/publications/the-future-of-jobs-report-2025/in-full/3-skills-outlook/`
  - Use for: expected skill disruption and rising AI/data-related skill demand

- `REF-5`
  - OECD. Labour market mismatch and labour productivity.
  - URL: `https://www.oecd.org/en/publications/labour-market-mismatch-and-labour-productivity_5js1pzx1r2kb-en.html`
  - Use for: mismatch as an economic and productivity problem

- `REF-6`
  - Heliyon review on knowledge graph construction and application in education.
  - URL: `https://www.sciencedirect.com/science/article/pii/S2405844024014142`
  - Use for: educational knowledge-graph literature

- `REF-7`
  - Journal of Computer Science and Technology paper on constructing an educational knowledge graph linked to Wikipedia.
  - URL: `https://link.springer.com/article/10.1007/s11390-020-0328-2`
  - Use for: concrete educational KG system precedent

- `REF-8`
  - IJCAI 2024 survey on LLM-based multi-agent systems.
  - URL: `https://www.ijcai.org/proceedings/2024/0890.pdf`
  - Use for: multi-agent decomposition rationale

- `REF-9`
  - UNESCO guidance for generative AI in education and research.
  - URL: `https://www.unesco.org/en/articles/guidance-generative-ai-education-and-research`
  - Use for: governance, trust, and human oversight

- `REF-10`
  - Course-Skill Atlas, Scientific Data.
  - URL: `https://www.nature.com/articles/s41597-024-03931-8`
  - Use for: curriculum-to-skills linkage literature

- `REF-11`
  - PLOS ONE paper connecting higher education content to workplace activities and earnings.
  - URL: `https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0282323`
  - Use for: linking course content to labor-market ontologies

- `REF-12`
  - EDM 2020 paper on curriculum profile and job-market gap modeling.
  - URL: `https://educationaldatamining.org/files/conferences/EDM2020/papers/paper_59.pdf`
  - Use for: curriculum-to-job-market comparison methodology

- `REF-13`
  - Education and Information Technologies review on educational recommender systems.
  - URL: `https://link.springer.com/article/10.1007/s10639-022-11341-9`
  - Use for: educational recommendation literature

- `REF-14`
  - Systematic review of ontology use in e-learning recommender systems.
  - URL: `https://www.sciencedirect.com/science/article/pii/S2666920X22000029`
  - Use for: semantic recommendation and ontology-grounded learning support

## Section Outline

Use this top-level paper shape:

1. Introduction
2. Related Work
3. Methodology
4. Results
5. Conclusion

### 1. Introduction

Purpose:

- establish the curriculum-market mismatch problem
- explain fragmented teaching knowledge
- explain the manual cost of resource construction
- end with the main research question and contributions

Inputs:

- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/chatgpt_deep_research.md`
- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/Gemini_deep_research_on_the_project.md`
- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/teacher_proposed_paper framework-Roma.docx`

Target length:

- 700-900 words

### 2. Related Work

Cover only the categories needed to position the paper:

- knowledge graphs in education
- multi-agent educational systems
- curriculum-industry alignment
- intelligent resource recommendation

Target length:

- 600-800 words

### 3. Methodology

Subsections:

- 3.1 Framework Overview and Design Principles
- 3.2 Task 1: Document Extraction, Concept Structuring, and Embeddings
- 3.3 Task 2: Textbook Discovery and Curriculum Alignment
- 3.4 Task 3: Market-Demand Alignment
- 3.5 Task 4: Resource Curation and Student Learning Support
- 3.6 Human-AI Review and Quality Assurance
- 3.7 Big Data Case Study and Evaluation Design

Main figure:

- Figure 1: simplified three-layer framework and system overview

Target length:

- 1,900-2,300 words

Core technical sources:

- `/Users/khajievroma/Projects/lab_tutor/docs/agent_logic_current.md`
- `/Users/khajievroma/Projects/lab_tutor/docs/MARKET_DEMAND_ANALYST.md`
- `/Users/khajievroma/Projects/lab_tutor/docs/agent_descriptions_for_proposal.md`
- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/conference_paper_algorithm_drafts.md`

### 4. Results

Subsections:

- 4.1 Curriculum-to-Market Alignment by Variant
- 4.2 Skill-Gap Closure Analysis
- 4.3 Discussion and Limitations

Target length:

- 1,400-1,700 words

`4.3 Discussion and Limitations` must include:

- educational significance
- case-study scope
- small-sample held-out limitation
- student-case personalization limitation
- no employment-outcome claim

### 5. Conclusion

Purpose:

- restate the problem
- restate the framework
- restate the case-study outcome
- point to larger future evaluation and stronger student-facing deployment

Target length:

- 250-400 words

## Figure, Table, and Algorithm Plan

Use 7 visual assets total:

- 4 figures
- 3 tables

Recommended figures:

1. Figure 1: three-layer framework and simplified system overview
2. Figure 2: simplified system realization or agent ecology
3. Figure 3: variant-level alignment results
4. Figure 4: skill-gap closure results

Recommended tables:

1. Table 1: Big Data case study dataset summary
2. Table 2: main experimental results
3. Table 3: representative skill-gap closure examples

Recommended algorithms in the main paper:

1. Algorithm 1: textbook-side skill-bank construction
2. Algorithm 2: market-side skill-bank construction

Algorithm 3 should stay appendix-only unless the paper has unexpected extra space.

## Asset Decisions

Keep:

- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/experiment_result_1.png`
- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/experiment_result2.png`

Use only after simplification:

- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/system-architecture.png`
- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/database_schema.png`

Leave out of the main paper:

- `/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/UI_schreenshot_of_student_choosing_skills.png`

Reason:

- it is useful as application context, but it does not directly support the paper's main empirical claim

## Result Numbers Already Fixed

Current course-level metrics:

- `KG`: coverage `0.2961`, average job-fit `0.2775`
- `KG + B_S`: coverage `0.3398`, average job-fit `0.3179`
- `KG + J_S`: coverage `0.4806`, average job-fit `0.4602`
- `KG + B_S + J_S`: coverage `0.4757`, average job-fit `0.4568`

Current student-level metrics:

- `KG`: coverage `0.2608`, average job-fit `0.2588`
- `KG + B_S`: coverage `0.2671`, average job-fit `0.2646`
- `KG + J_S`: coverage `0.4196`, average job-fit `0.4259`
- `KG + B_S + J_S`: coverage `0.4266`, average job-fit `0.4333`

Experimental framing to preserve:

- `62` deduplicated raw jobs in the broad graph pool
- `28` strict-scope Big Data / Data Engineering jobs for the main benchmark
- `20` build jobs and `8` held-out jobs for the course-level table
- `7` student seed jobs and `55` remaining jobs for the personalized table
- the current run uses persisted job descriptions for evaluated jobs, so job skills are extracted from raw job text

## Writing Order

Draft in this sequence:

1. Introduction
2. Related Work
3. Methodology
4. Results
5. Conclusion
6. Abstract
7. Title and keywords

## Layout Preview

This is the intended paper layout before any prose is finalized.

### Front Matter

1. Title
2. Optional subtitle
3. Author names
4. Affiliations
5. Corresponding author note
6. Abstract
7. Keywords

### Main Body

1. Introduction
2. Related Work
3. Methodology
4. Results
5. Conclusion

### Back Matter

1. Acknowledgement if required
2. References
3. Author short bio if required

## Section-by-Section Blueprint

This is the section map we should review before writing full paragraphs.

### 1. Introduction Blueprint

Target role:

- explain why curriculum-market mismatch matters now
- define the three educational problems
- introduce Lab Tutor as the proposed answer
- end with research question and contributions

Suggested paragraph flow:

1. Macro context: skill change, graduate transition friction, and curriculum lag
2. Problem 1: fragmented course knowledge and weak semantic organization
3. Problem 2: slow curriculum response to labor-market change
4. Problem 3: high manual cost of textbook and resource construction
5. Proposed answer: knowledge-graph-centric multi-agent framework plus Big Data case study
6. Research question and three contributions

Evidence anchors:

- Eurostat
- New York Fed
- ILO
- WEF
- Lightcast
- Strada/Burning Glass

Hard constraints:

- do not claim employment outcomes
- do not over-explain implementation details here

### 2. Related Work Blueprint

Target role:

- position the paper against the nearest academic neighbors
- show the gap that our combined system addresses

Suggested subsection logic inside prose:

1. Knowledge graphs in education
2. Multi-agent or AI-supported educational systems
3. Curriculum-to-labor-market alignment
4. Educational recommender systems and semantic resource recommendation

What each part should do:

- summarize the strongest prior work
- identify what each line of work solves
- state what it does not yet combine

Gap to highlight:

- prior work usually covers only one or two of the following at a time:
  - educational knowledge graph construction
  - multi-agent orchestration
  - job-market alignment
  - skill-linked resource support
  - instructor-in-the-loop governance

### 3. Methodology Blueprint

Target role:

- explain the framework and the task-by-task system design
- show how the case-study evaluation is set up

Recommended internal structure:

#### 3.1 Framework Overview and Design Principles

Include:

- the three-layer framework
- why a knowledge graph is the common substrate
- why specialized agents are used
- why human review is retained

Figure placement:

- Figure 1 near this subsection

#### 3.2 Task 1: Document Extraction, Concept Structuring, and Embeddings

Include:

- teacher-uploaded files
- structured extraction
- concept evidence
- embeddings as retrieval substrate

#### 3.3 Task 2: Textbook Discovery and Curriculum Alignment

Include:

- query generation
- candidate discovery
- multi-criteria scoring
- teacher approval
- chapter-level skill extraction

Algorithm placement:

- Algorithm 1 can be introduced here

#### 3.4 Task 3: Market-Demand Alignment

Include:

- job discovery and filtering
- parallel skill extraction
- curriculum mapping
- concept linking
- teacher curation

Algorithm placement:

- Algorithm 2 can be introduced here

#### 3.5 Task 4: Resource Curation and Student Learning Support

Include:

- text and video support as downstream skill-linked application
- current implementation boundaries
- careful wording about student-learning-path emphasis

#### 3.6 Human-AI Review and Quality Assurance

Include:

- textbook approval
- skill curation
- concept review
- optional resource approval

#### 3.7 Big Data Case Study and Evaluation Design

Include:

- Big Data course context
- 62 deduplicated raw jobs in the broad graph pool
- 28 strict-scope main jobs, split into 20 build jobs and 8 held-out jobs
- 7 student seed jobs and 55 remaining jobs for the personalized case study
- four curriculum variants
- evaluation labels and metrics
- note that the latest run uses persisted job descriptions for skill extraction

Figure/table placements:

- Table 1 in this subsection

### 4. Results Blueprint

Target role:

- show the measured lift
- explain what improved
- name the limitations directly

Recommended internal structure:

#### 4.1 Curriculum-to-Market Alignment by Variant

Include:

- four variants
- main metric comparison
- main result numbers

Figure/table placements:

- Figure 3
- Table 2

#### 4.2 Skill-Gap Closure Analysis

Include:

- covered / partial / missing breakdown
- representative skill-gap closure examples

Figure/table placements:

- Figure 4
- Table 3

#### 4.3 Discussion and Limitations

Include:

- why market enrichment explains most of the lift
- why books still add complementary value
- why the result matters educationally
- why this remains a small-sample case study
- why the held-out design is still limited
- why we must avoid employment claims

### 5. Conclusion Blueprint

Target role:

- close tightly and safely

Suggested paragraph flow:

1. Restate the problem and framework
2. Restate the case-study result with safe wording
3. Point to future work on larger evaluations and stronger deployment

## Draft Workspace

### Title

Template notes:

- no more than 30 words
- should foreground the framework, not the engineering stack

Working title direction:

- A Knowledge Graph-Centric Multi-Agent Framework for Intelligent Curriculum Resource Construction and Curriculum-Market Alignment

Recommended title:

**A Knowledge Graph-Centric Multi-Agent Framework for Curriculum-Market Alignment and Learning Resource Construction**

Backup title options:

1. **Lab Tutor: A Knowledge Graph-Centric Multi-Agent Framework for Curriculum-Market Alignment**
2. **A Knowledge Graph-Centric Multi-Agent Framework for Intelligent Curriculum Resource Construction**
3. **A Multi-Agent Knowledge Graph Framework for Curriculum-Market Alignment in Higher Education**

### Abstract

Template notes:

- 200-400 words
- should contain problem, method, case study, and main result
- should not read like implementation notes

Abstract checklist:

- sentence 1-2: educational problem
- sentence 3-4: proposed framework
- sentence 5-6: Big Data case study and evaluation setup
- sentence 7-8: key result with safe wording
- sentence 9: significance and future direction

Draft abstract:

Higher education courses increasingly face three linked challenges: teaching knowledge is fragmented across heterogeneous course materials, curricula evolve more slowly than labor-market skill demands, and the manual construction of supporting resources imposes substantial burden on instructors. To address these issues, we propose Lab Tutor, a knowledge-graph-centric multi-agent framework for intelligent curriculum resource construction and curriculum-market alignment. The framework organizes teacher-provided materials into a course knowledge graph, enriches that graph through textbook discovery and chapter-level skill extraction, aligns curriculum content with market-demand skills derived from job postings, and links identified skills to downstream learning resources under human-in-the-loop review checkpoints. We evaluate the framework through a Big Data course case study using two complementary analyses built on the same four curriculum variants: `KG`, `KG + B_S`, `KG + J_S`, and `KG + B_S + J_S`. In the course-level held-out benchmark, the strongest variant (`KG + J_S`) improved demand-weighted skill coverage from `0.2961` to `0.4806` and average job-fit from `0.2775` to `0.4602` across `8` held-out jobs drawn from `28` strict-scope Big Data roles. In a student-centered spillover analysis, skills extracted from `7` student-selected target job postings improved average job-fit on the other `55` jobs from `0.2588` to `0.4259`, while the fully personalized variant reached `0.4333`. These findings suggest that a knowledge-graph-centric multi-agent workflow can improve estimated curriculum-to-market alignment and can also help explain how skills learned for a small target job portfolio transfer to adjacent opportunities, while preserving instructor oversight at critical decision points.

### 1. Introduction

Writing checklist:

- open with the curriculum-market gap, not the tools
- define fragmentation, lag, and manual cost
- connect the problem to Big Data / technical curricula only after the broad framing
- end with research question and 3 contributions

Higher education is under growing pressure to demonstrate that university learning still translates into timely, degree-relevant employment. Aggregate graduate employment indicators remain relatively strong in some regions, yet the transition from study to stable professional work has become increasingly fragile and uneven. Eurostat reports that the employment rate for recent tertiary graduates in the European Union reached 86.7% in 2024, but this favorable aggregate masks cross-country dispersion and does not eliminate mismatch between what programs teach and what employers require. In the United States, the picture is sharper for early-career graduates: the Federal Reserve Bank of New York reported unemployment of about 5.7% and underemployment of 42.5% for recent college graduates in 2025:Q4. More broadly, international labor statistics continue to show that smoother education-to-work transitions cannot be taken for granted even when top-line employment remains comparatively strong. Together, these trends suggest that the higher-education challenge is no longer only access to education, but also the quality and timeliness of the education-to-work alignment it produces [REF-1; REF-2; REF-3].

At the same time, the labor market is changing faster than conventional curriculum revision cycles. The World Economic Forum reports that employers expect 39% of workers' core skills to change by 2030, while AI, big data, and cybersecurity remain among the fastest-growing capability areas. OECD research further shows that skill and qualification mismatch is associated with lower productivity, reinforcing that misalignment is not only an educational issue but also an economic one. For universities, this means that curricula updated on multi-year governance cycles can drift out of sync with the skills landscape during the lifetime of a single student cohort [REF-4; REF-5].

This pressure exposes three linked problems in current course design and resource construction. First, teaching knowledge is fragmented. Course content is distributed across lecture notes, transcripts, slides, books, and other files that are difficult to search, compare, and reorganize semantically. Second, curriculum-market alignment is weak because program revision often depends on lagging indicators such as retrospective feedback, faculty intuition, or infrequent external consultation rather than continuously updated labor signals. Third, teaching-resource construction remains expensive and labor-intensive. Instructors must identify suitable books, determine what additional skills deserve coverage, and curate external resources manually, all while the underlying skill landscape continues to move. These three problems are tightly coupled: fragmented knowledge makes alignment harder, weak alignment increases the need for new materials, and manual resource construction scales poorly as knowledge changes faster.

To address these challenges, we propose Lab Tutor, a knowledge-graph-centric multi-agent framework for intelligent curriculum resource construction. The framework uses a course knowledge graph as the common semantic substrate for organizing teacher-provided materials, aligning them with textbook and labor-market skills, and linking the resulting skills to downstream learning resources. Rather than treating documents, books, jobs, and resources as separate silos, Lab Tutor models them as interoperable entities connected through explicit relations among course chapters, concepts, skills, job postings, and recommended resources. The system is organized as a three-layer workflow: a knowledge foundation layer that extracts and structures course content, a knowledge alignment layer that integrates textbook and market-demand evidence, and a resource application layer that supports skill-linked learning pathways. Because educational use requires trust and traceability, the workflow retains human review checkpoints at critical decisions such as textbook approval, skill curation, and concept review [REF-9].

We evaluate the framework through a Big Data course case study. Starting from transcript-derived course knowledge, we compare four curriculum variants: transcript knowledge only (`KG`), transcript knowledge plus textbook skills (`KG + B_S`), transcript knowledge plus market skills (`KG + J_S`), and the fully enriched variant (`KG + B_S + J_S`). The evaluation is intentionally framed as a curriculum-to-market alignment study rather than an employment-outcome study. It asks whether curriculum enrichment reduces the skill gap between a university course and relevant job requirements on a small held-out subset of Big Data-related jobs.

The central research question of this paper is: how can a knowledge-graph-centric multi-agent system organize fragmented course knowledge, align it with textbooks and labor-market skills, and support resource construction under human oversight? This paper makes three contributions. First, it proposes a knowledge-graph-centric multi-agent framework for intelligent curriculum resource construction. Second, it presents a unified alignment pipeline connecting transcript knowledge, textbook skills, market skills, and skill-linked learning resources. Third, it reports a Big Data case study showing that curriculum enrichment improves estimated curriculum-to-market alignment under a small-sample held-out evaluation.

### 2. Related Work

Writing checklist:

- organize by literature theme, not by source list
- compare our system to closest neighbors
- end with the gap our paper addresses

Research on knowledge graphs in education provides an important foundation for our work because it addresses the problem of fragmented educational content through structured semantic representation. Recent review literature argues that knowledge graphs are increasingly used in education for concept organization, learning support, curriculum analysis, and recommendation tasks [Heliyon review, 2024; IEEE Access survey on knowledge graphs in education and employability]. System-oriented studies such as KnowEdu, CourseKG, and work on educational knowledge graphs linked to Wikipedia show that heterogeneous educational artifacts can be normalized into entities and relations suitable for retrieval, analytics, and downstream applications. These studies support the core premise that curriculum knowledge should not remain trapped inside disconnected files. At the same time, most prior educational knowledge-graph systems emphasize graph construction, recommendation, or concept linking in isolation. They do not usually combine course-graph construction with textbook selection, labor-market alignment, and instructor-governed resource generation inside one end-to-end workflow.

The second relevant line of work concerns AI-supported and multi-agent educational systems. Earlier conversational intelligent tutoring research already argued that multiple agents can be useful when educational tasks require distinct roles such as explanation, reflection, assessment, and dialogue management. More recent work on LLM-based multi-agent systems generalizes this argument by showing that specialized agents can improve decomposition, coordination, and controllability for complex tasks [IJCAI survey on LLM-based multi-agent systems, 2024]. Education-specific examples now include multi-agent tutoring, automated grading, and Socratic dialogue generation, while UNESCO guidance and human-in-the-loop reviews emphasize the need for governance, transparency, and human oversight in educational deployments [GenMentor; EvaAI; UNESCO, 2023]. This literature supports the architectural logic behind using specialized agents rather than one monolithic model. However, most of these systems focus on tutoring, grading, or instructional interaction. They do not directly target curriculum-market alignment or the construction of skill-linked educational resource pipelines.

The third literature group focuses on curriculum-labor-market alignment. Here, recent work has started to make curriculum analysis more computable by linking course artifacts to explicit skills, job activities, and labor-market taxonomies. Course-Skill Atlas provides a large-scale dataset for inferring skills from course syllabi, while a PLOS ONE study connecting higher education content to workplace activities and earnings shows that curriculum artifacts can be mapped to external labor ontologies in a systematic way [Course-Skill Atlas, Scientific Data, 2024; PLOS ONE, 2023]. Work in educational data mining has also modeled curriculum profiles against job-market needs in data-intensive fields, demonstrating that the curriculum-job gap can be studied as an empirical comparison rather than only a qualitative concern [EDM 2020 curriculum profile]. Tools aligned with ESCO and similar skill taxonomies further support transparent mapping from text to skill and occupation structures. This literature is especially close to our problem setting. Still, it often concentrates on static analysis, large-scale measurement, or taxonomy linkage rather than a teacher-facing system that both diagnoses alignment gaps and connects them to enrichment and resource-construction actions.

The fourth relevant area is educational recommendation and personalized support. Educational recommender systems have a substantial research history, and recent reviews emphasize both their practical value and their dependence on high-quality semantic representations [Education and Information Technologies review, 2022]. More specialized work on ontology-based and knowledge-graph-based recommendation in e-learning argues that semantic models improve contextual relevance, resource matching, and learning-path generation [systematic review of ontology use in e-learning recommenders, 2022; ACM knowledge-graph recommendation framework for personalized e-learning]. This literature aligns with our resource application layer, particularly the idea that a recommendation is stronger when it is grounded in concepts and skills rather than in isolated keyword matching. However, most recommendation systems start from learners and resources, whereas our pipeline starts earlier by building and aligning the course graph itself before resource support is generated.

Taken together, prior work establishes five important ideas: educational knowledge graphs are a viable substrate for structured learning content; multi-agent systems are useful when educational workflows require decomposable roles; curriculum-market alignment can be studied through skills and labor data; semantic recommenders can support personalized resource selection; and human oversight remains important when AI is used in high-stakes educational settings. What remains less common in prior literature is the combination of all five elements inside a single teacher-centered pipeline. Lab Tutor is positioned in that gap: it combines course knowledge-graph construction, textbook and labor-market alignment, resource linkage, and human-in-the-loop governance inside one integrated framework, then evaluates that framework through a focused curriculum-to-market case study.

### 3. Methodology

Writing checklist:

- keep it task-by-task
- describe architecture at a research-method level, not as a repo walkthrough
- place Figure 1, Algorithm 1, Algorithm 2, and Table 1 deliberately
- keep student-resource support realistic to the current implementation

#### 3.1 Framework Overview and Design Principles

Lab Tutor is designed as a knowledge-graph-centric multi-agent framework for intelligent curriculum resource construction. The core design decision is to treat the course knowledge graph as the shared semantic substrate through which all downstream tasks communicate. Instead of allowing textbooks, labor-market evidence, and resource recommendations to remain detached from course materials, the system represents them through explicit entities and relations centered on course chapters, concepts, and skills. This choice directly addresses the fragmentation problem described in the Introduction: if course knowledge is stored only in files, it is difficult to align, query, and extend; if it is stored as a graph, later agents can attach evidence, detect gaps, and surface targeted support.

The framework is organized into three layers. The knowledge foundation layer transforms teacher-provided files into a transcript-grounded curriculum graph. The knowledge alignment layer enriches that graph from two directions: textbooks and labor-market skill demand. The resource application layer uses the resulting skill banks to support downstream reading and video recommendations. Figure 1 should be placed near this subsection to present the three-layer model and the high-level system flow. A second design principle is role decomposition. Each major task is handled by a specialized workflow or agent group rather than by a single undifferentiated model call. A third design principle is human governance. Because textbook adoption, skill insertion, and concept normalization all have curricular consequences, the system intentionally pauses for instructor approval at key points rather than fully automating these decisions.

#### 3.2 Task 1: Document Extraction, Concept Structuring, and Embeddings

The first task constructs the transcript-grounded course knowledge base. Teacher-uploaded materials are parsed and passed through structured extraction to identify document topics, summaries, keywords, and explicit concepts. Each extracted concept carries semantic provenance, including a normalized name, definition-like description, and textual evidence from the source material. The extracted information is written into the graph as teacher-uploaded documents and concept mentions, creating a traceable record of which concepts originate from which course artifacts.

This stage is important for two reasons. First, it converts passive instructional files into a queryable curriculum memory. Second, it establishes the anchor against which later textbook and market skills are aligned. After extraction, embeddings are generated for both documents and concept mentions, creating a semantic retrieval substrate that later workflows can use for comparison, search, and evidence grounding. In practical terms, the output of Task 1 is not yet a market-aware curriculum; it is the teacher-owned baseline representation of what the course currently teaches.

#### 3.3 Task 2: Textbook Discovery and Curriculum Alignment

The second task is implemented by the Curricular Alignment Architect, which builds the book-side skill bank. The workflow begins by generating a diverse set of textbook-oriented search queries from the course context, then searching external sources such as Google Books and Tavily in parallel. Candidate books are deduplicated and scored through a multi-criteria reasoning process that considers topic relevance, structural alignment, scope, freshness, author or publisher quality, and practical usefulness. The workflow then pauses for teacher review so that only instructor-approved books continue into the extraction pipeline.

After book selection, the system resolves PDF acquisition, extracts chapter structure, and performs chapter-level analysis. The important distinction here is that raw PDF extraction and chunking are not themselves the final book-skill output. The book-side skill vocabulary is created in the agentic chapter-extraction stage, where individual chapters are analyzed in parallel to produce chapter summaries, practical skills, and prerequisite concepts. These outputs are written into the graph as `BOOK_SKILL` nodes and `REQUIRES_CONCEPT` relations. A separate mapping flow then aligns extracted `BOOK_SKILL` nodes to the teacher-created course chapter scaffold. Algorithm 1 should be introduced in this subsection because it captures the main logic of book-skill-bank construction more clearly than a long prose-only description.

#### 3.4 Task 3: Market-Demand Alignment

The third task is the Market Demand Analyst, which builds the market-side skill bank and serves as the main evaluated layer in the case study. The current implementation uses a coordinated multi-agent workflow centered on supervisory orchestration, curriculum mapping, and concept linking, together with parallel skill extraction. The process begins with job discovery from relevant search terms and external job platforms. Job postings are deduplicated and grouped so that the instructor can retain only roles genuinely relevant to the target curriculum. This human filtering step is important because curriculum alignment is meaningful only if the selected jobs correspond to the course domain rather than to a broad or noisy market sample.

Once a relevant job subset is selected, job descriptions are processed in parallel to extract concrete market skills. The resulting skills are aggregated, cleaned, frequency-scored, and mapped against the curriculum graph. For each candidate skill, the workflow determines whether the skill is already covered, partially covered, or better treated as a new topic need. Later stages remove redundancies relative to existing curriculum content and link retained skills to prerequisite concepts before inserting them as `MARKET_SKILL` nodes in the graph. This stage is what turns labor-market evidence into curriculum-relevant diagnostic output rather than a raw list of job terms. Algorithm 2 should be introduced here because it formalizes the market-skill-bank construction pipeline and clarifies the roles of extraction, mapping, curation, and concept linking.

#### 3.5 Task 4: Resource Curation and Student Learning Support

The fourth task connects aligned skills to downstream support resources. In Lab Tutor, this is implemented through textual and video-oriented resource discovery workflows that build context from the graph. For each selected skill, the system can construct a skill profile using related concepts, chapter context, and course level, then generate targeted queries for readings and videos. Candidate resources are collected from external sources, filtered semantically, and ranked using criteria such as relevance, pedagogical quality, depth, and source credibility.

It is important to describe this layer carefully. In the current implementation, readings and videos are primarily generated through the student learning-path pipeline rather than as a fully mature teacher-side planning interface. For the paper, this means the resource application layer should be presented as an implemented downstream use of the aligned skill banks, not as a claim that all teacher-facing resource workflows are already complete. This wording keeps the paper technically honest while still showing how the framework closes the loop from "what should be learned" to "how it may be learned."

#### 3.6 Human-AI Review and Quality Assurance

Human review is not an auxiliary feature in Lab Tutor; it is one of the framework's methodological commitments. In the textbook workflow, teachers review ranked candidate books before adoption and can intervene when automatic retrieval fails or yields weak results. In the market-demand workflow, teachers help constrain job relevance, curate skill sets, and determine which skills should be retained for insertion. Concept-level review is also preserved where merge or linkage decisions may affect curriculum interpretation. Optional review can further be applied to downstream resource recommendations before they are treated as finalized support materials.

This design aligns with current educational AI governance guidance, which argues that trust, interpretability, and accountability are especially important in teaching and curriculum applications [UNESCO, 2023; human-in-the-loop review in AI in education]. Methodologically, these review points also reduce the risk that the final system output reflects only model fluency rather than curricular judgment.

#### 3.7 Big Data Case Study and Evaluation Design

We evaluate the framework through a Big Data course case study and frame the evaluation as a curriculum-to-market alignment study. The baseline curriculum representation, `KG`, is built from transcript-derived course knowledge and the teacher-owned chapter scaffold. We then construct three enriched variants: `KG + B_S`, which adds textbook-derived skills; `KG + J_S`, which adds market-derived skills; and `KG + B_S + J_S`, which combines both enrichment sources. This four-variant setup functions as an ablation-style comparison that lets us observe the relative contribution of different enrichment paths.

[Insert Table 1 near here: Big Data case study dataset summary.]

The current artifact operates over `62` deduplicated job postings in the broad graph pool. For the course-level benchmark, the notebook applies a strict Big Data / Data Engineering relevance filter, yielding `28` main-benchmark jobs. These are split into `20` build jobs and `8` held-out jobs using a deterministic seeded procedure. For the personalized case study, `7` job postings explicitly selected by `STUDENT(id=2)` form the seed portfolio, and the remaining `55` jobs are used to measure spillover beyond the student's original targets.

The evaluation uses persisted job descriptions for the current run, so job skills are extracted from raw job text rather than from graph-linked proxy skills. Each skill instance is then judged as `covered`, `partial`, or `missing` relative to a curriculum variant, and these labels are mapped to numeric values of `1.0`, `0.5`, and `0.0`, respectively. From these judgments we compute demand-weighted skill coverage and average job-fit score, with threshold-based success rates used only as secondary indicators. The course-level table is therefore a held-out benchmark, whereas the student table is a personalized scenario analysis based on the transfer value of the student's `7` selected target jobs.

### 4. Results

Writing checklist:

- lead with the main ablation result
- use exact numbers already fixed in the plan
- include limitations in the final subsection
- keep claims at the alignment level only

#### 4.1 Curriculum-to-Market Alignment by Variant

The course-level held-out benchmark shows a consistent pattern: curriculum enrichment improves estimated alignment relative to the course-only baseline, and market-skill enrichment explains most of the measurable lift. The baseline `KG` variant achieved a demand-weighted skill coverage of `0.2961` and an average job-fit score of `0.2775` across `8` held-out jobs. Adding textbook-derived skills alone raised coverage to `0.3398` and average job-fit to `0.3179`. Adding market-derived skills produced the strongest held-out result, increasing coverage to `0.4806` and average job-fit to `0.4602`, while also yielding the only `>= 0.80` success in the held-out set (`1/8`). The full variant, `KG + B_S + J_S`, remained far above the baseline at `0.4757` coverage and `0.4568` average job-fit, although it did not surpass `KG + J_S` on this particular split.

[Insert Figure 3 near here: Market Alignment Improves as Curriculum Enrichment Increases.]
[Insert Table 2 near here: Main experimental results.]

These results support two immediate observations. First, transcript-derived course knowledge alone does not provide strong coverage of the evaluated market-skill requirements in the held-out set. Second, textbook enrichment and market enrichment are not interchangeable. Textbook enrichment adds modest gains relative to the baseline, but market enrichment produces the dominant improvement because it injects missing skill demand that is not strongly represented in the original course materials. The combined variant still outperforms `KG + J_S`, which suggests that textbook-derived disciplinary depth and market-derived labor relevance contribute in complementary ways.

#### 4.2 Skill-Gap Closure Analysis

The stacked-bar analysis shows how the improvement occurs. In the transcript-only baseline, 58% of evaluated market-skill instances remained missing and 42% were only partially covered, with no fully covered instances. Adding textbook-derived skills reduced the missing share to 46% and increased partial coverage to 54%, indicating that textbook supplementation helps narrow the gap but does not fundamentally close it. The strongest shift appears when market-derived skills are introduced: the `KG + J_S` variant reduced the missing share to 19% and increased partial coverage to 81%. The fully enriched variant retained the 19% missing share while introducing a small fully covered portion of 4%, with 77% partial coverage.

[Insert Figure 4 near here: Skill Gap Closes as Enrichment Adds Missing Market Competencies.]
[Insert Table 3 near here: Representative skill-gap closure examples.]

This pattern is substantively important. The main effect of enrichment in the current artifact is not a dramatic jump from missing directly to fully covered across the board. Instead, enrichment first transforms missing skills into partially supported skills by connecting them to new curricular evidence, prerequisite concepts, and aligned skill nodes. Given the small-sample held-out design, this gradual movement from missing to partial should be interpreted as meaningful evidence of gap reduction rather than as proof of complete curricular sufficiency.

#### 4.3 Discussion and Limitations

From an educational perspective, the results suggest that alignment-aware curriculum enrichment can make hidden curriculum gaps more visible and more actionable. The transcript-only baseline reflects what the teacher-provided materials already express in the graph. The textbook-enriched variant adds disciplinary depth, chapter-level practical skills, and prerequisite structure. The market-enriched variant contributes the strongest observed lift in the course-level held-out benchmark because it directly injects labor-demand signals into the curriculum representation. In the student-centered table, the fully personalized variant performs best overall, which supports the idea that course design and student planning both benefit from combining internal academic structure with external demand evidence.

At the same time, the case study should be interpreted with appropriate caution. First, the evaluation is a focused Big Data case study rather than a multi-course benchmark. Second, the course-level held-out set contains only `8` jobs, so the benchmark remains small. Third, the student table is a personalized scenario analysis, not a held-out benchmark, because it intentionally asks how the skills from `7` target job postings can be applied to `55` other jobs. Fourth, the evaluation measures estimated curriculum-to-market alignment rather than real employment outcomes. It is therefore appropriate to claim improved visibility into skill gaps and improved estimated alignment, but not employability gains, hiring success, or causal labor-market impact on students.

These limitations also clarify the paper's future-work agenda. A stronger next step would be a larger held-out corpus with stored job descriptions, together with additional baselines and expert evaluation of the coverage judgments. Even with those limitations, however, the present case study is still useful: it shows that the framework can convert fragmented course materials, textbooks, and market evidence into a shared representation from which alignment differences across curriculum variants can be measured.

### 5. Conclusion

Writing checklist:

- short
- no new evidence
- no inflated impact language

This paper presented Lab Tutor, a knowledge-graph-centric multi-agent framework for intelligent curriculum resource construction and curriculum-market alignment. The framework addresses three linked problems in higher education: fragmented course knowledge, slow response to labor-market change, and the high manual cost of building and updating instructional support materials. By organizing teacher-provided materials into a course knowledge graph, enriching that graph with textbook and market-derived skills, and linking aligned skills to downstream learning resources under instructor review, the framework provides a structured pathway from curriculum representation to actionable curriculum support.

The Big Data case study shows that curriculum enrichment improves estimated curriculum-to-market alignment relative to a transcript-only baseline. In the current small-sample held-out evaluation, the fully enriched variant achieved the strongest overall performance, with market-derived skills contributing most of the observed lift and textbook-derived skills providing additional complementary gains. These findings do not demonstrate employment outcomes, but they do show that a knowledge-graph-centric multi-agent workflow can expose and reduce curriculum-market skill gaps in a measurable way.

Future work should strengthen the evidence base through larger held-out evaluations, richer job-text persistence, and broader multi-course validation. It should also continue improving the resource application layer so that alignment diagnostics and learning support become more tightly connected in practical educational use.
