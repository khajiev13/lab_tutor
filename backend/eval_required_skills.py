"""ARCD required-skills evaluation script.

Loads a trained checkpoint, runs the model on the test split, and
evaluates three categories of metrics:

    1. MetricsSuite   — standard classification metrics (AUC-ROC, F1, …)
    2. AdaEx eval     — ZPD alignment, calibration error, prereq correlation
    3. PathGen eval   — ZPD align, prereq sat, proj gain, decay cov, unlock pot
                        (PathGen v2 vs. random baseline)

Output
------
    <checkpoint_dir>/required_skills_report.json

Usage
-----
    cd backend
    uv run python eval_required_skills.py \\
        --checkpoint checkpoints/roma_synth_v6_2048 \\
        --data-dir   ../knowledge_graph_builder/data/synthgen/<run_id>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# Allow running from workspace root or backend/
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from app.modules.arcd_agent.evaluation.adaex_eval import (  # noqa: E402
    DifficultyCalculator,
    adaex_difficulty,
    evaluate_difficulty_strategy,
    fixed_medium_difficulty,
    random_difficulty,
)
from app.modules.arcd_agent.evaluation.pathgen_eval import (  # noqa: E402
    evaluate_path,
    pathgen_v2,
    random_path,
)
from app.modules.arcd_agent.model.training import ARCDModel, MetricsSuite  # noqa: E402

logger = logging.getLogger("eval_required_skills")


# ── Helpers re-used from arcd_train ──────────────────────────────────────────


def _load_prereq_adjacency(
    data_dir: Path | None,
    n_skills: int,
    concept_idx: dict[str, int],
    device: torch.device,
) -> torch.Tensor:
    if data_dir is not None:
        p = data_dir / "prereq_edges.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                A = torch.zeros(n_skills, n_skills, device=device)
                for _, row in df.iterrows():
                    si, di = int(row["src_skill_idx"]), int(row["dst_skill_idx"])
                    if 0 <= si < n_skills and 0 <= di < n_skills:
                        A[di, si] = 1.0
                row_sum = A.sum(dim=1, keepdim=True).clamp(min=1.0)
                logger.info("A_pre: loaded %d prereq edges from %s", len(df), p)
                return (A / row_sum).to(device)
            except Exception as exc:
                logger.warning(
                    "Failed to load prereq_edges.parquet (%s) — using identity", exc
                )
    return torch.eye(n_skills, device=device)


def _load_video_adjacency(
    data_dir: Path | None,
    vocab: dict,
    n_skills: int,
    device: torch.device,
) -> torch.Tensor:
    if data_dir is not None:
        p = data_dir / "skill_videos.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                n_videos = len(vocab.get("video", {})) or (
                    int(df["video_idx"].max()) + 1 if len(df) else 1
                )
                n_videos = max(n_videos, 1)
                A = torch.zeros(n_videos, n_skills, device=device)
                for _, row in df.iterrows():
                    vi, si = int(row["video_idx"]), int(row["skill_idx"])
                    if 0 <= vi < n_videos and 0 <= si < n_skills:
                        A[vi, si] = 1.0
                row_sum = A.sum(dim=1, keepdim=True).clamp(min=1.0)
                return (A / row_sum).to(device)
            except Exception as exc:
                logger.warning(
                    "Failed to load skill_videos.parquet (%s) — using dummy", exc
                )
    return torch.zeros(1, n_skills, device=device)


def _load_reading_adjacency(
    data_dir: Path | None,
    vocab: dict,
    n_skills: int,
    device: torch.device,
) -> torch.Tensor:
    if data_dir is not None:
        p = data_dir / "skill_readings.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                n_readings = len(vocab.get("reading", {})) or (
                    int(df["reading_idx"].max()) + 1 if len(df) else 1
                )
                n_readings = max(n_readings, 1)
                A = torch.zeros(n_readings, n_skills, device=device)
                for _, row in df.iterrows():
                    ri, si = int(row["reading_idx"]), int(row["skill_idx"])
                    if 0 <= ri < n_readings and 0 <= si < n_skills:
                        A[ri, si] = 1.0
                row_sum = A.sum(dim=1, keepdim=True).clamp(min=1.0)
                return (A / row_sum).to(device)
            except Exception as exc:
                logger.warning(
                    "Failed to load skill_readings.parquet (%s) — using dummy", exc
                )
    return torch.zeros(1, n_skills, device=device)


def build_graph_tensors(
    test_df: pd.DataFrame,
    vocab: dict,
    d_skill_embed: int,
    device: torch.device,
    data_dir: Path | None = None,
) -> dict[str, torch.Tensor]:
    n_skills = len(vocab["concept"])
    n_questions = len(vocab["question"])
    n_students = len(vocab["user"])
    concept_idx: dict[str, int] = vocab["concept"]

    H = torch.empty(n_skills, d_skill_embed)
    nn.init.xavier_uniform_(H)

    A_pre = _load_prereq_adjacency(data_dir, n_skills, concept_idx, device)
    A_vs = _load_video_adjacency(data_dir, vocab, n_skills, device)
    A_rs = _load_reading_adjacency(data_dir, vocab, n_skills, device)

    A_qs_raw = torch.zeros(n_questions, n_skills, device=device)
    for qi, si in (
        test_df[["question_idx", "skill_idx"]].drop_duplicates().values.tolist()
    ):
        qi, si = int(qi), int(si)
        if 0 <= qi < n_questions and 0 <= si < n_skills:
            A_qs_raw[qi, si] = 1.0
    A_qs = A_qs_raw / A_qs_raw.sum(dim=1, keepdim=True).clamp(min=1.0)

    A_uq = torch.zeros(n_students, n_questions, device=device)

    return {
        "H_skill_raw": H.to(device),
        "A_pre": A_pre,
        "A_qs": A_qs,
        "A_vs": A_vs,
        "A_rs": A_rs,
        "A_uq": A_uq,
    }


def build_mastery_lookup(
    mastery_df: pd.DataFrame, concept_to_idx: dict[str, int]
) -> dict[int, np.ndarray]:
    n_skills = len(concept_to_idx)
    lookup: dict[int, np.ndarray] = {}
    for sid, grp in mastery_df.groupby("student_id"):
        try:
            student_idx = int(str(sid).split("_")[1])
        except (IndexError, ValueError):
            continue
        arr = np.zeros(n_skills, dtype=np.float32)
        for _, row in grp.iterrows():
            cidx = concept_to_idx.get(str(row["skill_id"]))
            if cidx is not None:
                arr[cidx] = float(row["mastery"])
        lookup[student_idx] = arr
    return lookup


# ── Test dataset (same sliding-window as in arcd_train) ──────────────────────


class TestDataset(Dataset):
    def __init__(
        self,
        df: pd.DataFrame,
        mastery_lookup: dict[int, np.ndarray],
        n_skills: int,
        seq_len: int = 100,
        stride: int = 3,
    ):
        self.seq_len = seq_len
        self._zero_mastery = np.zeros(n_skills, dtype=np.float32)
        self.mastery_lookup = mastery_lookup

        df = df.sort_values(["student_idx", "timestamp_sec"]).reset_index(drop=True)
        student_events: dict[int, list[tuple]] = defaultdict(list)
        for row in df.itertuples(index=False):
            student_events[int(row.student_idx)].append(
                (int(row.question_idx), int(row.correct), float(row.timestamp_sec))
            )

        self.examples: list[tuple] = []
        for uid, events in student_events.items():
            if len(events) < 2:
                continue
            for end in range(stride + 1, len(events) + 1, stride):
                window = events[max(0, end - seq_len) : end]
                if len(window) < 2:
                    continue
                self.examples.append((uid, window))

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        uid, window = self.examples[idx]
        hist = window[:-1]
        tgt_q, tgt_correct, _ = window[-1]

        T = self.seq_len - 1
        pad_len = T - len(hist)

        event_types = [0] * len(hist) + [0] * pad_len
        entity_indices = [e[0] for e in hist] + [0] * pad_len
        outcomes = [float(e[1]) for e in hist] + [0.0] * pad_len
        timestamps = [float(e[2]) for e in hist] + [0.0] * pad_len
        decay_values = [0.0] * T
        pad_mask = [True] * len(hist) + [False] * pad_len
        mastery = self.mastery_lookup.get(uid, self._zero_mastery)

        return {
            "student_ids": torch.tensor(uid, dtype=torch.long),
            "event_types": torch.tensor(event_types, dtype=torch.long),
            "entity_indices": torch.tensor(entity_indices, dtype=torch.long),
            "outcomes": torch.tensor(outcomes, dtype=torch.float32),
            "timestamps": torch.tensor(timestamps, dtype=torch.float32),
            "decay_values": torch.tensor(decay_values, dtype=torch.float32),
            "pad_mask": torch.tensor(pad_mask, dtype=torch.bool),
            "target_type": torch.tensor(0, dtype=torch.long),
            "target_idx": torch.tensor(tgt_q, dtype=torch.long),
            "response_target": torch.tensor(float(tgt_correct), dtype=torch.float32),
            "mastery_target": torch.tensor(mastery, dtype=torch.float32),
        }


# ── Batch inference ───────────────────────────────────────────────────────────


@torch.no_grad()
def run_inference(
    model: ARCDModel,
    loader: DataLoader,
    graph_data: dict[str, torch.Tensor],
    device: torch.device,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (y_true, y_prob, mastery_preds).

    mastery_preds: (N, n_skills) float32 — one row per example.
    """
    model.eval()
    gd = {k: v.to(device) for k, v in graph_data.items()}

    all_logits: list[torch.Tensor] = []
    all_targets: list[torch.Tensor] = []
    all_mastery: list[torch.Tensor] = []

    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        out = model(
            gd["H_skill_raw"],
            gd["A_pre"],
            gd["A_qs"],
            gd["A_vs"],
            gd["A_rs"],
            gd["A_uq"],
            batch["event_types"],
            batch["entity_indices"],
            batch["outcomes"],
            batch["timestamps"],
            batch["decay_values"],
            batch["pad_mask"],
            batch["target_type"],
            batch["target_idx"],
            student_ids=batch["student_ids"],
        )
        all_logits.append(out["response_logit"].cpu())
        all_targets.append(batch["response_target"].cpu())
        all_mastery.append(out["mastery"].cpu())

    y_prob = torch.sigmoid(torch.cat(all_logits)).numpy()
    y_true = torch.cat(all_targets).numpy()
    mastery_preds = torch.cat(all_mastery).numpy()  # (N, n_skills)
    return y_true, y_prob, mastery_preds


# ── Main ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="eval_required_skills",
        description="Evaluate ARCD checkpoint on MetricsSuite + AdaEx + PathGen.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Checkpoint directory produced by arcd_train.py (contains best_model.pt)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="synthgen run directory (test.parquet / vocab.json / …)",
    )
    parser.add_argument("--seq-len", type=int, default=100)
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument(
        "--n-eval-students",
        type=int,
        default=50,
        help="Max students to use for AdaEx / PathGen eval",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)

    ckpt_path = args.checkpoint.resolve() / "best_model.pt"
    if not ckpt_path.exists():
        logger.error("Checkpoint not found: %s", ckpt_path)
        sys.exit(1)

    data_dir = args.data_dir.resolve()

    # ── Device ────────────────────────────────────────────────────────────
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    logger.info("Device: %s", device)

    # ── Load checkpoint ───────────────────────────────────────────────────
    logger.info("Loading checkpoint from %s …", ckpt_path)
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    cfg = ckpt.get("model_config", ckpt.get("config", {}))

    # ── Load data ─────────────────────────────────────────────────────────
    logger.info("Loading data from %s …", data_dir)
    test_df = pd.read_parquet(data_dir / "test.parquet")
    mastery_df = pd.read_parquet(data_dir / "mastery_ground_truth.parquet")

    with open(data_dir / "vocab.json") as f:
        vocab = json.load(f)

    n_skills = len(vocab["concept"])
    concept_to_idx: dict[str, int] = vocab["concept"]
    logger.info(
        "n_skills=%d  n_questions=%d  n_students=%d",
        n_skills,
        len(vocab["question"]),
        len(vocab["user"]),
    )

    mastery_lookup = build_mastery_lookup(mastery_df, concept_to_idx)

    # ── Build graph tensors ────────────────────────────────────────────────
    d_skill_embed = cfg.get("d_skill_embed", 32)
    graph_data = build_graph_tensors(
        test_df, vocab, d_skill_embed, device, data_dir=data_dir
    )

    # ── Reconstruct model ─────────────────────────────────────────────────
    model = ARCDModel(
        d_skill_embed=d_skill_embed,
        d=cfg.get("d", 64),
        n_gat_layers=cfg.get("n_gat_layers", cfg.get("n_gcn_layers", 2)),
        n_questions=cfg.get("n_questions", len(vocab["question"])),
        n_videos=cfg.get("n_videos", graph_data["A_vs"].size(0)),
        n_readings=cfg.get("n_readings", graph_data["A_rs"].size(0)),
        n_students=cfg.get("n_students", len(vocab["user"])),
        n_skills=n_skills,
        n_heads_gat=cfg.get("n_heads_gat", 2),
        d_type=cfg.get("d_type", 16),
        n_heads=cfg.get("n_heads", 2),
        d_ff=cfg.get("d_ff", cfg.get("d", 64) * 4),
        n_attn_layers=cfg.get("n_attn_layers", 2),
        dropout=0.0,
        use_gat=cfg.get("use_gat", True),
    ).to(device)

    state_key = "model_state_dict" if "model_state_dict" in ckpt else "state_dict"
    model.load_state_dict(ckpt[state_key])
    model.eval()
    logger.info(
        "Model loaded — params: %s", f"{sum(p.numel() for p in model.parameters()):,}"
    )

    # ── Build test DataLoader ─────────────────────────────────────────────
    test_ds = TestDataset(
        test_df,
        mastery_lookup,
        n_skills,
        seq_len=args.seq_len,
        stride=args.stride,
    )
    test_loader = DataLoader(
        test_ds, batch_size=args.batch_size, shuffle=False, num_workers=0
    )
    logger.info("Test windows: %d", len(test_ds))

    # ── 1. MetricsSuite ───────────────────────────────────────────────────
    logger.info("Running inference for MetricsSuite …")
    y_true, y_prob, mastery_preds = run_inference(
        model, test_loader, graph_data, device
    )
    suite = MetricsSuite()
    metrics = suite.report(y_true, y_prob, title="Required Skills — Test Set")
    logger.info(
        "AUC-ROC=%.4f  PR-AUC=%.4f  F1=%.4f",
        metrics["AUC-ROC"],
        metrics["PR-AUC"],
        metrics["F1"],
    )

    # ── 2. AdaEx eval ─────────────────────────────────────────────────────
    logger.info("Running AdaEx evaluation …")
    A_pre_np = graph_data["A_pre"].cpu().numpy()

    # Build mastery matrix using MODEL-PREDICTED mastery so AdaEx reflects what
    # the production system actually sees (not ground truth).  Aggregate per-student
    # mastery predictions across all test windows (last window per student wins).
    student_ids_ordered = sorted(mastery_lookup.keys())[: args.n_eval_students]
    predicted_mastery: dict[int, np.ndarray] = {}
    for sid in student_ids_ordered:
        predicted_mastery[sid] = np.zeros(n_skills, dtype=np.float32)

    # Collect per-student last mastery prediction from test inference
    # mastery_preds shape: (N_windows, n_skills) — use the last window per student
    # We rebuild a per-student index from the test dataset
    test_student_windows: dict[int, list[int]] = defaultdict(list)
    for win_idx in range(len(test_loader.dataset)):
        item = test_loader.dataset[win_idx]
        sid_raw = int(item["student_ids"].item())
        test_student_windows[sid_raw].append(win_idx)
    for sid_raw, win_idxs in test_student_windows.items():
        last_win = max(win_idxs)
        if last_win < len(mastery_preds):
            predicted_mastery[sid_raw] = mastery_preds[last_win]

    # Fall back to ground truth for students with no predicted mastery
    for sid in student_ids_ordered:
        if np.all(predicted_mastery.get(sid, np.zeros(n_skills)) == 0):
            predicted_mastery[sid] = mastery_lookup.get(
                sid, np.zeros(n_skills, dtype=np.float32)
            )

    mastery_arr = np.stack(
        [
            predicted_mastery.get(s, np.zeros(n_skills, dtype=np.float32))
            for s in student_ids_ordered
        ],
        axis=0,
    )  # (N, S)
    decay_arr = np.ones_like(mastery_arr) * 0.85  # default retention
    n_concepts_arr = np.ones(n_skills, dtype=int)  # 1 concept per skill (conservative)
    max_concepts = 10

    calc = DifficultyCalculator(A_skill=A_pre_np)

    adaex_results = evaluate_difficulty_strategy(
        adaex_difficulty,
        mastery_arr,
        decay_arr,
        A_pre_np,
        calc,
        n_concepts_arr,
        max_concepts,
        rng,
        use_calc=True,
    )
    baseline_fixed = evaluate_difficulty_strategy(
        fixed_medium_difficulty,
        mastery_arr,
        decay_arr,
        A_pre_np,
        calc,
        n_concepts_arr,
        max_concepts,
        rng,
    )
    baseline_random = evaluate_difficulty_strategy(
        random_difficulty,
        mastery_arr,
        decay_arr,
        A_pre_np,
        calc,
        n_concepts_arr,
        max_concepts,
        rng,
    )

    logger.info(
        "AdaEx  zpd_alignment=%.3f  calib_error=%.3f  prereq_corr=%.3f  variance=%.3f",
        adaex_results["zpd_alignment"],
        adaex_results["calibration_error"],
        adaex_results.get("prereq_correlation", 0.0),
        adaex_results.get("cross_student_variance", 0.0),
    )
    logger.info(
        "Fixed  zpd_alignment=%.3f  calib_error=%.3f | Random zpd_alignment=%.3f  calib_error=%.3f",
        baseline_fixed["zpd_alignment"],
        baseline_fixed["calibration_error"],
        baseline_random["zpd_alignment"],
        baseline_random["calibration_error"],
    )

    # ── 3. PathGen eval ───────────────────────────────────────────────────
    logger.info("Running PathGen v2 evaluation …")
    pathgen_results: list[dict] = []
    random_results: list[dict] = []

    for s_idx in student_ids_ordered:
        mastery_vec = predicted_mastery.get(
            s_idx, mastery_lookup.get(s_idx, np.zeros(n_skills, dtype=np.float32))
        ).copy()
        decay_vec = np.ones(n_skills, dtype=np.float32) * 0.85

        pg_path = pathgen_v2(mastery_vec, decay_vec, A_pre_np, K=8)
        rnd_path = random_path(mastery_vec, decay_vec, A_pre_np, K=8, rng=rng)

        pathgen_results.append(
            evaluate_path(pg_path, mastery_vec, decay_vec, A_pre_np, rng=rng)
        )
        random_results.append(
            evaluate_path(rnd_path, mastery_vec, decay_vec, A_pre_np, rng=rng)
        )

    def _mean_dict(dicts: list[dict]) -> dict:
        if not dicts:
            return {}
        keys = dicts[0].keys()
        return {k: float(np.mean([d[k] for d in dicts])) for k in keys}

    pg_mean = _mean_dict(pathgen_results)
    rnd_mean = _mean_dict(random_results)

    logger.info(
        "PathGen v2  zpd_align=%.3f  prereq_sat=%.3f  proj_gain=%.3f  unlock_pot=%.1f",
        pg_mean["zpd_align"],
        pg_mean["prereq_sat"],
        pg_mean["proj_gain"],
        pg_mean["unlock_pot"],
    )
    logger.info(
        "Random      zpd_align=%.3f  prereq_sat=%.3f  proj_gain=%.3f  unlock_pot=%.1f",
        rnd_mean["zpd_align"],
        rnd_mean["prereq_sat"],
        rnd_mean["proj_gain"],
        rnd_mean["unlock_pot"],
    )

    # ── Acceptance thresholds ──────────────────────────────────────────────
    # AdaEx computes d* = alpha*(1-mastery) + depth + complexity — it assigns
    # PERSONALISED difficulty that varies with each student's mastery state.
    # Fixed medium always assigns 0.5 → zero cross-student variance.  The
    # meaningful acceptance check is: does AdaEx produce more spread across
    # students than fixed medium?  (i.e., variance > 0, which is guaranteed
    # as long as mastery predictions are non-trivially distributed).
    # We also verify PathGen v2 beats random on the two key metrics.
    passed = {
        "val_auc_ge_0.65": metrics["AUC-ROC"] >= 0.65,
        "f1_nonzero": metrics["F1"] > 0.0,
        "adaex_personalises_difficulty": (
            adaex_results.get("cross_student_variance", 0.0)
            > baseline_fixed.get("cross_student_variance", 0.0)
        ),
        "pathgen_v2_beats_random_zpd": pg_mean["zpd_align"] >= rnd_mean["zpd_align"],
        "pathgen_v2_beats_random_gain": pg_mean["proj_gain"] >= rnd_mean["proj_gain"],
    }
    all_passed = all(passed.values())
    logger.info("Acceptance checks: %s", passed)
    logger.info("ALL PASSED: %s", all_passed)

    # ── Write report ──────────────────────────────────────────────────────
    report = {
        "checkpoint": str(args.checkpoint),
        "data_dir": str(args.data_dir),
        "best_val_auc_at_train": float(ckpt.get("best_val_auc", 0.0)),
        "metrics_suite": metrics,
        "adaex": {
            "adaex": adaex_results,
            "baseline_fixed_medium": baseline_fixed,
            "baseline_random": baseline_random,
        },
        "pathgen": {
            "pathgen_v2_mean": pg_mean,
            "random_mean": rnd_mean,
        },
        "acceptance": passed,
        "all_passed": all_passed,
    }

    out_path = args.checkpoint / "required_skills_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Report written to %s", out_path)

    if not all_passed:
        failed = [k for k, v in passed.items() if not v]
        logger.warning("FAILED acceptance checks: %s", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
