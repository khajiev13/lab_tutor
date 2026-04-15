# Professor Framework to Actual Conference Paper

This note translates your professor's proposed paper framework into the actual paper you should write for the conference.

The goal is not to copy her framework word for word. The goal is to preserve her **research-story preference** while making the paper technically accurate to the system you actually built.

## 1. Main Reading of Your Professor's Intention

From the proposed framework, your professor seems to want a paper that is:

- problem-driven
- framework-oriented
- theoretically grounded
- innovation-focused
- aligned with the conference theme

She does **not** seem to want a paper that is mainly:

- a software engineering implementation report
- a notebook walkthrough
- a backend architecture document
- a long prompt-engineering explanation

So the paper should present the system as a **research framework and intelligent platform**, and then use your experiment as **evidence**.

## 2. The One-Sentence Story of the Paper

If we compress your professor's idea into one sentence, it becomes:

> Higher education lacks a scalable way to organize course knowledge, align it with textbook knowledge and industry skill demand, and recommend supporting resources; therefore, we propose a knowledge-graph-centric multi-agent platform and evaluate it through a Big Data course case study.

This is the paper's backbone.

## 3. What Your Professor Wants vs. What You Should Actually Write

## 3.1 Research Background and Problem Statement

### What your professor wants

She wants you to begin with three educational problems:

- fragmented teaching knowledge
- curriculum-industry mismatch
- high cost of resource construction

### What you should actually write

Keep these three problems exactly. They are strong and match your system well.

But write them more concretely:

- course materials are scattered across transcripts, slides, books, and other resources
- teachers have difficulty knowing which skills are currently demanded by industry
- manually choosing books and supplementary resources is slow and unsustainable

### What to avoid

Do not start with technical tools like Neo4j, LangGraph, DeepSeek, or embeddings. Those belong later.

## 3.2 Core Scientific Question

### What your professor wants

She wants one central research question:

> How can course knowledge be extracted, organized, aligned, and quality-assured in an intelligent curriculum resource construction system?

### What you should actually write

Keep this as the main question, but slightly sharpen it:

> How can a knowledge-graph-centric multi-agent system automatically organize course knowledge, align it with textbooks and labor-market skills, and support resource construction while preserving output quality through human review?

This keeps her intent while making it match your actual system.

## 3.3 Theoretical Foundations

### What your professor wants

She wants the paper grounded in:

- Knowledge Graph Theory
- Multi-Agent Coordination Theory
- Human-AI Collaborative Cognition Theory

### What you should actually write

Use all three, but keep this section short.

Recommended role of each theory:

- `Knowledge Graph Theory`: explains why knowledge should be represented as concepts, skills, and relations
- `Multi-Agent Coordination Theory`: explains why the workflow is split across specialized agents
- `Human-AI Collaborative Cognition Theory`: explains why teacher review is still needed at key checkpoints

### What to avoid

Do not let this become a literature dump. Theories should support the system design, not dominate the paper.

## 3.4 Three-Layer Model

### What your professor wants

She clearly wants the system described as a three-layer framework:

- Knowledge Foundation Layer
- Knowledge Alignment Layer
- Resource Application Layer

### What you should actually write

You should absolutely keep this structure. It is one of the strongest parts of her proposed framework.

Recommended interpretation:

- `Knowledge Foundation Layer`
  - transcript processing
  - course knowledge graph construction
  - concept normalization
- `Knowledge Alignment Layer`
  - textbook extraction and mapping
  - market skill extraction and mapping
  - curriculum-gap diagnosis
- `Resource Application Layer`
  - resource recommendation
  - personalized learning support
  - curriculum improvement support

This section should become your main system-overview section.

## 3.5 Core Research Content

Your professor divides the paper into four research contents. This is useful, but in the final conference paper you should simplify them into system modules.

### Her Research Content 1

> Course knowledge graph construction and quality assurance

### Your paper version

Write this as:

> Transcript-to-knowledge-graph construction with structured extraction, normalization, and review.

### Her Research Content 2

> Intelligent textbook discovery and curriculum alignment

### Your paper version

Write this as:

> Textbook discovery, textbook evaluation, and chapter-level knowledge injection into the curriculum graph.

### Her Research Content 3

> Dynamic industry demand perception and curriculum-skill alignment

### Your paper version

Write this as:

> Market-demand sensing and curriculum-to-job alignment analysis.

This is where your **Big Data experiment** belongs.

### Her Research Content 4

> Intelligent teaching resource curation and personalized recommendation

### Your paper version

Write this as:

> Resource recommendation and personalized skill-oriented learning support.

## 4. What the Actual Paper Should Look Like

Here is the version that best matches both your professor's opinion and your real system.

## 4.1 Recommended Final Outline

### 1. Introduction

Write:

- why curriculum-market mismatch matters
- why existing teaching resources are fragmented
- why manual resource construction is too expensive
- your contribution in one paragraph

End the introduction with 3 contributions.

Recommended contribution style:

1. We propose a knowledge-graph-centric multi-agent framework for intelligent curriculum resource construction.
2. We integrate transcript knowledge, textbook knowledge, market skills, and learning resources in a unified alignment pipeline.
3. We evaluate the framework through a Big Data course case study showing improved curriculum-to-market alignment.

### 2. Related Work

Cover only the categories you need:

- knowledge graphs in education
- AI agents in educational systems
- curriculum-industry alignment
- intelligent resource recommendation

Do not make this section too large.

### 3. Framework Overview

This section should follow your professor's preferred three-layer model.

Suggested subsections:

- `3.1 Knowledge Foundation Layer`
- `3.2 Knowledge Alignment Layer`
- `3.3 Resource Application Layer`
- `3.4 Human-AI Review Checkpoints`

### 4. System Realization

This is where you translate the framework into the actual system.

Suggested subsections:

- transcript knowledge extraction
- concept normalization
- textbook discovery and evaluation
- market skill extraction and mapping
- resource curation and recommendation

Do not go too deep into implementation details like route files or package names unless the conference is highly technical.

### 5. Case Study and Experimental Design

This is the experiment section.

Suggested subsections:

- `5.1 Big Data Course and Data Sources`
- `5.2 Curriculum Variants`
- `5.3 Held-Out Job Evaluation`
- `5.4 Metrics`

This is the section your professor's framework does not specify in enough detail, but your actual paper needs it.

### 6. Results

Suggested subsections:

- `6.1 Variant-Level Curriculum-to-Market Alignment`
- `6.2 Skill-Gap Closure Analysis`
- `6.3 Representative Cases`

### 7. Discussion and Limitations

Use this section to balance the paper.

Include:

- what the system contributes educationally
- what the current evaluation can and cannot prove
- why this is a case study, not a universal benchmark

### 8. Conclusion

Short and clean.

## 4.2 What to Put in the Results Section

Your professor's framework is broad, but the conference paper will need concrete evidence.

Use the experiment to support these claims:

- transcript-only curriculum has incomplete market alignment
- textbook and market enrichment improve alignment
- the full system gives the strongest result

Do not overload the results section with:

- chapter distribution heatmaps
- search-term diagnostic charts
- internal workflow diagrams

The main result visuals should stay focused on:

- variant-level improvement
- covered / partial / missing gap closure

## 5. How to Translate Her Framework into Your Actual Contributions

## 5.1 Contribution 1

Professor's language:

> knowledge graph-centric intelligent curriculum resource construction

Your actual paper language:

> a unified semantic framework that organizes transcripts, textbook skills, market skills, and resources around a course knowledge graph

## 5.2 Contribution 2

Professor's language:

> multi-agent coordination

Your actual paper language:

> a modular multi-agent workflow for textbook discovery, market alignment, and resource curation

## 5.3 Contribution 3

Professor's language:

> human-AI collaborative cognition

Your actual paper language:

> teacher-in-the-loop review at critical points such as textbook approval, concept normalization, and skill coverage verification

## 5.4 Contribution 4

Professor's language:

> resource application and personalized recommendation

Your actual paper language:

> downstream support for personalized skill development and resource recommendation based on the aligned curriculum graph

## 6. Where the Big Data Experiment Fits in Her Framework

Your professor's framework is broad enough that the experiment should not dominate the entire paper.

The Big Data case study should be presented as:

- the evaluation of the `Knowledge Alignment Layer`
- especially the curriculum-market alignment part
- with light connection to the `Resource Application Layer`

So the experiment is not the full paper.
It is the main empirical proof for one important part of the paper.

That is the right balance.

## 7. What Your Professor Probably Cares About Most

Reading her framework, the highest-priority values seem to be:

- clear educational problem
- strong conceptual structure
- explicit scientific questions
- identifiable innovation points
- visible conference-theme alignment

This means she will likely respond well if the paper:

- sounds academically organized
- makes the framework easy to understand
- names the innovation clearly
- shows one convincing experiment

She will likely care less about:

- exact low-level implementation mechanics
- backend module names
- code architecture details
- prompt wording internals

## 8. What You Should Simplify for the Conference Version

Your actual system is richer than what a conference paper can comfortably explain.

So simplify:

- backend engineering details
- full agent runtime details
- detailed API descriptions
- every review checkpoint
- every scoring formula if not necessary

Keep:

- framework
- modules
- experiment
- main results
- limitations

## 9. The Best Final Strategy

If we combine your professor's opinion with your actual system, the best conference paper strategy is:

1. Present the work as a **knowledge-graph-centric multi-agent educational framework**
2. Explain it using the **three-layer model**
3. Describe 3-4 main modules without too much engineering detail
4. Use the Big Data case study as the main empirical evidence
5. End with a careful discussion of educational value and limitations

## 10. Final Recommendation

If you want the paper to sound closest to what your professor is asking for, then the paper should feel like:

- **60% framework and research design**
- **25% concrete system realization**
- **15% experiment and results**

If you want it to sound closer to your actual implementation strength, then:

- **45% framework**
- **25% system realization**
- **30% experiment**

For a conference paper, I recommend the second balance:

- enough framework to satisfy your professor
- enough experiment to convince reviewers

## 11. Best Working Title

If you want a title close to your professor's thinking but still accurate to your system:

> A Knowledge Graph-Centric Multi-Agent Framework for Intelligent Curriculum Resource Construction and Curriculum-Market Alignment

If you want a shorter conference-style version:

> A Knowledge Graph-Centric Multi-Agent Framework for Intelligent Curriculum and Resource Alignment

## 12. Next Writing Step

The next best step is not to rewrite everything at once.

The next best step is:

1. lock the final paper outline
2. write the introduction around the three problems
3. write the three-layer framework section
4. write the Big Data experiment as the main empirical section
5. then refine language for conference style

That sequence matches your professor's structure and your actual system at the same time.
