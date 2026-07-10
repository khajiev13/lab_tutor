#!/usr/bin/env bash
# ICCSE2026 synthetic multi-resource benchmark ARCD retrain.
#
# Trains ARCD on the roma_synth_v6_2048 dataset with the post-baseline fix
# hyperparameters (focal_alpha=0.65 etc.) and writes outputs to
# checkpoints/<tag>/. Also automatically appends a row to
# checkpoints/inference_log.json (via arcd_train.py).
#
# Pre-flight checks before running:
#   1. No other ARCD training is using the MPS GPU:
#        ps -ef | grep -E "retrain_arcd_v2|arcd_train|iccse2026" | grep -v grep
#      Must be empty (besides this script's own processes).
#   2. Neo4j Aura is reachable (sourced from /Users/mohasani/LAB_ARCD_INTEGERATE/.env)
#
# Usage:
#   cd /Users/mohasani/LAB_ARCD_INTEGERATE/backend
#   bash scripts/iccse2026_synth_retrain.sh <tag>   # default tag if omitted: synth_v6_iccse2026_t1
#
# Outputs:
#   checkpoints/<tag>/best_model.pt
#   checkpoints/<tag>/training_history.json
#   checkpoints/<tag>/metrics_report.json
#   checkpoints/inference_log.json   (appended by arcd_train.py auto-logger)

set -euo pipefail

TAG="${1:-synth_v5_iccse2026_t1}"
# v5 has the same scale as v6 (1000 students, 7261 questions, 423 skills,
# 360 videos, 370 readings) and is the only synth dataset on disk with a
# complete mastery_ground_truth.parquet. v6 checkpoint dir is missing the
# mastery file, so we use v5 as the canonical multi-resource synthetic
# corpus for the ICCSE2026 retrain.
DATA_DIR="${2:-/Users/mohasani/LAB_ARCD_INTEGERATE/knowledge_graph_builder/data/synthgen/roma_synth_v5_1k_200k}"

BACKEND_DIR="/Users/mohasani/LAB_ARCD_INTEGERATE/backend"
PROJECT_ROOT="/Users/mohasani/LAB_ARCD_INTEGERATE"
OUT_DIR="${BACKEND_DIR}/checkpoints/${TAG}"
LOG_FILE="${OUT_DIR}.log"

cd "${BACKEND_DIR}"
mkdir -p "${OUT_DIR}"

# Source Neo4j credentials from the repo .env. The trainer needs LAB_TUTOR_NEO4J_*
# vars to fetch 2048-dim skill name_embedding initializers.
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
    set +a
fi

if [[ -z "${LAB_TUTOR_NEO4J_URI:-}" ]]; then
    echo "ERROR: LAB_TUTOR_NEO4J_URI not set after sourcing .env" >&2
    exit 1
fi

# Sanity check: nothing else holding MPS
if ps -ef | grep -E "(retrain_arcd_v2|arcd_train|iccse2026_(orchestrate|finetune))" | grep -v grep | grep -v "iccse2026_synth_retrain" >/dev/null; then
    echo "WARNING: another ARCD training process is active. Aborting to avoid MPS contention." >&2
    ps -ef | grep -E "(retrain_arcd_v2|arcd_train|iccse2026_(orchestrate|finetune))" | grep -v grep | grep -v "iccse2026_synth_retrain" >&2
    exit 2
fi

echo "Launching synthetic ARCD retrain"
echo "  tag       = ${TAG}"
echo "  data_dir  = ${DATA_DIR}"
echo "  out_dir   = ${OUT_DIR}"
echo "  neo4j_uri = ${LAB_TUTOR_NEO4J_URI}"
echo

# Default hyperparameters from arcd_train.py (already corrected for threshold
# collapse). Override here only if a tag-specific experiment is needed.
exec uv run python arcd_train.py \
    --data-dir "${DATA_DIR}" \
    --out-dir "${OUT_DIR}" \
    --epochs 80 \
    --batch-size 256 \
    --seq-len 50 \
    --stride 5 \
    --lr 1e-3 \
    --d 2048 \
    --d-skill 2048 \
    --n-gat-layers 2 \
    --n-attn-layers 2 \
    --patience 20 \
    --warmup-epochs 5 \
    --workers 8 \
    --bf16 \
    --focal-alpha 0.65 \
    --mastery-weight 0.1 \
    --rdrop-alpha 0.1 \
    --label-smoothing 0.05 \
    --dropout 0.2 \
    --student-emb-dropout 0.3 \
    --weight-decay 5e-4 \
    --seed 42 \
    2>&1 | tee "${LOG_FILE}"
