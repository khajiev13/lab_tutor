# Big Data Experiment in the Conference Paper

This note explains how to present the updated Big Data evaluation in the conference paper after the notebook refactor.

The experiment should now be described as **two complementary analyses**, not one:

- a **course-level held-out alignment study**
- a **student-centered opportunity-spillover case study**

Both use the same four ablation rows:

- `KG`
- `KG + B_S`
- `KG + J_S`
- `KG + B_S + J_S`

But they answer different questions, so they should appear in **different tables** and be discussed separately.

## 1. Core Interpretation

The paper should present the experiment as a **curriculum-to-market alignment study**, not as a direct employment-outcome study.

Safe headline claim:

> The proposed framework improves estimated alignment between course content and labor-market requirements, and it can also expand the range of adjacent jobs that become reachable for a student who prepares around a focused set of target roles.

The experiment does **not** prove:

- guaranteed employment
- causal labor-market outcomes
- superiority in real hiring decisions

## 2. What `KG`, `B_S`, and `J_S` Mean Now

The notebook no longer uses the old concept-only interpretation for `KG`.

### Shared `KG`

`KG` now means:

> skill statements extracted from teacher-uploaded course documents (`TEACHER_UPLOADED_DOCUMENT.original_text`) and organized by course chapter

This is intentionally notebook-local for evaluation. These extracted course skills do **not** need to be persisted into the production graph.

### Course-Level `B_S`

For the main course-level table:

> `B_S` means the course's mapped `BOOK_SKILL` layer

### Course-Level `J_S`

For the main course-level table:

> `J_S` means the course's mapped `MARKET_SKILL` layer

### Student-Level `B_S`

For the student case-study table:

> `B_S` means the real student's `SELECTED_SKILL -> BOOK_SKILL` nodes

### Student-Level `J_S`

For the student case-study table:

> `J_S` means the union of skills extracted from the student's `INTERESTED_IN` jobs

This distinction is important in the paper. The same symbols are reused across both tables, but the student table uses **personalized inputs** rather than course-global book and market layers.

## 3. Paper Structure

Use the evaluation in three places:

- `Section 4: Case Study and Experimental Design`
- `Section 5: Results`
- `Section 6: Discussion`

Recommended paper flow:

1. describe the course-level held-out benchmark first
2. then introduce the student-centered case study
3. then discuss how the two views complement each other

## 4. Research Questions

Use three research questions.

### RQ1

> How well does the course, represented only through teacher-provided course materials, cover the competencies required by relevant Big Data job postings?

### RQ2

> How much do textbook-derived skills and market-derived skills improve held-out curriculum-to-market alignment?

### RQ3

> If a student prepares around a focused set of target jobs, how much does that preparation improve reachability of other related jobs?

## 5. Experimental Design

### 5.1 Case Study

Suggested text:

> We evaluate the framework on a Big Data course represented in our knowledge graph. Teacher-uploaded course materials are used to extract course-level skill statements by chapter. We then compare four curriculum variants formed by progressively adding textbook-derived and market-derived skills. In addition to the course-level benchmark, we run a personalized case study for a real student already present in the graph.

### 5.2 Course-Level Variants

Suggested text:

> For the course-level benchmark, `KG` contains only course skills extracted from teacher-uploaded documents. `KG + B_S` adds chapter-mapped textbook skills, `KG + J_S` adds chapter-mapped market skills, and `KG + B_S + J_S` combines both enrichment sources.

### 5.3 Student-Level Variants

Suggested text:

> For the student case study, `KG` again contains course skills extracted from teacher-uploaded documents. `KG + B_S` adds the student's selected textbook skills, `KG + J_S` adds skills extracted from the student's target job portfolio, and `KG + B_S + J_S` combines both personal enrichment sources.

### 5.4 Datasets and Splits

The notebook now uses **two different job pools**.

#### Main Benchmark Pool

Use strict Big Data / Data Engineering relevance filtering:

- `MAIN_MARKET_SCOPE = 'big_data'`
- deterministic seeded `build/held_out` split
- use `build_jobs` and `held_out_jobs` terminology in the paper
- avoid the misleading ML-style `train/test` wording

Suggested text:

> The main benchmark uses only job postings that are strongly aligned with the Big Data / Data Engineering market. These postings are split into build and held-out subsets using a seeded stratified procedure, and the reported course-level benchmark is computed on the held-out subset.

#### Student Case-Study Pool

Use the broader deduped market:

- `STUDENT_MARKET_SCOPE = 'all'`
- `STUDENT_ID = 2`
- the student's `INTERESTED_IN` jobs define the seed portfolio
- those seed jobs are excluded from evaluation
- the student is evaluated on the remaining broad-market jobs

Suggested text:

> The student case study uses a broader market pool. The student's explicit target jobs form a seed portfolio, the union of their extracted skills defines the personalized `J_S` layer, and the remaining jobs are used to measure opportunity spillover beyond the student's original targets.

### 5.5 Skill Extraction and Coverage Judgment

Suggested text:

> Course skills are extracted from teacher-uploaded course documents, and job skills are extracted from persisted job descriptions when available. A structured LLM-based evaluator then judges whether each job skill is `covered`, `partial`, or `missing` relative to a given curriculum variant, using only the job skill text and the provided curriculum evidence.

Important wording:

- say `persisted job descriptions`
- say `raw job text extraction from persisted descriptions`
- treat `linked MARKET_SKILL` fallback as a contingency path, not as the primary path for the latest artifact

For the current artifact, the evaluated jobs use persisted descriptions, so the paper should describe the run as a raw-description extraction benchmark rather than a proxy-skill benchmark.

### 5.6 Scoring

Suggested text:

> We map `covered`, `partial`, and `missing` to numeric values of `1.0`, `0.5`, and `0.0`, respectively. We then compute demand-weighted skill coverage and average job-fit score for each variant. Threshold-based success rates at `0.60` and `0.80` are used as supporting metrics.

## 6. Tables to Show

### Table 1: Dataset Summary

Suggested columns:

- course
- number of chapters
- number of teacher-uploaded documents
- number of raw jobs
- number of strict-scope main jobs
- number of build jobs
- number of held-out jobs
- number of student seed jobs
- number of student remaining jobs

Use the current notebook validation block for these values.

### Table 2: Course-Level Held-Out Results

Suggested columns:

- variant
- demand-weighted skill coverage
- average job-fit score
- jobs `>= 0.60`
- jobs `>= 0.80`

Suggested caption:

> Course-level held-out alignment results for the Big Data benchmark.

### Table 3: Student-Centered Opportunity Spillover

Suggested columns:

- variant
- demand-weighted skill coverage
- average job-fit score
- remaining jobs `>= 0.60`
- remaining jobs `>= 0.80`

Suggested caption:

> Personalized opportunity-spillover results for one student after combining course skills, selected textbook skills, and target-job skills.

Important note for the text:

> Table 3 is a personalized scenario analysis, not a held-out benchmark.

## 7. Figures to Show

Keep the figures focused on the **course-level benchmark**.

### Figure 1

Title:

> Market Alignment Improves as Course Enrichment Increases

What it shows:

- x-axis: `Course Only`, `Course + Books`, `Course + Market`, `Course + Books + Market`
- left panel: demand-weighted skill coverage
- right panel: average job-fit score

### Figure 2

Title:

> Skill Gap Closes as Course Enrichment Adds Missing Competencies

What it shows:

- 100% stacked bars
- segments: `Covered`, `Partial`, `Missing`

Do **not** force the student case study into the same figures. It is better reported as a separate table because it answers a different question.

Recommended exported figure files:

- `./figures/big_data_employability_course_2_market_alignment.png`
- `./figures/big_data_employability_course_2_market_alignment.svg`
- `./figures/big_data_employability_course_2_skill_gap.png`
- `./figures/big_data_employability_course_2_skill_gap.svg`

## 8. Results Writing Template

Use the current artifact values directly unless a newer rerun supersedes them.

### Table 2 Paragraph

> In the course-level held-out benchmark, the course-only baseline (`KG`) achieved a demand-weighted skill coverage of `0.2961` and an average job-fit score of `0.2775`. Adding textbook skills raised these values to `0.3398` and `0.3179`, respectively. Adding market skills produced the strongest held-out performance, increasing coverage to `0.4806` and average job-fit to `0.4602`, with `1/8` held-out jobs reaching `0.80`. The full variant (`KG + B_S + J_S`) remained well above the baseline at `0.4757` coverage and `0.4568` average job-fit, but it did not surpass `KG + J_S` on this particular held-out split. These results show that enrichment improves held-out curriculum-to-market alignment, with the largest gains attributable to market-skill augmentation.

### Table 3 Paragraph

> In the student-centered case study, the course-only baseline (`KG`) yielded a coverage score of `0.2608` and an average job-fit score of `0.2588` across the `55` jobs outside the student's seed portfolio. The student's `7` explicitly selected target job postings are used to extract a seed skill portfolio, and those seed-job skills are then applied to the remaining jobs to test opportunity spillover. The seed portfolio spans `AI Development Architect`, `Data Architect`, two `Data Engineer` roles, `Full Stack Engineer`, `Engineering Intern`, and `Junior Developer`, so the transferred skill bundle mixes AI architecture and governance, SQL and data profiling, ETL and data pipelines, Python/PySpark, APIs and microservices, Linux/containerization, and testing or automation practices. Adding the student's selected textbook skills produced only a small increase to `0.2671` coverage and `0.2646` average job-fit. Adding the `7` target-job skill bundle generated the dominant lift, increasing performance to `0.4196` coverage and `0.4259` average job-fit and raising the number of remaining jobs at `>= 0.60` from `1/55` to `6/55`. The full personalized variant achieved the strongest overall student-case result at `0.4266` coverage and `0.4333` average job-fit, suggesting that focused preparation around a small set of target jobs can unlock adjacent opportunities because related jobs share overlapping competencies.

### Synthesis Paragraph

> Taken together, the two analyses show both system-level and student-level value. The course-level benchmark demonstrates that enrichment improves held-out alignment with relevant labor-market requirements, while the student case study shows that the same framework can support personalized career spillover beyond a student's initial target jobs. Across both tables, market-aligned job skills explain most of the measurable lift, while textbook skills contribute smaller but still complementary gains.

## 9. Important Reporting Rules

When writing the paper:

- say `build/held_out`, not `train/test`
- say `course skills extracted from teacher-uploaded documents`, not `transcript concepts only`
- say `student opportunity spillover`, not `student held-out benchmark`
- report exact counts and scores from the newest artifact, not from earlier exploratory runs
- keep the course-level benchmark and student case study in separate tables

## 10. Current Status

The latest saved artifact already provides the current paper-ready evaluation snapshot:

- `62` deduplicated raw jobs in the broad graph pool
- `28` strict-scope Big Data / Data Engineering jobs for the main benchmark
- `20` build jobs and `8` held-out jobs for the course-level table
- `7` student seed jobs and `55` remaining jobs for the personalized spillover table
- `256` deduplicated course skills extracted from teacher-uploaded documents

Current course-level held-out results:

- `KG`: coverage `0.2961`, average job-fit `0.2775`, `0/8 >= 0.60`, `0/8 >= 0.80`
- `KG + B_S`: coverage `0.3398`, average job-fit `0.3179`, `1/8 >= 0.60`, `0/8 >= 0.80`
- `KG + J_S`: coverage `0.4806`, average job-fit `0.4602`, `1/8 >= 0.60`, `1/8 >= 0.80`
- `KG + B_S + J_S`: coverage `0.4757`, average job-fit `0.4568`, `1/8 >= 0.60`, `0/8 >= 0.80`

Current student-centered spillover results:

- `KG`: coverage `0.2608`, average job-fit `0.2588`, `1/55 >= 0.60`
- `KG + B_S`: coverage `0.2671`, average job-fit `0.2646`, `1/55 >= 0.60`
- `KG + J_S`: coverage `0.4196`, average job-fit `0.4259`, `6/55 >= 0.60`
- `KG + B_S + J_S`: coverage `0.4266`, average job-fit `0.4333`, `6/55 >= 0.60`

Current student seed portfolio:

- `SAP` — `AI Development Architect`
- `PTR Global` — `Data Architect`
- `BeaconFire Inc.` — `Data Engineer`
- `Stefanini North America and APAC` — `Data Engineer`
- `Alignerr` — `Full Stack Engineer`
- `Platform9` — `Engineering Intern`
- `Lensa` — `Junior Developer`

Representative spillover examples in the remaining-job pool:

- `Air Apps` — `Data Engineer`
- `First Horizon Bank` — `Enterprise Data Engineer Sr.`
- `Google` — `Software Engineer, AI/ML, Workspace`
- `SoFi` — `Software Engineer, Member AI Features`
- `YouTube` — `Senior Software Engineer, YouTube Ads ML`

The main held-out benchmark still remains a small case-study sample, but the latest artifact should replace the older `15/5` and proxy-skill wording everywhere in the paper.
