# Example Session: Polishing an Abstract

This document shows a complete session of polishing an abstract for an academic journal submission.

## Context

- **Paper**: Deep learning framework for medical image classification (Fictional Example)
- **Target Journal**: Example Journal (with ≤8,000 words, ≤250 words abstract)
- **Section**: Abstract

> **Note**: This is a fictional example created for demonstration purposes only. All research details, methods, and results are fabricated.

---

## Phase 0: Pre-Polish Baseline

**AI**: 
```
Before we start polishing, I need some information:
1. What is the target journal? Any special requirements?
2. Where are the example/reference papers?
3. Which section should we start with?
```

**User**: Target journal has 250-word abstract limit, examples in docs/example, start with abstract

**AI**: 
```
## Pre-Polish Checklist
- Target: Example Journal (≤8,000 words total, ≤250 words abstract)
- Example papers: docs/example/*.pdf
- Section: Abstract
- Current abstract word count: ~280 words (needs trimming)
```

---

## Step 1: Confirm Macro Structure

**AI**:
```markdown
## Abstract Structure Analysis

| Component | Function | Suggested Sentences |
|-----------|----------|---------------------|
| Background | Research importance | 1-2 |
| Gap | Existing limitations | 1-2 |
| Method | Proposed approach | 3-4 |
| Results | Key findings | 1-2 |
| Contribution | Significance | 1 |

Please confirm this structure, or describe adjustments needed.
```

**User**: The structure looks good. Confirm.

---

## Step 2: Confirm Per-Sentence Logic

**AI**:
```markdown
## Per-Sentence Logic Mapping

| Sentence | Logic Function | Key Points |
|----------|----------------|------------|
| S1 | Background | Medical imaging importance for clinical diagnosis |
| S2 | Data | Large-scale datasets enabling AI-based analysis |
| S3 | Gap | Current methods → limited interpretability → hard to trust → clinical adoption barrier |
| S4 | Method Overview | Hybrid framework: local features + global context |
| S5 | Method Detail | CNN extracts local patterns from image regions |
| S6 | Method Detail | Attention mechanism highlights diagnostic regions |
| S7 | Method Detail | Multi-scale fusion combines different resolution features |
| S8 | Method Detail | Interpretability module generates visual explanations |
| S9 | Results | Evaluated on benchmark datasets, achieves competitive accuracy |
| S10 | Contribution | Accuracy + interpretability + clinical applicability |

Please confirm each sentence's logic.
```

**User**: 
- S1: Confirm
- S2: Confirm  
- S3: Modify - emphasize that interpretability is essential for clinical trust
- S4-S8: Confirm
- S9: Confirm
- S10: Confirm

**AI**: Updated S3 logic to: "Current methods → limited interpretability (essential for clinical trust) → adoption barrier in real-world settings"

---

## Step 3: Confirm Specific Expressions

**AI** uses `mcp_question`:

```
┌─────────────────────────────────────────────────────────────┐
│ S1 Expression                                               │
│ ─────────────────────────────────────────────────────────── │
│ S1: Medical imaging importance for clinical diagnosis       │
│                                                             │
│ ○ A: Medical imaging plays a critical role in modern        │
│      clinical diagnosis, disease monitoring, and treatment  │
│      planning.                                              │
│                                                             │
│ ○ B: Advances in medical imaging have revolutionized        │
│      clinical practice, enabling non-invasive diagnosis     │
│      across specialties.                                    │
│                                                             │
│ ○ C: Accurate interpretation of medical images is           │
│      fundamental to clinical decision-making and patient    │
│      outcomes.                                              │
│                                                             │
│ ○ Type your own answer                                      │
└─────────────────────────────────────────────────────────────┘
```

**User selects**: A

```
┌─────────────────────────────────────────────────────────────┐
│ S2 Expression                                               │
│ ─────────────────────────────────────────────────────────── │
│ S2: Large-scale datasets enabling AI analysis               │
│                                                             │
│ ○ A: The availability of large-scale annotated datasets     │
│      has accelerated the development of AI-based diagnostic │
│      systems.                                               │
│                                                             │
│ ○ B: Deep learning methods have shown remarkable success    │
│      in automated image analysis, driven by growing data    │
│      availability.                                          │
│                                                             │
│ ○ C: Recent advances in deep learning, combined with        │
│      large medical imaging datasets, have enabled automated │
│      diagnostic tools.                                      │
│                                                             │
│ ○ Type your own answer                                      │
└─────────────────────────────────────────────────────────────┘
```

**User selects**: C

*(Process continues for all sentences...)*

---

## Step 4: Reference Paper Consultation

**User**: "Is 'clinical decision-making and patient outcomes' the right terminology?"

**AI** analyzes example papers:

```markdown
## Reference Paper Patterns

| Paper | Opening Phrase | Pattern |
|-------|---------------|---------|
| Paper 1 | "diagnosis and treatment planning" | task-focused |
| Paper 2 | "clinical workflow and patient care" | process-focused |
| Paper 3 | "diagnostic accuracy and efficiency" | outcome-focused |
| Paper 4 | "clinical practice and decision support" | application-focused |

## Suggested Alternatives

| Option | Expression |
|--------|------------|
| A | clinical decision-making and patient outcomes |
| B | diagnostic accuracy and clinical efficiency |
| C | clinical workflow and patient care |
| D | clinical decision-making and patient outcomes (keep original) |
```

**User selects**: D (keep original)

---

## Step 5: Repetition & Coherence Check

**AI**:
```markdown
## Repetition Check

| Location | Issue | Suggestion |
|----------|-------|------------|
| S4 vs S10 | Both mention "interpretability" | Rephrase S4 to "explainable predictions" |

## Coherence Check

| Location | Issue | Suggestion |
|----------|-------|------------|
| S3→S4 | Abrupt transition from gap to method | Add transition word |
```

**AI** uses `mcp_question` for transition:

```
┌─────────────────────────────────────────────────────────────┐
│ Transition Word                                             │
│ ─────────────────────────────────────────────────────────── │
│ S3→S4 transition: From 'problem' to 'solution'              │
│                                                             │
│ ○ A: "To address these limitations, this study..."          │
│ ○ B: "In response, this study..."                           │
│ ○ C: "To bridge this gap, we..."                            │
│ ○ D: Keep as is (no transition)                             │
└─────────────────────────────────────────────────────────────┘
```

**User selects**: A

---

## Final Version

**AI**:
```markdown
## Final Abstract

Medical imaging plays a critical role in modern clinical diagnosis, 
disease monitoring, and treatment planning. Recent advances in deep 
learning, combined with large medical imaging datasets, have enabled 
automated diagnostic tools. However, existing methods often lack 
interpretability, which is essential for clinical trust and limits 
their adoption in real-world settings. To address these limitations, 
this study introduces a hybrid framework combining local feature 
extraction with global context modeling. The framework employs 
convolutional neural networks to extract local patterns from image 
regions, while an attention mechanism highlights diagnostically 
relevant areas. Multi-scale feature fusion integrates information 
across resolutions, and an interpretability module generates visual 
explanations for predictions. We evaluate the framework on multiple 
benchmark datasets, achieving competitive accuracy while providing 
clinician-friendly explanations. The framework advances both 
diagnostic accuracy and interpretability, supporting practical 
clinical deployment.

**Word Count**: ~150 words ✅ (within 250 limit)

Confirm to write to file?
```

**User**: Yes

**AI**: ✅ Written to `docs/paper/sections/00_abstract_polished.md`

---

## Summary

| Step | Action | User Input |
|------|--------|------------|
| Phase 0 | Collect requirements | Journal specs, docs/example |
| Step 1 | Confirm structure | Confirmed |
| Step 2 | Confirm sentence logic | Modified S3 |
| Step 3 | Select expressions | A, C, B, B, ... |
| Step 4 | Reference consultation | Keep original |
| Step 5 | Coherence check | Added transition |
| Write | Final confirmation | Yes |

**Total conversation turns**: ~15
**Time saved**: Systematic approach avoids back-and-forth revisions
