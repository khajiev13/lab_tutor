"""ARCD serving test client.

Loads N students from test.parquet, exercises all 5 API endpoints, and
reports per-student AUC + request latency.

Usage
-----
    cd backend
    # Start the service first:
    #   ARCD_CHECKPOINT_DIR=checkpoints/roma_synth_v1 \\
    #       uv run python -m arcd_serving.run --port 8000

    uv run python -m arcd_serving.test_client \\
        --base-url http://localhost:8000 \\
        --n-students 20 \\
        --data-dir ../knowledge_graph_builder/data/synthgen/roma_synth_v2_80pct
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ── Helpers ───────────────────────────────────────────────────────────────────

def _auc_from_scores(y_true: list[int], y_score: list[float]) -> float:
    """Compute ROC-AUC without sklearn (trapezoidal rule)."""
    if len(set(y_true)) < 2:
        return float("nan")
    pairs = sorted(zip(y_score, y_true, strict=False), key=lambda x: -x[0])
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    tp = fp = auc = prev_tp = prev_fp = 0.0
    for _score, label in pairs:
        if label:
            tp += 1
        else:
            fp += 1
        if fp != prev_fp:
            auc += (fp - prev_fp) / n_neg * (tp + prev_tp) / 2 / n_pos
            prev_tp, prev_fp = tp, fp
    auc += (n_neg - prev_fp) / n_neg * (n_pos + prev_tp) / 2 / n_pos
    return float(auc)


def _post(url: str, payload: dict) -> tuple[dict, float]:
    """POST JSON, return (response_json, latency_ms)."""
    t0 = time.perf_counter()
    resp = requests.post(url, json=payload, timeout=30, proxies={"http": None, "https": None})
    latency_ms = (time.perf_counter() - t0) * 1000
    resp.raise_for_status()
    return resp.json(), latency_ms


def _get(url: str) -> tuple[dict, float]:
    t0 = time.perf_counter()
    resp = requests.get(url, timeout=10, proxies={"http": None, "https": None})
    latency_ms = (time.perf_counter() - t0) * 1000
    resp.raise_for_status()
    return resp.json(), latency_ms


# ── Main ──────────────────────────────────────────────────────────────────────

def run(base_url: str, data_dir: Path, n_students: int, history_frac: float) -> None:
    base_url = base_url.rstrip("/")

    # ── 1. GET /health ────────────────────────────────────────────────────────
    print("── GET /health ──")
    health, lat = _get(f"{base_url}/health")
    print(f"   status={health['status']}  checkpoint_loaded={health['checkpoint_loaded']}")
    print(f"   model_version={health['model_version']}  best_val_auc={health['best_val_auc']:.4f}")
    print(f"   latency={lat:.1f} ms\n")

    if not health["checkpoint_loaded"]:
        print("ERROR: model not loaded — check ARCD_CHECKPOINT_DIR", file=sys.stderr)
        sys.exit(1)

    # ── 2. GET /info ──────────────────────────────────────────────────────────
    print("── GET /info ──")
    info, lat = _get(f"{base_url}/info")
    print(f"   n_skills={info['n_skills']}  n_questions={info['n_questions']}  "
          f"n_students={info['n_students']}")
    print(f"   first 5 concepts: {info['concept_names'][:5]}")
    print(f"   latency={lat:.1f} ms\n")

    all_concept_names: list[str] = info["concept_names"]

    # ── 3. Load test.parquet and vocab.json ───────────────────────────────────
    parquet_path = data_dir / "test.parquet"
    vocab_path   = data_dir / "vocab.json"

    if not parquet_path.exists():
        print(f"ERROR: {parquet_path} not found", file=sys.stderr)
        sys.exit(1)

    df = pd.read_parquet(parquet_path)
    print(f"Loaded test.parquet  rows={len(df):,}  cols={list(df.columns)[:8]}")

    with open(vocab_path) as f:
        vocab = json.load(f)

    q_idx_to_name: dict[int, str] = {v: k for k, v in vocab.get("question", {}).items()}
    user_col   = "user_idx" if "user_idx" in df.columns else (
                 "student_idx" if "student_idx" in df.columns else "student_id"
             )
    q_col      = "question_idx" if "question_idx" in df.columns else "question_id"
    corr_col   = "correct"
    ts_col     = "timestamp_sec" if "timestamp_sec" in df.columns else "timestamp"

    # Pick N random students.
    all_users = df[user_col].unique()
    rng_users = all_users[:n_students]
    print(f"Evaluating {len(rng_users)} students  (history_frac={history_frac:.0%})\n")

    # ── Per-student evaluation ─────────────────────────────────────────────────
    aucs: list[float] = []
    lat_mastery:   list[float] = []
    lat_predict:   list[float] = []
    lat_next_q:    list[float] = []
    n_errors = 0

    for uid in rng_users:
        rows = df[df[user_col] == uid].sort_values(ts_col if ts_col in df.columns else q_col)

        interactions_raw = [
            {
                "question_name": q_idx_to_name.get(int(row[q_col]), f"Q_{row[q_col]}"),
                "correct": int(row[corr_col]),
                "timestamp_sec": float(row[ts_col]) if ts_col in df.columns else float(i),
            }
            for i, (_, row) in enumerate(rows.iterrows())
        ]

        split = max(1, int(len(interactions_raw) * history_frac))
        history   = interactions_raw[:split]
        held_out  = interactions_raw[split:]

        if not held_out:
            continue

        held_out_names = [h["question_name"] for h in held_out]
        y_true = [h["correct"] for h in held_out]

        try:
            # POST /mastery
            _, lm = _post(f"{base_url}/mastery", {
                "interactions": history,
                "concept_names": all_concept_names[:10],
            })
            lat_mastery.append(lm)

            # POST /predict
            pred_resp, lp = _post(f"{base_url}/predict", {
                "interactions": history,
                "target_questions": held_out_names,
            })
            lat_predict.append(lp)

            p_map = {d["question_name"]: float(d["p_correct"])
                     for d in pred_resp.get("predictions", [])}
            y_score = [p_map.get(q, 0.5) for q in held_out_names]
            auc = _auc_from_scores(y_true, y_score)
            if auc == auc:  # skip NaN
                aucs.append(auc)

            # POST /next-question (10 random candidates from held-out)
            candidates = held_out_names[:10]
            _, ln = _post(f"{base_url}/next-question", {
                "interactions": history,
                "candidate_questions": candidates,
            })
            lat_next_q.append(ln)

        except Exception as exc:  # noqa: BLE001
            print(f"   !! student {uid}: {exc}")
            n_errors += 1

    # ── Summary ────────────────────────────────────────────────────────────────
    def _stats(vals: list[float]) -> str:
        if not vals:
            return "n/a"
        p50 = statistics.median(vals)
        p95 = sorted(vals)[max(0, int(len(vals) * 0.95) - 1)]
        return f"p50={p50:.1f} ms  p95={p95:.1f} ms"

    print("\n" + "═" * 60)
    print("RESULTS")
    print("═" * 60)
    print(f"  Students evaluated : {len(aucs)} / {len(rng_users)}")
    if aucs:
        mean_auc = statistics.mean(aucs)
        stdev_auc = statistics.stdev(aucs) if len(aucs) > 1 else 0.0
        print(f"  Mean per-student AUC  : {mean_auc:.4f} ± {stdev_auc:.4f}")
    else:
        print("  Mean per-student AUC  : n/a")
    print(f"  Errors                : {n_errors}")
    print(f"  /mastery  latency     : {_stats(lat_mastery)}")
    print(f"  /predict  latency     : {_stats(lat_predict)}")
    print(f"  /next-q   latency     : {_stats(lat_next_q)}")
    print("═" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ARCD test client — exercises all API endpoints against test.parquet",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="Flask service URL"
    )
    parser.add_argument(
        "--n-students", type=int, default=20, help="Number of students to evaluate"
    )
    parser.add_argument(
        "--data-dir",
        default="../knowledge_graph_builder/data/synthgen/roma_synth_v2_80pct",
        help="Directory containing test.parquet and vocab.json",
    )
    parser.add_argument(
        "--history-frac",
        type=float,
        default=0.8,
        help="Fraction of interactions to use as history (rest = held-out targets)",
    )
    args = parser.parse_args()

    run(
        base_url=args.base_url,
        data_dir=Path(args.data_dir),
        n_students=args.n_students,
        history_frac=args.history_frac,
    )


if __name__ == "__main__":
    main()
