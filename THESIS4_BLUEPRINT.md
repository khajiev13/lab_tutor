# THESIS4 — Master Blueprint

**Title:** ARCD: Attentive Relational Cognitive Diagnosis with Multi-Agent Personalized Learning and Digital Twins
**Author:** Mohammed Al Hasani — Student ID 3820241060
**Institution:** Beijing Institute of Technology
**Document type:** Master's Thesis, Microsoft Word (`.docx`) deliverable using BIT thesis Word template, ~60 pages excluding references
**Style reference:** `Downloads/example.pdf` (sub-problem decomposition + Thesis Organization diagram pattern)
**Status:** v1.2 — Locked plan with Deliverable Options Catalog (§14), ready for writing
**This blueprint supersedes:** all earlier `thesis/`, `thesis2/`, `thesis3/` drafts. Thesis4 is a clean slate.

---

## 1. Locked Decisions (frozen, do not relitigate)

| # | Decision | Locked value |
|---|---|---|
| L1 | Thesis title | *ARCD: Attentive Relational Cognitive Diagnosis with Multi-Agent Personalized Learning and Digital Twins* |
| L2 | Author scope (vs. colleagues) | KG (schema + integration), ARCD model, Orchestrator, PathGen, Learning Fellow, AdaEx, Student Digital Twin, Teacher Digital Twin |
| L3 | Five GAT entity stages | **Skill / Question / Video / Reading / Student** — paper's new set; Lab and Progress entities are removed everywhere |
| L4 | Theory/Practical bifurcation | **Dropped.** Not in the project, not a thesis claim |
| L5 | Agent canonical name | **Learning Fellow** (capital L F). "Review Fellow" (proposal) and "LearnFell" (code variable) are surface forms only |
| L6 | Five thesis innovations | (a) Modality-adaptive multi-relational 5-stage GAT; (b) Four-stage decay cascade with topological prerequisite propagation; (c) Closed-loop multi-agent orchestrator (PathGen + Learning Fellow + AdaEx); (d) Student Digital Twin with 30-day forecast and 3-strategy comparison; (e) Teacher Digital Twin with what-if simulator. Items (d) and (e) are the headline thesis-only contributions beyond the conference paper |
| L7 | Embedding dimension | All ARCD I/O at **2048-dim** (KG-native). Never 48 or 96 |
| L8 | Active checkpoint | `roma_synth_v6_2048` (per CLAUDE.md retraining notes) |
| L9 | Page budget | Total ~60, minimum 50, references not counted |
| L10 | Evaluation flavor | Cognitive-diagnosis prediction metrics (AUC/ACC/RMSE on simulated and real data) **plus** human-subject study (teacher decisions, student engagement) |
| L11 | **Output format** | Microsoft Word **`.docx`** is the submission deliverable. Source authored in Markdown, compiled to `.docx` via Pandoc using `docs/thesis/sources/bit_thesis_template_and_cover/310fbfa7b4114ccf820b8df462913921.docx` as the BIT reference template. The LaTeX `bithesis.cls` track is **not** used for thesis4 |
| L12 | **Figures, tables, algorithms — language** | All visual artefacts (figure labels, table headers/cells, algorithm pseudocode, axis labels, legends, captions) are authored in **English only**. Body text remains bilingual where the BIT cover and abstract require Chinese; the rest is English |
| L13 | **Style reference** | `Downloads/example.pdf` — adopt its two signature patterns: (a) Problem Statement decomposed into 5 named sub-problems with thematic statement-style titles, and (b) a single-figure Thesis Organization diagram inside §1.5 grouping every chapter's subsections. Subsection titles across the whole thesis use full thematic statements, not generic labels |

---

## 2. Page Budget by Chapter

| Chapter | Title | Pages | % of body |
|---|---|---|---|
| — | Front matter (cover, abstract EN/中, ToC) | 1 (abstract) | — |
| 1 | Introduction | 5–6 | 10% |
| 2 | Related Work / Literature Review | 8–10 | 16% |
| 3 | Methodology (system + ARCD + 4 agents + 2 twins) | 28–30 | 50% |
| 4 | Implementation | 10–15 | 20% |
| 5 | Results & Evaluation | 3–5 | 6% |
| 6 | Conclusion & Future Work | 2–3 | 4% |
| — | References | not counted | — |
| **Total body** | — | **~60** | 100% |

---

## 3. Chapter-by-Chapter Outline

### Abstract (1 page)

* Problem in 2 sentences (decay-aware diagnosis on heterogeneous learning evidence; closed-loop personalization for both student and teacher).
* Approach in 3 sentences (KG-grounded ARCD with 5-stage GAT and 4-stage decay cascade; multi-agent orchestrator with PathGen + Learning Fellow + AdaEx; Student & Teacher Digital Twins).
* Contributions enumerated (the 5 in L6).
* Headline numbers (AUC, ablation deltas, twin study sample size, pilot finding).
* Keywords: cognitive diagnosis, knowledge graph, graph attention, forgetting curve, multi-agent, LangGraph, digital twin, adaptive learning.

### Chapter 1 — Introduction (5–6 pages)

Style follows `Downloads/example.pdf`: a single Background section, a Problem Statement decomposed into five named sub-problems, a Proposed Solution that maps each sub-problem to a thesis component, the research questions, and a contributions-and-organization section that closes with a single full-width **Thesis Organization** figure (F0).

| § | Title (statement-style) | Pages |
|---|---|---|
| 1.1 | Background and Motivation: Adaptive Learning Under Skill Decay and Heterogeneous Evidence | 1.0 |
| 1.2 | Problem Statement: From One-Shot Diagnosis to Closed-Loop Personalization | 2.5 |
| 1.2.1 | Heterogeneous Learning Evidence Resists Unified Cognitive Diagnosis | 0.5 |
| 1.2.2 | Forgetting Cascades Through Prerequisite Networks Are Underspecified | 0.5 |
| 1.2.3 | Static Recommendation Cannot Adapt to Real-Time Mastery Drift | 0.5 |
| 1.2.4 | Students Cannot See Their Own Future Learning Trajectory | 0.5 |
| 1.2.5 | Teachers Lack Decision Support for Class-Level Intervention | 0.5 |
| 1.3 | Proposed Solution: A KG-Grounded ARCD Engine With Multi-Agent Loop and Dual Digital Twins | 1.0 |
| 1.4 | Research Questions (RQ1–RQ6) | 0.5 |
| 1.5 | Contributions and Thesis Organization | 1.0 |

**Locked Chapter 1 visuals:**

* **F1** — Problem-to-Solution Mapping (one figure on the §1.3 page): five sub-problems on the left, five thesis components on the right, arrows between them — example-style (English labels only).
* **F0** — Thesis Organization Diagram (full-width figure inside §1.5): six chapter blocks, each block lists its top-level subsection titles in English boxes; visually mirrors the example's "Curriculum-Market Alignment Framework" diagram on its page 1.

**Research questions (locked):**

* **RQ1** — Can a 5-stage multi-relational GAT over Skill/Question/Video/Reading/Student improve next-attempt prediction over single-relation baselines?
* **RQ2** — Does an explicit four-stage decay cascade with topological prerequisite propagation outperform Ebbinghaus-only decay on long-horizon forecasting?
* **RQ3** — Does a closed-loop orchestrator (PathGen → Learning Fellow → AdaEx) drive faster mastery growth and lower mastery decay than a static recommender baseline?
* **RQ4** — Can a Student Digital Twin produce a 30-day forecast and 3-strategy comparison that students rate as actionable and trustworthy?
* **RQ5** — Can a Teacher Digital Twin's what-if simulator change the intervention decisions teachers make in a controlled study?
* **RQ6** — How does ARCD generalize to a real classroom cohort after training only on synthetic IRT data?

**Sub-problem ↔ component ↔ research question map (drives F1 and the §1.3 prose):**

| Sub-problem | Mapped thesis component(s) | Mapped RQ |
|---|---|---|
| 1.2.1 Heterogeneous evidence | KG schema + 5-stage GAT in ARCD | RQ1 |
| 1.2.2 Decay cascades | 4-stage decay cascade in ARCD | RQ2 |
| 1.2.3 Static recommendation | Orchestrator + PathGen + Learning Fellow + AdaEx | RQ3 |
| 1.2.4 No trajectory visibility | Student Digital Twin | RQ4 |
| 1.2.5 No teacher decision support | Teacher Digital Twin | RQ5 |
| All five (generalization) | End-to-end pipeline | RQ6 |

### Chapter 2 — Related Work (8–10 pages)

Subsection titles are thematic statements (example-style), not generic labels.

| § | Title (statement-style) | Pages | Reusable? |
|---|---|---|---|
| 2.1 | Cognitive Diagnosis Models From IRT and DINA to Neural and Relational Architectures | 1.5 | reuse from lit-review §2.1 |
| 2.2 | Knowledge Tracing as a Sequential Lens on Mastery Evolution | 1.5 | reuse from lit-review §2.2 |
| 2.3 | Knowledge Graphs as the Substrate for Adaptive Learning | 1.5 | reuse from lit-review §2.3 |
| 2.4 | Forgetting and Memory Decay Beyond the Single-Rate Curve | 1.0 | reuse from lit-review §2.4, expand to four-stage decay |
| 2.5 | Multi-Agent and LLM-Augmented Tutoring Workflows | 1.5 | reuse from lit-review §2.5 + add 2024–2025 LangGraph & swarm papers |
| 2.6 | Educational Digital Twins for Personalization and Decision Support | 1.0 | **NEW stream** — must source 5–10 references |
| 2.7 | Synthesis and Research Gap | 1.0 | new (T1: baseline comparison on 6 axes) |

### Chapter 3 — Methodology (28–30 pages)

The body chapter. Subsection titles are thematic statements; allocations are budgets. Every component subsection has at least one English-only figure (F-series) and one defining equation or pseudocode block.

| § | Title (statement-style) | Pages |
|---|---|---|
| 3.1 | System Overview: Eight Components Around a Shared Knowledge Graph | 2 |
| 3.2 | Knowledge Graph as the Shared Substrate for Diagnosis, Agents, and Twins | 3 |
| 3.2.1 | Node Types and Edge Semantics for Skills, Resources, and Learners | 1 |
| 3.2.2 | Embedding Storage and Write-Back of ARCD Stage Outputs | 1 |
| 3.2.3 | The Knowledge Graph as a Substrate for ARCD, the Agents, and the Twins | 1 |
| 3.3 | ARCD: Attentive Relational Cognitive Diagnosis With Decay Modeling | 9 |
| 3.3.1 | Five-Stage Multi-Relational GAT Over Skill, Question, Video, Reading, and Student | 2.5 |
| 3.3.2 | Temporal Attention Over Heterogeneous Learning Events | 1.5 |
| 3.3.3 | A Four-Stage Decay Cascade With Topological Prerequisite Propagation | 2.5 |
| 3.3.4 | Joint Performance and Mastery Heads With Mask-Aware Loss | 1.5 |
| 3.3.5 | Cold-Start and Out-of-Vocabulary Handling Through a Reserved Student Slot | 1 |
| 3.4 | Orchestrator: A LangGraph Closed Loop From Assessment to Reassessment | 2 |
| 3.5 | Learning Path Generator: Prerequisite-Filtered ZPD-Aligned Multi-Criterion Scoring | 2.5 |
| 3.6 | Learning Fellow: Detecting Prior-Correct Overclaim and Driving Targeted Review | 2.5 |
| 3.7 | Adaptive Exercise: Closed-Form Difficulty Targeting With LLM Generation and Three-Axis Evaluation | 2.5 |
| 3.8 | Student Digital Twin: Mastery Snapshot, 30-Day Forecast, and Three-Strategy Comparison | 2 |
| 3.9 | Teacher Digital Twin: Class Analytics, What-If Simulation, and Authorisation-Bounded Drilldown | 2 |
| 3.10 | End-to-End Loop: Composing the Eight Components Into One Adaptive Cycle | 0.5 |

### Chapter 4 — Implementation (10–15 pages)

| § | Title (statement-style) | Pages |
|---|---|---|
| 4.1 | Repository Topology and Module Boundaries Across Frontend, Backend, and Graph Builder | 1 |
| 4.2 | Backend Modular Onion Architecture for Each Feature Domain | 1.5 |
| 4.3 | ARCD Training Pipeline From Synthetic Data to a 2048-Dim Checkpoint | 2.5 |
| 4.4 | Knowledge Graph Integration and Write-Back of Five Embedding Properties | 1.5 |
| 4.5 | Wiring the Orchestrator as a LangGraph State Machine With Persistence | 1.5 |
| 4.6 | Frontend Integration of the Student and Teacher Digital Twins | 2 |
| 4.7 | Deployment With Docker Compose Across Postgres, Neo4j, Backend, and Frontend | 1 |
| 4.8 | Reproducibility Through Environment Variables, Run IDs, and a Checkpoint Registry | 1 |

### Chapter 5 — Experiments and Results (3–5 pages)

| § | Title (statement-style) | Pages |
|---|---|---|
| 5.1 | Datasets and Experimental Setup Across Synthetic and Pilot Real-Classroom Data | 0.5 |
| 5.2 | Predictive Performance on Next-Attempt Correctness and Per-Skill Mastery | 1 |
| 5.3 | Ablations Isolating Decay, Prerequisite Cascade, Modality Adaptation, and Cold-Start | 1 |
| 5.4 | Pilot Study Results for the Student and Teacher Digital Twins | 1 |
| 5.5 | Discussion of Findings and Threats to Validity | 0.5 |

### Chapter 6 — Conclusion and Future Work (2–3 pages)

| § | Title (statement-style) | Pages |
|---|---|---|
| 6.1 | Summary of Contributions Mapped Back to the Research Questions | 1 |
| 6.2 | Limitations of the Current Pipeline and Evaluation | 0.75 |
| 6.3 | Future Work Toward Multimodal, Federated, and Longitudinal Adaptive Learning | 0.75 |

### References (not counted)

* Target: 80–110 entries, BibTeX in `reference/main.bib`.
* Citation style: GB/T 7714-2015 numeric (BIT default; `gb-7714-2015-numeric.csl` already in `docs/thesis/workspace/csl/`).

---

## 4. Source-to-Chapter Reuse Map

| Source | Reusability for thesis4 |
|---|---|
| `docs/thesis/sources/ARCD-Paper.pdf` (conference paper) | **High** — entity set matches L3. Lift §3.1–§3.4 into Methodology §3.3 with light tightening. Tables 2–4 lift verbatim into Chapter 5 |
| `docs/thesis/sources/Hasani-3820241060-Opening Proposal.pdf` | **Medium** — reuse motivation paragraphs in Chapter 1; **redact** Innovation 3 (Theory/Practical) per L4 |
| `docs/thesis/sources/38202410600-AlHasani-Mohammed-Literature Review.pdf` | **High** — six streams map directly to Chapter 2 §2.1–§2.5. §2.6 (Educational Digital Twins) is **new**, needs fresh citations |
| `docs/agent_logic_current.md` | **Authoritative** for §3.4–§3.7 (Orchestrator, PathGen, Learning Fellow, AdaEx). Treat as ground truth |
| `docs/COGNITIVE_DIAGNOSIS_AND_TEACHER_TWIN.md` | **Authoritative** for §3.8 (Student Twin) and §3.9 (Teacher Twin) |
| `CLAUDE.md` ARCD retraining notes | **Authoritative** for §4.3 (training pipeline, dimensions, fixes) |
| Live code under `backend/app/modules/{arcd_agent,cognitive_diagnosis,teacher_digital_twin}/` | **Authoritative** for all code-derived figures and snippets in Chapter 4 |
| `docs/thesis2/`, `docs/thesis3/` LaTeX | **Do not reuse.** Thesis4 is a clean slate |

---

## 5. Figure & Table Plan

### Figures (~25 total — all labels, captions, and legends in English only per L12)

| ID | Title | Chapter | Style | Source / status |
|---|---|---|---|---|
| F0 | Thesis Organization Diagram (six chapter blocks with subsection boxes) | 1.5 | Example-style grid (mirrors `Downloads/example.pdf` page 1.1) | New (mermaid → png) |
| F1 | Problem-to-Solution Mapping (5 sub-problems → 5 components) | 1.3 | Two-column box-and-arrow | New |
| F2 | System Overview With KG Substrate and Eight Components | 3.1 | Block diagram | New, replaces conference paper Fig. 1 |
| F3 | Knowledge Graph Schema | 3.2.1 | UML-style node/edge | New |
| F4 | KG-to-Component Data Flow | 3.2.3 | Layered flow | New |
| F5 | ARCD End-to-End Architecture | 3.3 | Block diagram | Adapt conference paper Fig. 2 |
| F6 | Temporal Attention Over Heterogeneous Events | 3.3.2 | Sequence diagram | Adapt paper Fig. 3 |
| F7 | Four-Stage Decay Cascade With Prerequisite Propagation | 3.3.3 | Block diagram | Adapt paper Fig. 4 |
| F8 | Performance and Mastery Heads | 3.3.4 | Block diagram | New |
| F9 | Orchestrator LangGraph State Machine | 3.4 | State machine | New |
| F10 | PathGen Filter and Scoring Pipeline | 3.5 | Pipeline | New |
| F11 | PathGen State In / State Out Schema | 3.5 | Schema | New |
| F12 | Learning Fellow Review Loop | 3.6 | Loop diagram | New |
| F13 | Learning Fellow PCO Detector Schema | 3.6 | Schema | New |
| F14 | AdaEx Generation-Evaluation Loop | 3.7 | Loop diagram | New |
| F15 | AdaEx Three-Axis Quality Space | 3.7 | Radar chart | New |
| F16 | Student Twin Engine (Mastery Snapshot + Forecast) | 3.8 | Block diagram | New |
| F17 | Student Twin What-If Rollout | 3.8 | Time-series sketch | New |
| F18 | Student Twin Three-Strategy Comparison UI | 3.8 | UI mockup | New |
| F19 | Teacher Twin Dashboard Layout | 3.9 | UI mockup | New |
| F20 | Teacher Twin What-If Simulator Flow | 3.9 | Flow diagram | New |
| F21 | Repository Topology | 4.1 | Tree | New |
| F22 | Backend Onion Layers per Feature Module | 4.2 | Concentric rings | New |
| F23 | Training-to-Write-Back Pipeline | 4.3 | Pipeline | New |
| F24 | Frontend Route Map and State Flow | 4.6 | Sitemap | New |

### Tables (~12 total — all column headers, row labels, and captions in English only per L12)

| ID | Title | Chapter |
|---|---|---|
| T1 | Comparison of Baselines Across Cognitive Diagnosis, Knowledge Tracing, Knowledge Graphs, Decay, Multi-Agent, and Twins | 2.7 |
| T2 | Knowledge Graph Node and Edge Counts | 3.2 |
| T3 | ARCD Layer Dimensions (All 2048) | 3.3 |
| T4 | PathGen Scoring Weights | 3.5 |
| T5 | Learning Fellow PCO Trigger Thresholds | 3.6 |
| T6 | AdaEx Three-Axis Evaluator Rubric | 3.7 |
| T7 | Student Twin Strategy Scenario Definitions | 3.8 |
| T8 | Teacher Twin What-If Intervention Catalog | 3.9 |
| T9 | Synthgen Run Configuration for `roma_synth_v6_2048` | 4.3 |
| T10 | Predictive Metrics (AUC, ACC, RMSE) on Synthetic and Real Data | 5.2 |
| T11 | Ablation Deltas | 5.3 |
| T12 | Twin Pilot Results (Likert Means and Decision-Change Rate) | 5.4 |

### Algorithms (~7 total — pseudocode rendered in English only per L12)

| ID | Title | Chapter |
|---|---|---|
| A1 | Five-Stage GAT Forward Pass | 3.3.1 |
| A2 | Four-Stage Decay Cascade With Prerequisite Propagation | 3.3.3 |
| A3 | Orchestrator LangGraph Cycle (assess → pathgen → review → exercises → reassess → finalize) | 3.4 |
| A4 | PathGen Scoring and Top-K Selection | 3.5 |
| A5 | Learning Fellow PCO Detection and Review Trigger | 3.6 |
| A6 | AdaEx Closed-Form Difficulty Targeting and Refinement Loop | 3.7 |
| A7 | Student Twin 30-Day Forecast and Three-Strategy Rollout | 3.8 |

---

## 6. Evaluation Plan (operational detail for Chapter 5)

| Component | Metric | Dataset | Baseline | Status |
|---|---|---|---|---|
| ARCD next-attempt | AUC, ACC | synthgen v6 hold-out | NCD, KaNCD, RCD | partly in conference paper — re-run |
| ARCD mastery | RMSE | synthgen v6 hold-out | DKT, AKT | re-run |
| Decay cascade | RMSE on 7/14/30-day forecast | synthgen v6 forecast split | Ebbinghaus-only, no-decay | ablation |
| Orchestrator loop | mastery growth slope, decay slope | simulated student rollouts | static recommender | new experiment |
| PathGen | top-K skill recall against expert path | expert-annotated subset | random, popularity, single-criterion | new experiment |
| Learning Fellow PCO | precision/recall on labelled overclaim events | log-mined sample | rule-only baseline | new experiment |
| AdaEx | 3-axis quality (alignment / difficulty fit / pedagogy) | LLM judge + 2 expert raters | base prompt | new experiment |
| Student Twin | Likert (trust, actionability), recommendation acceptance | pilot N≈20 students | none (within-subject before/after) | human study |
| Teacher Twin | decision-change rate, time-to-decision | pilot N≈8 teachers | dashboard-only condition | human study |
| Real-classroom generalization | AUC, calibration | real cohort N≈30 | model-only baseline | pilot |

Human-study artefacts to prepare:

* IRB-style consent form (template in `docs/`).
* Pre/post Likert questionnaire (5 items × 5 points).
* Anonymized data-handling SOP referencing CLAUDE.md privacy policy.

---

## 7. Implementation Steps & Writing Schedule

The thesis is due in **~10 weeks**. Buffer one week at the end for binding & supervisor revisions.

### Phase 0 — Setup (Week 0, ~3 days)

| Step | Owner | Output | Done-when |
|---|---|---|---|
| 0.1 | Author | Create `docs/thesis/thesis4/` per §10 layout (clean slate; no carry-over from thesis2/3) | folder exists with `Makefile`, `pandoc.yaml`, empty `chapters/`, empty `figures/` |
| 0.2 | Author | Copy BIT Word template into `reference_template.docx`; fill cover metadata (title L1, author, supervisor, school, date) | first build of `make docx` produces a valid Word file with the correct cover |
| 0.3 | Author | Author `pandoc.yaml` with reference-doc, GB/T 7714-2015 CSL, ToC depth 3, bibliography path | `make docx` succeeds end-to-end on an empty `chapters/01_introduction.md` |
| 0.4 | Author | Set up `figures/` with `render_figures.py` (mermaid CLI, 300 dpi) and a smoke test that all labels are ASCII (English-only per L12) | `make figures` regenerates F0 and `make lint-en` reports zero violations |
| 0.5 | Author | Add a `make lint-en` rule that greps `figures/`, `tables/`, `algorithms/` for non-ASCII characters and prints a fail list | rule runs in CI-style |
| 0.6 | Author | Confirm checkpoint `roma_synth_v6_2048` exists; if not, kick off training per CLAUDE.md v6 command | checkpoint dir + `vocab.json` present |

### Phase 1 — Methodology core (Weeks 1–4)

This is the largest block (28–30 pages) and the highest-novelty content.

| Week | Step | Output | Sources to draw from |
|---|---|---|---|
| 1 | §3.1 + §3.2 (system overview + KG schema) | 5 pages prose + F2, F3, F4, T2 | conference paper §1–§2, `agent_logic_current.md`, live Neo4j MCP for counts |
| 1 | §3.3.1 + §3.3.2 (GAT + temporal) | 4 pages + F5, F6, T3, **A1** | conference paper §3.2.1–§3.2.2, code in `arcd_agent/model/training/arcd_model.py` |
| 2 | §3.3.3 + §3.3.4 + §3.3.5 (decay + heads + cold-start) | 5 pages + F7, F8, **A2** | conference paper §3.2.3–§3.2.4, CLAUDE.md v4–v6 notes |
| 2 | §3.4 (Orchestrator) | 2 pages + F9 + **A3** | `agents/orchestrator.py`, `agent_logic_current.md` |
| 3 | §3.5 (PathGen) | 2.5 pages + F10, F11, T4, **A4** | `agents/pathgen.py` |
| 3 | §3.6 (Learning Fellow) | 2.5 pages + F12, F13, T5, **A5** | `agents/learnfell.py` |
| 4 | §3.7 (AdaEx) | 2.5 pages + F14, F15, T6, **A6** | `agents/adaex.py` |
| 4 | §3.8 (Student Twin) | 2 pages + F16, F17, F18, T7, **A7** | `cognitive_diagnosis/service.py`, `COGNITIVE_DIAGNOSIS_AND_TEACHER_TWIN.md` |
| 4 | §3.9 + §3.10 (Teacher Twin + closing loop) | 2.5 pages + F19, F20, T8 | `teacher_digital_twin/service.py` |

### Phase 2 — Front-loaded prose (Weeks 5–6)

| Week | Step | Output |
|---|---|---|
| 5 | Chapter 2 §2.1–§2.5 (lift from lit-review with refresh) | 7 pages |
| 5 | Chapter 2 §2.6 (Educational Digital Twins, NEW) | 1 page + 5–10 new BibTeX entries |
| 5 | Chapter 2 §2.7 (synthesis & research gap) | 1 page + T1 |
| 6 | Chapter 1 (Introduction) — **example-style** with 5 sub-problems §1.2.1–§1.2.5 | 5–6 pages + F1 (problem→solution map) + F0 (Thesis Organization Diagram in §1.5) |
| 6 | Abstract (EN + 中文) | 1 page |

### Phase 3 — Implementation chapter (Week 7)

| Step | Output |
|---|---|
| §4.1 + §4.2 (repo + onion) | 2.5 pages + F21, F22 |
| §4.3 (training pipeline) | 2.5 pages + F23, T9 |
| §4.4 + §4.5 (KG write-back + LangGraph wiring) | 3 pages |
| §4.6 (frontend) | 2 pages + F24 |
| §4.7 + §4.8 (deployment + reproducibility) | 2 pages |

### Phase 4 — Experiments & results (Week 8)

| Step | Output |
|---|---|
| Re-run ARCD AUC/ACC/RMSE on synthgen v6 hold-out | T10 |
| Run all 4 ablations | T11 |
| Run PathGen / Learning Fellow / AdaEx component experiments | numbers in §5.2–§5.3 |
| Conduct Student Twin pilot (N≈20) and Teacher Twin pilot (N≈8) | T12 |
| Write Chapter 5 prose | 3–5 pages |

### Phase 5 — Conclusion, polish, references (Week 9)

| Step | Output |
|---|---|
| Write Chapter 6 (Conclusion + future work) | 2–3 pages |
| Cross-reference sweep (all `\ref`, `\cite`, `\autoref` resolve) | clean log |
| Bibliography pass: 80–110 entries, deduplicated, GB/T 7714-2015 formatted | `reference/main.bib` finalized |
| Figure quality pass: 300 dpi minimum, consistent colormap, legible at print size | `figures/*.png` regenerated |
| Hand to supervisor for first review | comments received |

### Phase 6 — Revision & defense prep (Week 10)

| Step | Output |
|---|---|
| Apply supervisor revisions | revised PDF |
| Compile final cover, signatures, declaration of originality | submission package |
| Defense slide deck (15–20 slides) | `defense.pptx` |
| Internal mock defense | feedback applied |

---

## 8. Risks, Mitigations, and Contingencies

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `roma_synth_v6_2048` retraining not converged in time | Medium | High | Train in Phase 0 in parallel with writing; keep v4 checkpoint as fallback for §5 numbers |
| Real-classroom cohort access blocked by IRB / school | Medium | Medium | Frame Chapter 5 around synthetic + pilot; mark real-cohort study as supplementary |
| Page budget overrun in Methodology | Medium | Low | Move §3.10 closing-loop content to a half-page figure caption; trim §3.3.5 to 0.75 pages |
| Page budget undershoot in Results | Medium | Low | Add a calibration plot and a per-skill RMSE breakdown to lift §5.2 from 1 to 1.5 pages |
| Educational Digital Twin literature too thin | Low | Medium | Broaden §2.6 to "intelligent tutoring digital companions" and pull from learning-analytics + adaptive systems venues |
| Teacher pilot N too small for significance | High | Low | Report descriptive statistics + qualitative themes; do not claim statistical significance |
| Theory/Practical references leaking from old proposal | Medium | Low | Global grep for "theory", "practical bifurcation", "lab", "progress" before submission; redact or rephrase per L4 |
| BIT Word template style mapping breaks during Pandoc compile (e.g., custom Heading 1 font lost) | Low | High | Use the official BIT `.docx` template untouched as `reference_template.docx`; verify `make docx` output against template-styled headings each Phase boundary; do not edit `reference_template.docx` by hand |
| Non-ASCII characters leak into figures/tables/algorithms | Medium | Medium | `make lint-en` runs in CI and fails the build on any non-ASCII match inside `figures/`, `tables/`, or `algorithms/` |
| Supervisor requests scope expansion beyond L2 | Low | Medium | Point to L2 + colleague-scope paragraph in §1.5; document boundary in cover letter |

---

## 9. Definitions of Done (per chapter)

| Chapter | Done-when |
|---|---|
| 1 | All 5 contributions in §1.4 are stated, each linked to a methodology section. RQ1–RQ6 each have a forward-reference to a results subsection |
| 2 | Every claim is cited. T1 (baseline comparison) is filled with at least 8 rows. §2.6 has ≥5 references |
| 3 | Every component (KG, ARCD, Orchestrator, PathGen, Learning Fellow, AdaEx, Student Twin, Teacher Twin) has at least one figure and one defining equation or pseudocode block |
| 4 | Every code block compiles or has a footnote pointing to the live file. F23 traces the full path from synthgen → train → write-back |
| 5 | Every metric in T10–T12 is reproducible from a documented run-id |
| 6 | Each limitation in §6.2 maps to a future-work item in §6.3 |

---

## 10. File & Folder Layout for `docs/thesis/thesis4/`

Authored in Markdown, compiled to `.docx` via Pandoc using the BIT Word template as the reference document.

```
docs/thesis/thesis4/
├── README.md                        # how to build, conventions, English-only rule
├── Makefile                         # `make docx`, `make figures`, `make all`
├── pandoc.yaml                      # pandoc options (reference-doc, csl, toc-depth)
├── reference_template.docx          # copied from BIT Word template (see L11) — do NOT edit by hand
├── chapters/
│   ├── 00_front_matter.md           # cover meta, abstract EN + 中文 (1 page)
│   ├── 01_introduction.md           # Chapter 1 — 5–6 pages, follows example.pdf style
│   ├── 02_related_work.md           # Chapter 2 — 8–10 pages
│   ├── 03_methodology.md            # Chapter 3 — 28–30 pages (the giant)
│   ├── 04_implementation.md         # Chapter 4 — 10–15 pages
│   ├── 05_results.md                # Chapter 5 — 3–5 pages
│   ├── 06_conclusion.md             # Chapter 6 — 2–3 pages
│   ├── 90_acknowledgements.md       # 致谢
│   ├── 91_resume.md                 # 个人简历
│   └── 92_appendices.md             # raw configs, extra tables
├── figures/                         # English-only labels, captions, legends
│   ├── F0_thesis_organization.{mmd,png}
│   ├── F1_problem_solution_map.{mmd,png}
│   ├── F2_system_overview.{mmd,png}
│   ├── ... (all 25 figures, .mmd source where applicable)
│   └── render_figures.py            # mermaid → png at 300 dpi
├── tables/
│   └── *.csv                        # raw table data, rendered into docx via pandoc
├── algorithms/
│   └── A1..A7.md                    # pandoc-style fenced pseudocode (English only)
├── reference/
│   ├── main.bib                     # 80–110 entries
│   └── gb-7714-2015-numeric.csl     # citation style (BIT default)
├── images/
│   ├── bit_logo.png
│   ├── icon_academic.jpg
│   └── icon_professional.jpg
└── build/
    └── thesis4.docx                 # final deliverable produced by `make docx`
```

This layout is independent of `thesis/`, `thesis2/`, `thesis3/` — none of those folders are imported.

---

## 11. Tooling & Commands Reference

The toolchain is **Markdown → Pandoc → `.docx`** with the BIT Word reference template. No LaTeX is required for the thesis4 deliverable.

| Task | Command |
|---|---|
| Build the thesis as `.docx` | `cd docs/thesis/thesis4 && make docx` (wraps `pandoc --reference-doc=reference_template.docx --csl=reference/gb-7714-2015-numeric.csl --bibliography=reference/main.bib --toc --toc-depth=3 -o build/thesis4.docx chapters/*.md`) |
| Build a quick PDF preview | `make pdf` (pandoc → `.docx` → libreoffice headless → PDF) |
| Regenerate figures (English-only labels) | `cd docs/thesis/thesis4/figures && python render_figures.py` |
| Lint the Markdown for English-only rule | `make lint-en` (greps figures, tables, algorithms for non-ASCII labels and reports violations) |
| Re-run ARCD training (v6 defaults) | `cd backend && uv run python arcd_train.py --data-dir ../knowledge_graph_builder/data/synthgen/<run_id> --out-dir checkpoints/roma_synth_v6_2048` |
| Inspect Neo4j live counts | Use the `user-neo4j-database` MCP server |
| Rebuild backend container | `docker compose up -d --build backend` |
| Re-run inference walkthrough | `backend/notebooks/arcd_inference_walkthrough.ipynb` |

**Pandoc reference-doc rationale:** the BIT Word template at `docs/thesis/sources/bit_thesis_template_and_cover/310fbfa7b4114ccf820b8df462913921.docx` is copied verbatim into `docs/thesis/thesis4/reference_template.docx`. Pandoc inherits its named styles (Heading 1, Heading 2, Caption, Table, Code, etc.), so all chapter Markdown maps automatically to the BIT-approved Word style.

---

## 12. Quality Bars & Submission Checklist

Pre-submission checklist (run in Phase 5–6):

- [ ] Title on cover matches L1 verbatim
- [ ] Page count is in `[50, 60]` excluding references (verified in compiled `.docx` printed at A4)
- [ ] Every figure is referenced in text by its English caption
- [ ] Every table is referenced in text
- [ ] Every algorithm (A1–A7) is referenced in text
- [ ] **English-only check passes:** `make lint-en` returns zero non-ASCII matches inside any file under `figures/`, `tables/`, or `algorithms/` (per L12)
- [ ] Chapter 1 follows example-style: 5 named sub-problems §1.2.1–§1.2.5; F0 Thesis Organization Diagram present in §1.5; F1 problem-to-solution map present in §1.3
- [ ] No occurrence of "Lab", "Progress", "Theory/Practical bifurcation", "Review Fellow", or "LearnFell" in body text
- [ ] All five GAT stages described as Skill / Question / Video / Reading / Student
- [ ] All embedding dimensions in §3.3 stated as 2048
- [ ] Active checkpoint cited in §5 is `roma_synth_v6_2048`
- [ ] Bibliography uses GB/T 7714-2015 numeric, deduplicated
- [ ] Acknowledgements page present
- [ ] 个人简历 (resume) page present per BIT requirement
- [ ] Declaration of originality signed and inserted
- [ ] **`.docx` builds reproducibly** via `make docx` from a clean clone (no Word-only edits that diverge from `chapters/*.md` source)
- [ ] BIT Word reference template styles (Heading 1, Heading 2, Caption, Table) all map correctly in the produced `build/thesis4.docx`

---

## 13. Style Reference (anchored to `Downloads/example.pdf`)

The following four conventions from the example are adopted verbatim for thesis4:

| Convention | Example location | Thesis4 adoption |
|---|---|---|
| Single-figure Thesis Organization Diagram on the page closing Chapter 1 | example page numbered 1, immediately before §1.2 | F0 in §1.5; six chapter blocks, each block lists subsection titles in English boxes |
| Problem Statement decomposed into 5 named sub-problems | example §1.2.1–§1.2.5 | thesis4 §1.2.1–§1.2.5 with sub-problem ↔ component ↔ RQ map |
| Subsection titles written as full thematic statements, not generic labels | example §1.1 "Student Readiness Under Labor-Market Change", §1.2.1 "Fast-Changing Job Skills Create Course-To-Career Uncertainty" | applied to every chapter §3-letter onward (see Chapter 1–6 outlines above) |
| Every chapter's first page presents an explicit problem-to-solution thread that names the chapter's deliverables in the opening paragraph | example §1.2 opening | each thesis4 chapter opens with a 4–6 line abstract paragraph that names its deliverables and figures in plain text |

The example uses a single, neutral font for diagram boxes with English-only labels. Thesis4 mirrors this: figures use **Inter / Arial / Helvetica** for box text; no Chinese characters appear inside any figure, table, or algorithm.

---

## 14. Deliverable Options Catalog (writing menu)

A standing menu of writing units that can be requested and produced individually. Each option is self-contained, tied to a specific blueprint section, and produced as `.docx`-ready Markdown that drops directly into `docs/thesis/thesis4/chapters/*.md`. This catalog is the operational interface to the blueprint — pick a letter at any phase boundary and the corresponding deliverable is produced.

| Option | Deliverable | Pages | Maps to blueprint sections | Sources of truth | Status |
|---|---|---|---|---|---|
| **A** | Thesis-quality prose for **Chapter 1 (Introduction)** end-to-end — real-world motivation + 5 named sub-problems §1.2.1–§1.2.5 + proposed solution + RQ1–RQ6 + contributions and Thesis Organization Diagram (F0) | ~6 | §3 Chapter 1 outline; example-style structure from §13; F0 + F1 from §5 | Opening proposal, lit-review §6, conference paper §1, `agent_logic_current.md`, `Downloads/example.pdf` for style | Pending |
| **B** | Thesis-quality prose for **Chapter 3 §3.1 (System Overview) + §3.3 (ARCD Model)** — lifts and tightens conference paper §3.1–§3.4 with locked decisions L3, L4, L7 applied | ~7 | §3 Chapter 3 outline rows §3.1, §3.3.1–§3.3.5; A1, A2; F2, F5, F6, F7, F8; T3 | Conference paper §3.1–§3.4, `arcd_agent/model/training/arcd_model.py`, CLAUDE.md v4–v6 notes | Pending |
| **C** | Thesis-quality prose for the **NEW chapters §3.8 (Student Twin) + §3.9 (Teacher Twin)** — the thesis-only content the conference paper does not have | ~6 | §3 Chapter 3 rows §3.8, §3.9; A7; F16, F17, F18, F19, F20; T7, T8 | `cognitive_diagnosis/service.py`, `teacher_digital_twin/service.py`, `COGNITIVE_DIAGNOSIS_AND_TEACHER_TWIN.md`, `agent_logic_current.md` | Pending |
| **D** | **Literature Review §2.6 (Educational Digital Twins)** — the new stream, drafted with reference slots and 5–10 candidate citations | ~1.5 | §3 Chapter 2 row §2.6 | New web research (the conference paper does not cover this stream); BibTeX entries added to `reference/main.bib` | Pending |
| **E** | A combined **Chapter 3 full draft** — overview + KG + ARCD + Orchestrator + 4 agents + 2 twins, lifted/expanded as appropriate | ~29 | All of §3 Chapter 3 rows; A1–A7; F2–F20; T2–T8 | All Methodology sources combined (B + C + agent prose) | Pending |
| **F** | The **updated thesis blueprint** (one-page master plan) reflecting all locked decisions, ready to share with your supervisor | ~1 | Distillation of §1, §2, §3, §13 into a single page | This blueprint document | Pending |

### How to invoke an option

1. **Single option** — say "produce option X" or "draft X". The output is committed to the corresponding `chapters/*.md` file.
2. **Stacked options** — say "produce A then F" to chain. Each is delivered separately so it can be reviewed before moving on.
3. **Re-request after revisions** — say "revise option X with: [feedback]" to regenerate.

### Recommended sequencing for the 10-week schedule (§7)

| Week | Recommended option(s) | Rationale |
|---|---|---|
| 0 (setup) | — | Phase 0 setup steps from §7 |
| 1–2 | **B** | Highest-volume content; lifts most directly from conference paper |
| 3 | (Phase 1 prose for §3.4–§3.7) | Agent prose drafted module-by-module |
| 4 | **C** | The thesis-only twin chapters; closes Methodology |
| 5 | **D** | New §2.6 stream during Related Work week |
| 5 | (Chapter 2 §2.1–§2.5 + §2.7 prose) | Lit-review refresh |
| 6 | **A** | Introduction last so it can reference the methodology already drafted |
| 7 | (Chapter 4 prose) | Implementation chapter |
| 8 | (Chapter 5 prose + experiments) | Results |
| 9 | **F** + (Chapter 6 prose) | One-page supervisor brief + conclusion |
| 10 | (Defense prep) | Phase 6 |

### Option dependency graph

```
F (one-pager) ─── independent, can be produced any time
A (Chapter 1) ─── depends on B, C, D being drafted first (so contributions in §1.4 can reference real subsection numbers)
B (overview + ARCD) ─── independent, can be produced first
C (twins) ─── depends on B (re-uses ARCD outputs as inputs)
D (lit review §2.6) ─── independent
E (full Ch 3) ─── = B + C + agent prose (use only if a single mega-deliverable is preferred over staged)
```

---

## 15. Open Questions to Resolve Before Phase 1

| # | Question | Decider | Needed by |
|---|---|---|---|
| Q1 | Is real-classroom pilot data accessible by Week 8? | Author + supervisor | end of Week 1 |
| Q2 | Are the Student Twin and Teacher Twin pilot studies IRB/ethics-cleared? | Author + supervisor | end of Week 4 |
| Q3 | Will the conference paper (`docs/thesis/sources/ARCD-Paper.pdf`) be cited as our own under review? If yes, self-cite; if not, treat methodology as thesis-original | Supervisor | Week 5 |
| Q4 | Final decision on Chinese abstract — translated by author or by school office? | Author | Week 6 |
| Q5 | Which deliverable from §14 to produce first? | Author | before next writing session |

---

**Blueprint locked. Ready to execute Phase 0.**
