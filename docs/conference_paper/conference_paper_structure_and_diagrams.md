# Conference Paper Structure and Diagram Plan

> Update note (2026-03-31): the notebook now uses a two-table evaluation design and the latest artifact is already available.
> Treat [big_data_experiment_in_conference_paper.md](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/big_data_experiment_in_conference_paper.md) as the current source of truth for experiment wording, variant definitions, and table structure.
> The current evaluation snapshot is: `62` deduplicated raw jobs, `28` strict-scope main jobs, `20` build jobs, `8` held-out jobs, `7` student seed jobs, and `55` student remaining jobs.

This note combines three inputs:

- the official conference template
- your teacher's proposed paper framework
- the actual Lab Tutor codebase and current experimental artifacts

The goal is to decide how the conference paper should be structured and which diagrams should be included.

## 1. What the Conference Template Requires

From [教育技术协会 英文论文模板 2026.docx](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/%E6%95%99%E8%82%B2%E6%8A%80%E6%9C%AF%E5%8D%8F%E4%BC%9A%20%E8%8B%B1%E6%96%87%E8%AE%BA%E6%96%87%E6%A8%A1%E6%9D%BF%202026.docx), the most important requirements are:

- title should generally be no more than 30 words
- subtitle is optional
- maximum 5 authors
- corresponding author should be clearly marked
- abstract should be `200-400` words
- keywords should be `3-8`, separated by semicolons
- long paper length should be `6,000-8,000` words
- total number of **figures + tables** should not exceed `8`
- no less than `10` references
- references and citations should follow `APA 7th`
- only up to **third-level headings**

Formatting comments that matter while writing:

- first-level heading: bold, title case
- second-level heading: bold, title case
- third-level heading: bold italic, title case
- body text should be Times New Roman
- abbreviations must be defined before use
- single-letter variables should be explained when first used
- table number and title go above the table
- tables should be referenced in the main text
- no blank line is needed before text following figures or tables

Practical implication:

You should write a paper with a **clear architecture and a compact set of results**, not a paper overloaded with many diagnostic plots.

## 2. What Your Teacher Wants

From [teacher_proposed_paper framework-Roma.docx](/Users/khajievroma/Projects/lab_tutor/docs/conference_paper/teacher_proposed_paper%20framework-Roma.docx), your teacher is clearly asking for a paper that emphasizes:

- a strong educational problem statement
- a knowledge-graph-centric multi-agent framework
- textbook support
- industry skill alignment
- resource recommendation for students
- human-AI collaborative quality control

The teacher's key research questions are essentially:

1. What is the recent development of course content?
2. What are the best textbooks to support it?
3. What industry skills are needed for the course?
4. If new skills are added, how can students learn them?

This means she wants the paper to feel like a **framework paper with an educational mission**, not just a technical experiment report.

## 3. What the Codebase Actually Supports Well

Based on the current codebase and docs, the strongest technically supported story is:

- teacher files and transcripts are processed into a course knowledge graph
- textbook skills can be extracted and aligned to course chapters
- market-demand skills can be extracted from job postings and aligned to the course graph
- resources can be curated as downstream support
- human review exists at important checkpoints

The strongest implemented components in the repo are:

- transcript-derived curriculum backbone
- market-demand analysis and curriculum-market mapping
- multi-agent architecture
- knowledge graph centric data model

The most convincing empirical evidence currently available is:

- the Big Data course case study
- the four course-level curriculum variants
- the four student-level personalized variants
- the latest dual evaluation artifact with a held-out course benchmark and a student spillover case study

Important correction:

> The latest artifact should be described as a **two-table evaluation**. The main benchmark uses `28` strict-scope Big Data / Data Engineering jobs split into `20` build jobs and `8` held-out jobs. The personalized case study uses `7` student seed jobs and evaluates spillover over the remaining `55` broad-market jobs. The evaluated jobs in the latest run use persisted job descriptions, so the notebook extracts job skills from raw job text rather than relying on graph-linked proxy skills as the primary path.

So the paper should not try to prove everything equally. It should use the **Big Data alignment experiment** as the main proof point.

## 4. Recommended Overall Paper Strategy

The paper should be written as:

- a **framework and system paper**
- with one **focused empirical case study**

Best balance:

- `45%` framework and research motivation
- `25%` actual system realization
- `30%` experiment and results

This balance matches:

- the teacher's preference for conceptual structure
- the conference's preference for a clear contribution
- the codebase's strongest implemented capabilities

## 5. Recommended Final Paper Structure

Because the template only supports up to third-level headings, keep the structure clean.

## Title

Recommended title direction:

> A Knowledge Graph-Centric Multi-Agent Framework for Intelligent Curriculum Resource Construction and Curriculum-Market Alignment

Shorter alternative:

> A Knowledge Graph-Centric Multi-Agent Framework for Intelligent Curriculum and Resource Alignment

## Abstract

The abstract should contain 4 things:

- the educational problem
- the proposed framework
- the Big Data case-study evaluation
- the main result in safe wording

Do not use the abstract to explain implementation details.

## 1. Introduction

Purpose:

- introduce the curriculum-market gap problem
- explain fragmentation of educational resources
- explain the cost of manual curriculum resource construction
- present your system as the proposed answer

End this section with 3 contributions.

Recommended contribution structure:

1. A knowledge-graph-centric multi-agent framework for intelligent curriculum resource construction
2. A unified alignment pipeline connecting transcripts, textbooks, market skills, and resources
3. A Big Data course case study showing improved curriculum-to-market alignment under curriculum enrichment

## 2. Related Work

Keep this section short and grouped into 3-4 categories:

- knowledge graphs in education
- multi-agent or AI-assisted educational systems
- curriculum-industry alignment
- educational resource recommendation

Do not turn this into a long survey section.

## 3. Theoretical Foundations and Framework

This section should closely follow your teacher's preference.

### 3.1 Theoretical Foundations

Include:

- Knowledge Graph Theory
- Multi-Agent Coordination Theory
- Human-AI Collaborative Cognition Theory

Keep each one brief and directly tied to your system design.

### 3.2 Three-Layer Framework

Include the three layers:

- Knowledge Foundation Layer
- Knowledge Alignment Layer
- Resource Application Layer

This is the best place for the main architecture diagram.

## 4. System Realization

This section translates the framework into the actual system.

Recommended subsections:

### 4.1 Knowledge Foundation Layer Realization

- transcript processing
- concept extraction
- concept normalization
- course chapter graph construction

### 4.2 Knowledge Alignment Layer Realization

- textbook discovery and evaluation
- textbook-skill extraction
- market skill extraction
- curriculum-market mapping

### 4.3 Resource Application Layer Realization

- resource curation
- skill-linked learning support
- personalized recommendation direction

### 4.4 Human-AI Review Mechanisms

- textbook approval
- concept-merge review
- skill coverage review
- optional resource review

This section should be technical enough to be credible, but not too code-heavy.

## 5. Case Study and Experimental Design

This is where the Big Data experiment should appear.

Recommended subsections:

### 5.1 Big Data Course and Data Sources

Include:

- course identity
- transcript documents
- filtered strict-scope job postings
- broad-market job pool for the student case study
- raw / retained / dropped counts
- build / held-out split
- student seed / remaining split
- a note that the latest artifact uses persisted job descriptions for evaluated jobs

### 5.2 Curriculum Variants

Include:

- `KG`
- `KG + B_S`
- `KG + J_S`
- `KG + B_S + J_S`

### 5.3 Job Skill Extraction and Coverage Judgment

Explain:

- competency extraction from job postings
- comparison against curriculum variants
- `covered / partial / missing`

### 5.4 Evaluation Metrics

Include:

- demand-weighted skill coverage
- average job-fit score
- optional job-fit success rate at `0.60`
- answerable rate for retrieved learning materials
- answerable rate by modality: `readings`, `videos`, `combined`
- answerable rate by question difficulty: `easy`, `medium`, `hard`

## 6. Results

This section should be compact and visually clean.

Recommended subsections:

### 6.1 Curriculum-to-Market Alignment Summary

Use a compact results table, not a figure.

### 6.2 Resource Answerability of Retrieved Learning Materials

Use the single main figure plus a compact results table.

### 6.3 Interpretation

Explain:

- what transcript-only curriculum covers
- what books add
- what market skills add
- why retrieved readings currently outperform videos
- why answerability drops sharply for harder questions
- why book-derived skills are better supported than market-derived skills

## 7. Discussion and Limitations

This section is very important for reviewer trust.

Include:

- educational significance
- why the result matters for curriculum improvement
- that this is a case study, not a universal benchmark
- that the experiment measures estimated curriculum-to-market alignment, not actual employment outcomes
- that the course-level held-out set is still small
- that the student table is a personalized scenario analysis rather than a held-out benchmark
- that the answerability experiment uses a blind LLM judge as a proxy for resource sufficiency rather than a direct human learning assessment

## 8. Conclusion

Keep it short:

- restate the problem
- restate the framework
- restate the Big Data case-study result
- mention future work

## 6. Recommended Figure and Table Budget

Because the template caps total figures + tables at `8`, you should plan carefully.

Recommended total:

- `1` figure
- `3` tables
- total = `4`

This stays well within the template and matches the decision to keep only one diagram.

## 7. Recommended Diagrams

These are the diagrams that make the most sense given the template, the teacher's framework, and the codebase.

## Figure 1. Answerable Questions by Difficulty and Modality

Purpose:

- show, in one glance, whether the retrieved readings and videos actually contain enough information to answer the generated questions
- make the paper's student-support claim concrete

What it should show:

- x-axis: `easy`, `medium`, `hard`
- y-axis: answerable rate
- grouped bars: `readings`, `videos`, `combined`

Recommended contents:

- the current notebook results from the Big Data case study
- easy combined: `44.3%`
- medium combined: `31.1%`
- hard combined: `6.6%`
- readings consistently above videos across all difficulty levels

Best source asset to adapt:

- the grouped bar chart exported from [resource_answerability_llm_judge.ipynb](/Users/khajievroma/Projects/lab_tutor/backend/app/modules/student_learning_path/notebooks/resource_answerability_llm_judge.ipynb)

This should be the only figure in the paper.

Why this is the best single figure:

- it is more legible than a framework or architecture diagram
- it directly supports the strongest end-to-end educational claim
- the alignment ablation can remain in a table without losing the core comparison
- it shows the main weakness clearly: hard questions and videos remain under-supported

## 8. Diagrams You Should Not Put in the Main Paper

Do not include these in the main results section:

- three-layer framework diagram
- system or agent-ecology diagram
- chapter-by-variant inventory heatmap
- job search-term histogram
- curriculum source composition bar chart
- chapter-linked missing-skills network
- highly detailed internal workflow graph

Reason:

- they explain internal mechanics
- they are useful for debugging
- they do not directly prove the paper's main claim

If needed, they can go to an appendix or supplementary material.

## 9. Recommended Tables

## Table 1. Case Study Dataset Summary

Suggested columns:

- course
- transcript documents
- course chapters
- raw job postings
- retained job postings
- dropped job postings
- build jobs
- held-out jobs
- evaluated learning-path skills
- generated questions

## Table 2. Main Experimental Results

Suggested columns:

- variant
- demand-weighted skill coverage
- average job-fit score
- job-fit success rate @ 0.60

## Table 3. Resource Answerability by Difficulty and Modality

Suggested columns:

- difficulty
- readings yes count / rate
- videos yes count / rate
- combined yes count / rate

## 10. Best Final Figure/Table Combination

If space is tight, the best set is:

- Figure 1: answerable questions by difficulty and modality
- Table 1: dataset summary
- Table 2: alignment results by curriculum variant
- Table 3: answerability by difficulty and modality

Total = `4`

This is concise, defensible, and compliant with the template.

## 11. Final Recommendation

The paper should be structured as:

- a framework paper in the front half
- a case-study evaluation paper in the back half

The best storyline is:

1. higher education has a curriculum-market mismatch problem
2. we propose a knowledge-graph-centric multi-agent framework
3. the framework has three layers
4. the Big Data case study first evaluates curriculum-market alignment numerically
5. the retrieved readings and videos are then tested for whether they can answer generated skill questions
6. answerability is substantially higher for readings than for videos and drops sharply for hard questions

That structure matches:

- the conference template
- your teacher's expectations
- the real strengths of the codebase
