# ARCD Synthetic-Data Validation Report
**Date:** 2026-04-17  
**Author:** automated (ARCD validation pipeline)  
**Run ID:** `roma_synth_v1`

---

## 1. Scope

This report documents the end-to-end execution of the ARCD synthetic-data validation
pipeline, covering data generation, model training, mastery inference, and quality
assessment for the Lab Tutor project.

The test fixture targets the teacher node **Roma** and 1 000 synthetic students.

---

## 2. Synthetic Data Generation (Phase 1)

| Metric | Value |
|---|---|
| Target students | 1 000 |
| Students written to Postgres | 1 000 |
| Target interactions | 500 000 |
| **Interactions generated** | **164 098** |
| Train split | 131 278 (80 %) |
| Test split | 32 820 (20 %) |
| Unique questions exercised | 1 798 of 1 999 |
| Unique skills covered | 229 |
| Correct-answer rate (train) | 62.0 % |
| Correct-answer rate (test) | 61.6 % |
| IRT GT mastery mean ± std | 0.24 ± 0.34 |

### Why interactions fell short of 500 k

The cloud Neo4j Aura free tier enforces a **400 000-relationship hard cap**.  
After writing ≈ 212 k `ANSWERED` edges and ≈ 175 k `MASTERED` edges the
server rejected further writes.  All 164 k interaction records, the mastery
ground truth, and the vocabulary were persisted to **Parquet files**,
which were used for training without loss of data.

Every synthetic node/edge carries `{synthetic: true, run_id: "roma_synth_v1"}`.

---

## 3. Model Training (Phase 2)

Training was run on a CPU with the `backend/arcd_train.py` CLI:

```
uv run python arcd_train.py \
  --data-dir ../knowledge_graph_builder/data/synthgen/roma_synth_v1 \
  --output-dir checkpoints/synthgen \
  --epochs 50 \
  --batch-size 64 \
  --seq-len 50 \
  --hidden-dim 64
```

### Training history (11 epochs until early-stopping)

| Epoch | train_loss | val_loss | train_AUC | val_AUC | LR |
|---|---|---|---|---|---|
| 1 | 0.0872 | 0.0842 | 0.506 | **0.512** | 1.0e-3 |
| 2 | 0.0814 | 0.0891 | 0.511 | 0.490 | 9.8e-4 |
| 3 | 0.0809 | 0.0894 | 0.510 | 0.491 | 9.0e-4 |
| 4 | 0.0807 | 0.0875 | 0.521 | 0.484 | 7.9e-4 |
| 5 | 0.0806 | 0.0860 | 0.522 | 0.496 | 6.5e-4 |
| 6 | 0.0805 | 0.0856 | 0.524 | 0.493 | 5.0e-4 |
| 7 | 0.0804 | 0.0852 | 0.529 | 0.500 | 3.5e-4 |
| 8 | 0.0804 | 0.0851 | 0.531 | 0.501 | 2.1e-4 |
| 9 | 0.0804 | 0.0852 | 0.529 | 0.501 | 9.6e-5 |
| 10 | 0.0804 | 0.0853 | 0.525 | 0.499 | 2.5e-5 |
| 11 | 0.0803 | 0.0857 | 0.539 | 0.501 | 1.0e-3 |

Best checkpoint saved at **epoch 1** (`val_AUC = 0.5116`).  
Early stopping triggered after 10 non-improving epochs (patience = 10).

### Full MetricsSuite on held-out test set

| Metric | Value | Interpretation |
|---|---|---|
| AUC-ROC | **0.512** | ≈ random (0.5 baseline) |
| PR-AUC | 0.629 | inflated by class imbalance |
| Accuracy | 0.383 | predicts majority class |
| Balanced Accuracy | 0.500 | random |
| F1 | 0.000 | model never predicts "incorrect" |
| Precision | 0.000 | — |
| Recall | 0.000 | — |
| Specificity | 1.000 | always predicts "correct" |
| RMSE | 0.515 | high |
| Log Loss | 0.724 | high |
| Brier Score | 0.266 | high |
| ECE | 0.171 | poorly calibrated |
| MCC | 0.000 | no signal |
| Calibration slope | 0.563 | under-confident (flat) |

---

## 4. Mastery Inference & Dashboard Validation (Phases 3 & 4)

`backend/batch_mastery_recompute.py` ran inference on all 1 000 students and
wrote predicted `MASTERED` edges to Neo4j.

| Metric | Value |
|---|---|
| Students processed | 1 000 |
| Inference time | 5.3 s (≈ 190 students/s) |
| Neo4j MASTERED edges written | 229 000 |
| Avg predicted mastery | 0.137 |
| Std predicted mastery | 0.004 |
| RMSE vs IRT ground truth | **0.345** |
| Pearson-r vs IRT ground truth | **0.001** |

The model outputs near-constant mastery (~14 %) for all 1 000 students
regardless of their actual IRT ability — confirming that no signal was learned.

### Dashboard API endpoints validated

| Endpoint | Status |
|---|---|
| `GET /api/cognitive-diagnosis/mastery/{uid}` | served (heuristic or model) |
| `GET /api/cognitive-diagnosis/path/{uid}/{cid}` | served |
| `GET /api/cognitive-diagnosis/arcd-portfolio/{uid}/{cid}` | served |
| `GET /api/cognitive-diagnosis/arcd-twin/{uid}/{cid}` | served |

`ModelRegistry` integration (Phase 3) is wired into `CognitiveDiagnosisService`
with a transparent fallback to the heuristic when the model is unavailable or
raises an exception.

---

## 5. Root-Cause Analysis: Why the Model Did Not Learn

### 5.1 Too Few Interactions

| Target | Achieved | Gap |
|---|---|---|
| 500 000 | 164 098 | −67 % |

With 164 interactions per student on average (vs. 500 targeted), the temporal
attention model has very short sequences to learn from.

### 5.2 Knowledge-Tracing Objective vs. Static IRT Ground Truth

The ARCD model is trained to **predict the next answer** (KT objective).
The evaluation metric — Pearson-r between predicted mastery and IRT static mastery
— is a regression task the model was never directly optimised for.
AUC of 0.51 shows even the KT objective was not learned, but the mismatch
between objectives makes the mastery regression especially poor.

### 5.3 Very Short Training (11 Epochs, CPU Only)

Eleven epochs on 131 k interactions is insufficient.  The `CosineAnnealingWarmRestarts`
scheduler completed only one warm-up cycle before early-stopping fired.  GPU
training for 100+ epochs is required for this architecture.

### 5.4 Class Imbalance Not Compensated

62 % of interactions are "correct".  The model collapsed to always predicting
"correct" (Recall = 0, Specificity = 1.0).  FocalLoss (alpha = 0.25) was
intended to address this but the imbalance was not severe enough to trigger
meaningful gradient signal.

### 5.5 Synthetic Knowledge Graph is Shallow

The real-project KG contains rich prerequisite chains (`REQUIRES`/`RELATED_TO`)
between skills.  The synthetic questions added by `synthgen` lack these edges.
The GCN component therefore produces near-identical skill embeddings, removing
one of the model's key learning signals.

### 5.6 IRT Ability Distribution May Be Too Narrow

`theta_mu = 1.4`, `theta_std = 0.8` — the distribution is shifted towards
high-ability students (62 % correct rate).  A wider or centred distribution
(e.g., `theta_mu = 0`, `theta_std = 1.5`) would produce more discriminating
interactions (50 % correct rate) that better challenge the model.

---

## 6. Recommendations for Improvement

### Immediate (data pipeline)

| # | Action | Expected Impact |
|---|---|---|
| 1 | **Lift the Neo4j relationship cap** (upgrade Aura tier or use self-hosted Neo4j) | Enables the full 500 k interaction graph, unlocking richer GCN signal |
| 2 | **Shift IRT ability parameters**: `theta_mu = 0`, `theta_std = 1.5` | Produces ≈ 50 % correct rate → more balanced, informative interactions |
| 3 | **Add `REQUIRES` prerequisite edges** for synthetic skills in `kg_extraction.py` | Enables GCN to produce differentiated skill embeddings |
| 4 | **Increase `seq_len` from 50 to 200** | Makes better use of long interaction histories |

### Model training

| # | Action | Expected Impact |
|---|---|---|
| 5 | **Train on GPU for ≥ 100 epochs** | AUC typically reaches 0.70–0.80 on KT tasks with sufficient compute |
| 6 | **Use linear warm-up (5 epochs)** before cosine decay | Stabilises early training, prevents the model from converging on majority class |
| 7 | **Increase `mastery_weight` in `ARCDLoss`** (0.05 → 0.2) | Directly penalises wrong mastery predictions during training |
| 8 | **Use oversampling or `alpha=0.75`** in FocalLoss | Compensates for 62 % "correct" class imbalance |

### Architecture

| # | Action | Expected Impact |
|---|---|---|
| 9 | **Add student embedding lookup** (the model has one but `n_students=1000` was used with random interactions) | Provides persistent per-student state |
| 10 | **Increase `hidden_dim` from 64 → 128** once GPU is available | More capacity for complex skill-mastery mappings |

### Validation harness

| # | Action | Expected Impact |
|---|---|---|
| 11 | **Report next-answer AUC** (KT metric) alongside mastery-RMSE | Aligns the evaluation metric with the training objective |
| 12 | **Add `pytest` integration test** that runs `arcd_train.py` on a 50-student subset and asserts `val_AUC > 0.55` | Prevents regressions in the training pipeline |
| 13 | **Automate dashboard smoke tests** using `httpx` + an active FastAPI test client | Enables CI-level dashboard regression checks |

---

## 7. Files Produced

| File | Description |
|---|---|
| `knowledge_graph_builder/synthgen/` | Modular synthetic-data package |
| `knowledge_graph_builder/data/synthgen/roma_synth_v1/train.parquet` | 131 278-row training split |
| `knowledge_graph_builder/data/synthgen/roma_synth_v1/test.parquet` | 32 820-row test split |
| `knowledge_graph_builder/data/synthgen/roma_synth_v1/mastery_ground_truth.parquet` | IRT mastery per (student, skill) |
| `knowledge_graph_builder/data/synthgen/roma_synth_v1/vocab.json` | Entity → index mappings |
| `backend/arcd_train.py` | Training CLI |
| `backend/checkpoints/synthgen/best_model.pt` | Best model checkpoint |
| `backend/checkpoints/synthgen/metrics_report.json` | MetricsSuite evaluation |
| `backend/checkpoints/synthgen/training_history.json` | Per-epoch loss/AUC |
| `backend/app/modules/arcd_agent/model_registry.py` | Model loading & inference singleton |
| `backend/batch_mastery_recompute.py` | Phase 4 batch inference script |

---

## 8. Cleanup

No dedicated synthgen cleanup command is maintained in the repository.
