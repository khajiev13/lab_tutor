"""ICCSE2026 synthetic multi-resource benchmark ARCD orchestrator.

Mirrors the XES3G5M wave-style fine-tuning strategy on the synthetic
multi-resource corpus. Each trial:
  * trains via arcd_train.py for at most 50 epochs with patience=10
  * uses bf16 on MPS so the d=2048 model fits in budget
  * writes to checkpoints/<tag>/ and auto-appends to checkpoints/inference_log.json
  * is followed by a brief overfitting check (train_loss falling while
    val_loss rising) printed to stdout

Trials (all at 50 epochs, patience=10):
  S1_base           — corrected baseline (focal=0.65, dropout=0.2, lr=1e-3)
  S2_antioverfit    — heavier regularization (dropout=0.3, wd=2e-3, lr=5e-4)
  S3_lower_focal    — calibration tilt (focal=0.50, mastery=0.05)

Pre-flight: refuses to launch if any ARCD training is already on MPS.

Usage:
    cd /Users/mohasani/LAB_ARCD_INTEGERATE/backend
    source /Users/mohasani/LAB_ARCD_INTEGERATE/.env  # for LAB_TUTOR_NEO4J_*
    uv run python scripts/iccse2026_synth_orchestrate.py
    uv run python scripts/iccse2026_synth_orchestrate.py --tags S1_base S2_antioverfit
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
DATA_DIR_DEFAULT = (
    ROOT / "knowledge_graph_builder" / "data" / "synthgen" / "roma_synth_v5_1k_200k"
)


TRIALS: dict[str, dict[str, str]] = {
    "S1_base": {
        # Corrected baseline. Uses every default from arcd_train.py
        # (focal=0.65, dropout=0.2, lr=1e-3, weight_decay=5e-4, rdrop=0.1,
        #  label_smoothing=0.05, mastery=0.1), 50 epochs / patience=10.
        # Goal: establish a clean post-baseline-fix reference point.
        "rationale": "Corrected baseline with threshold-collapse hyperparameter fix; reference for the other trials.",
    },
    "S2_antioverfit": {
        "dropout": "0.30",
        "weight-decay": "2e-3",
        "lr": "5e-4",
        "student-emb-dropout": "0.40",
        "rationale": "Heavier regularization in case S1 overfits the 200k-event dataset with d=2048.",
    },
    "S3_lower_focal": {
        "focal-alpha": "0.50",
        "mastery-weight": "0.05",
        "rdrop-alpha": "0.05",
        "rationale": "Less aggressive minority-class re-weighting; cleaner calibration if S1 still shows overconfidence.",
    },
}


def already_training() -> str | None:
    """Return a descriptive string if anything ARCD-ish is on the GPU, else None."""
    try:
        out = subprocess.check_output(["ps", "-ef"], text=True, timeout=5)
    except Exception:
        return None
    patterns = [
        "arcd_train",
        "retrain_arcd_v2",
        "iccse2026_finetune",
        "iccse2026_orchestrate",
    ]
    for line in out.splitlines():
        if "iccse2026_synth_orchestrate" in line:
            continue
        if any(p in line for p in patterns):
            return line.strip()
    return None


def overfit_diag(history_path: Path) -> str:
    """Return a one-line diagnosis: are val_loss and train_loss diverging?"""
    if not history_path.exists():
        return "no history file"
    try:
        history = json.loads(history_path.read_text())
    except Exception as exc:
        return f"unreadable history ({exc})"
    train = history.get("train_loss", [])
    val = history.get("val_loss", [])
    val_auc = history.get("val_auc", [])
    if not train or not val:
        return "empty loss arrays"
    n = len(train)
    if n < 4:
        return f"only {n} epoch(s) — too short for diagnosis"
    # Compare second-half slopes
    mid = n // 2
    train_drop = train[mid - 1] - train[-1]
    val_drop = val[mid - 1] - val[-1]
    train_dir = "↓" if train_drop > 0 else "↑"
    val_dir = "↓" if val_drop > 0 else "↑"
    best_auc = max(val_auc) if val_auc else float("nan")
    best_ep = (val_auc.index(best_auc) + 1) if val_auc else -1
    final_auc = val_auc[-1] if val_auc else float("nan")
    diag = (
        f"epochs={n} | best_val_auc={best_auc:.4f}@ep{best_ep} | "
        f"final_val_auc={final_auc:.4f} | "
        f"second-half train_loss {train_dir} {abs(train_drop):.4f}, val_loss {val_dir} {abs(val_drop):.4f}"
    )
    # Overfit flag
    if train_drop > 0.005 and val_drop < -0.005:
        diag += "  [OVERFITTING: train↓ val↑]"
    elif (best_ep - 1) < n - 5 and (best_ep - 1) > 0:
        diag += f"  [PLATEAU: best was {n - best_ep} epochs ago]"
    return diag


def run_trial(tag: str, cfg: dict, args: argparse.Namespace) -> tuple[int, float, str]:
    """Run one trial. Returns (exit_code, elapsed_s, diag_line)."""
    out_dir = BACKEND / "checkpoints" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir.with_suffix(".log")

    cmd = [
        "uv",
        "run",
        "python",
        "arcd_train.py",
        "--data-dir",
        str(args.data_dir),
        "--out-dir",
        str(out_dir),
        "--epochs",
        str(args.epochs),
        "--batch-size",
        str(args.batch_size),
        "--seq-len",
        str(args.seq_len),
        "--stride",
        str(args.stride),
        "--patience",
        str(args.patience),
        "--warmup-epochs",
        str(args.warmup_epochs),
        "--workers",
        str(args.workers),
        "--seed",
        str(args.seed),
        "--bf16",
    ]
    # Per-trial overrides
    for k, v in cfg.items():
        if k == "rationale":
            continue
        cmd.extend([f"--{k}", str(v)])

    print(f"\n{'#' * 75}")
    print(f"  SYNTH TRIAL {tag}")
    print(f"  rationale: {cfg.get('rationale')}")
    print(f"  cmd: {' '.join(cmd)}")
    print(f"{'#' * 75}\n", flush=True)

    t0 = time.time()
    with log_path.open("w") as logf:
        proc = subprocess.run(
            cmd, stdout=logf, stderr=subprocess.STDOUT, cwd=str(BACKEND)
        )
    elapsed = time.time() - t0

    diag = overfit_diag(out_dir / "training_history.json")
    print(
        f"  {tag} finished: exit={proc.returncode}  elapsed={elapsed:.0f}s  {diag}",
        flush=True,
    )
    return proc.returncode, elapsed, diag


def collect_summary() -> list[dict]:
    """Read inference_log.json, return the synth-relevant runs."""
    log_path = BACKEND / "checkpoints" / "inference_log.json"
    if not log_path.exists():
        return []
    data = json.loads(log_path.read_text())
    runs = []
    for r in data.get("runs", []):
        run_id = r.get("run_id", "")
        if (
            run_id.startswith("S")
            or run_id.startswith("synth_")
            or run_id.startswith("roma_synth")
        ):
            runs.append(
                {
                    "tag": run_id,
                    "best_val_auc": r.get("training", {}).get("best_val_auc"),
                    "best_epoch": r.get("training", {}).get("best_epoch"),
                    "epochs_trained": r.get("hyperparameters", {}).get(
                        "epochs_trained"
                    ),
                    "test_auc": r.get("test_metrics", {}).get("AUC-ROC"),
                    "test_acc": r.get("test_metrics", {}).get("Accuracy"),
                    "test_f1": r.get("test_metrics", {}).get("F1"),
                    "test_specificity": r.get("test_metrics", {}).get("Specificity"),
                    "test_mcc": r.get("test_metrics", {}).get("MCC"),
                    "status": r.get("status"),
                }
            )
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tags",
        nargs="*",
        default=None,
        help="Subset of trial tags to run (default: all)",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR_DEFAULT)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--warmup-epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--seq-len", type=int, default=50)
    parser.add_argument("--stride", type=int, default=5)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--target-auc", type=float, default=0.82)
    parser.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Skip the pre-flight 'another ARCD training is active' check",
    )
    args = parser.parse_args()

    if not args.allow_overlap:
        busy = already_training()
        if busy:
            print(
                "ERROR: another ARCD training is on MPS — refusing to start.",
                file=sys.stderr,
            )
            print(f"  {busy}", file=sys.stderr)
            print(
                "  (re-run with --allow-overlap to override at your own risk)",
                file=sys.stderr,
            )
            sys.exit(2)

    # Sanity check Neo4j credentials
    if not os.environ.get("LAB_TUTOR_NEO4J_URI"):
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, _, v = line.partition("=")
                    if k.startswith("LAB_TUTOR_") and k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip().strip("'\"")
    if not os.environ.get("LAB_TUTOR_NEO4J_URI"):
        print(
            "ERROR: LAB_TUTOR_NEO4J_URI not set; cannot load skill embeddings.",
            file=sys.stderr,
        )
        sys.exit(3)

    tags = args.tags if args.tags else list(TRIALS.keys())
    print(f"\nSynth orchestration plan: {tags}")
    print(f"  data_dir = {args.data_dir}")
    print(
        f"  epochs={args.epochs}  patience={args.patience}  warmup={args.warmup_epochs}"
    )
    print(
        f"  batch_size={args.batch_size}  seq_len={args.seq_len}  stride={args.stride}\n",
        flush=True,
    )

    leaderboard = []
    for tag in tags:
        if tag not in TRIALS:
            print(f"  unknown trial '{tag}', skipping")
            continue
        exit_code, elapsed, diag = run_trial(tag, TRIALS[tag], args)
        leaderboard.append(
            {
                "tag": tag,
                "exit_code": exit_code,
                "elapsed_s": round(elapsed, 1),
                "diag": diag,
            }
        )

        # Sorted leaderboard from inference_log
        runs = sorted(
            collect_summary(),
            key=lambda r: (r.get("test_auc") or r.get("best_val_auc") or 0),
            reverse=True,
        )
        print(
            f"\n  Leaderboard ({len(runs)} synth-related run(s) in inference_log.json):"
        )
        for r in runs:
            ta = f"{r['test_auc']:.4f}" if r.get("test_auc") is not None else "  -   "
            bv = (
                f"{r['best_val_auc']:.4f}"
                if r.get("best_val_auc") is not None
                else "  -   "
            )
            print(
                f"    {r['tag']:32s}  best_val={bv}  test_auc={ta}  status={r.get('status')}"
            )

        # Optional early exit
        for r in runs:
            if r.get("test_auc") is not None and r["test_auc"] >= args.target_auc:
                print(
                    f"\n  Reached target test AUC {args.target_auc}; stopping synth orchestration."
                )
                break
        else:
            continue
        break

    print(f"\n{'=' * 75}\n  SYNTH ORCHESTRATION COMPLETE\n{'=' * 75}")
    leaderboard_file = BACKEND / "checkpoints" / "_synth_leaderboard.json"
    leaderboard_file.write_text(
        json.dumps(
            {
                "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "trials": leaderboard,
            },
            indent=2,
        )
    )
    print(f"  Leaderboard saved -> {leaderboard_file}")


if __name__ == "__main__":
    main()
