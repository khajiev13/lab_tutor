# ARCD Inference Service

A lightweight Flask HTTP service that wraps the trained `ARCDModel` for real-time
student knowledge tracing inference.

## Quick start

```bash
cd backend

# 1 – Start the service (defaults to port 8000, reads roma_synth_v6_2048 checkpoint)
ARCD_CHECKPOINT_DIR=checkpoints/roma_synth_v6_2048 \
    uv run python -m app.modules.arcd_serving.run --port 8000

# 2 – Run the test client (separate terminal)
uv run python -m app.modules.arcd_serving.test_client \
    --base-url http://localhost:8000 \
    --n-students 20 \
    --data-dir ../knowledge_graph_builder/data/synthgen/<run_id>
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ARCD_CHECKPOINT_DIR` | `backend/checkpoints/roma_synth_v6_2048` | Directory with `best_model.pt` and `vocab.json` |

---

## Loading the model standalone (no Flask)

```python
from pathlib import Path
from app.modules.arcd_agent.model_registry import ModelRegistry

registry = ModelRegistry.from_dir(Path("checkpoints/roma_synth_v1"))

# Check readiness
print(registry.is_available)   # True
print(registry.best_val_auc)   # e.g. 0.7183

# Predict per-skill mastery
mastery = registry.predict_mastery(
    interactions=[
        {"question_name": "Q_42", "correct": 1, "timestamp_sec": 0},
        {"question_name": "Q_17", "correct": 0, "timestamp_sec": 60},
    ],
    concept_names=["concept_5", "concept_12"],
)
# {"concept_5": 0.631, "concept_12": 0.478}

# Predict P(correct) for candidate questions
p_map = registry.predict_correctness(
    interactions=[{"question_name": "Q_42", "correct": 1, "timestamp_sec": 0}],
    target_questions=["Q_100", "Q_200", "Q_300"],
)
# {"Q_100": 0.72, "Q_200": 0.41, "Q_300": 0.55}
```

---

## API endpoints

### `GET /health`

Liveness probe. Always returns `200`.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "checkpoint_loaded": true,
  "model_version": "arcd_v2_model",
  "best_val_auc": 0.7183
}
```

---

### `GET /info`

Returns vocabulary metadata.

```bash
curl http://localhost:8000/info
```

```json
{
  "n_skills": 229,
  "n_questions": 1999,
  "n_students": 4000,
  "concept_names": ["concept_0", "concept_1", "..."],
  "device": "cpu"
}
```

---

### `POST /mastery`

Predict per-skill mastery for one student.

```bash
curl -X POST http://localhost:8000/mastery \
  -H "Content-Type: application/json" \
  -d '{
    "interactions": [
      {"question_name": "Q_42",  "correct": 1, "timestamp_sec": 0},
      {"question_name": "Q_17",  "correct": 0, "timestamp_sec": 60},
      {"question_name": "Q_101", "correct": 1, "timestamp_sec": 120}
    ],
    "concept_names": ["concept_5", "concept_12", "concept_33"],
    "seq_len": 50
  }'
```

```json
{
  "mastery": {
    "concept_5":  0.631,
    "concept_12": 0.478,
    "concept_33": 0.712
  }
}
```

**Request fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `interactions` | array | yes | `[{question_name, correct, timestamp_sec}]` |
| `concept_names` | array of str | no | Skills to return (defaults to all skills) |
| `seq_len` | int | no | Context window length, default 50 |

---

### `POST /predict`

Predict P(correct) for each target question.

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "interactions": [
      {"question_name": "Q_42", "correct": 1, "timestamp_sec": 0}
    ],
    "target_questions": ["Q_100", "Q_200", "Q_300"]
  }'
```

```json
{
  "predictions": [
    {"question_name": "Q_100", "p_correct": 0.721},
    {"question_name": "Q_200", "p_correct": 0.413},
    {"question_name": "Q_300", "p_correct": 0.551}
  ]
}
```

---

### `POST /next-question`

Recommend the next question to present from a candidate pool.

Default strategy `max_uncertainty`: picks the question closest to P(correct)=0.5,
maximising expected information gain under a 1-PL IRT model.

```bash
curl -X POST http://localhost:8000/next-question \
  -H "Content-Type: application/json" \
  -d '{
    "interactions": [
      {"question_name": "Q_42", "correct": 1, "timestamp_sec": 0},
      {"question_name": "Q_17", "correct": 0, "timestamp_sec": 60}
    ],
    "candidate_questions": ["Q_5", "Q_9", "Q_14", "Q_22", "Q_88"],
    "strategy": "max_uncertainty",
    "seq_len": 50
  }'
```

```json
{
  "recommended_question": "Q_14",
  "p_correct": 0.503,
  "alternatives": [
    {"question_name": "Q_88", "p_correct": 0.461},
    {"question_name": "Q_22", "p_correct": 0.589},
    {"question_name": "Q_5",  "p_correct": 0.712},
    {"question_name": "Q_9",  "p_correct": 0.821}
  ]
}
```

---

## Swapping checkpoints

Set the environment variable before starting the service:

```bash
# After a new training run
ARCD_CHECKPOINT_DIR=checkpoints/roma_synth_v1_reg \
    uv run python -m app.modules.arcd_serving.run --port 8000
```

The checkpoint directory must contain:
- `best_model.pt` — model weights + config dict (saved by `arcd_train.py`)
- `vocab.json` — vocabulary mapping (saved by `synthgen`)

---

## Production deployment

For production, use **Gunicorn** instead of the built-in Flask server:

```bash
pip install gunicorn
ARCD_CHECKPOINT_DIR=checkpoints/roma_synth_v6_2048 \
    gunicorn "app.modules.arcd_serving:create_app()" \
    --workers 1 --threads 4 \
    --bind 0.0.0.0:8000
```

Use a single worker (model is not fork-safe with MPS/CUDA) and multiple threads for
concurrent requests. The model is CPU-only at inference time (uses `map_location="cpu"`).

---

## Model performance

| Checkpoint | Val AUC | Mean mastery | Notes |
|---|---|---|---|
| `roma_synth_v6_2048` | **0.6420** | 0.49 (0.29–0.69) | Current default — 423 skills, 2048-dim, focal-alpha=0.25 |

## Swapping to a new checkpoint (after training completes)

```bash
ARCD_CHECKPOINT_DIR=checkpoints/<new_run_id> \
    uv run python -m app.modules.arcd_serving.run --port 9001 &

uv run python -m app.modules.arcd_serving.test_client \
    --base-url http://127.0.0.1:9001 \
    --n-students 20 \
    --data-dir ../knowledge_graph_builder/data/synthgen/<new_run_id>
```
