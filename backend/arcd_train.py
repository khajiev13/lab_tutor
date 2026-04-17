"""ARCD training CLI — trains ARCDModel on synthetic (or real) Parquet data.

Usage
-----
    cd backend
    uv run python arcd_train.py \
        --data-dir ../knowledge_graph_builder/data/synthgen/roma_synth_v1 \
        --out-dir  checkpoints/roma_synth_v1 \
        --epochs   50 \
        --batch-size 256 \
        --seq-len  50 \
        --seed     42

Artifacts saved
---------------
    <out-dir>/
        best_model.pt          — best checkpoint (state_dict + config)
        training_history.json  — per-epoch train/val loss and AUC
        metrics_report.json    — full MetricsSuite evaluation on test set
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# Allow running from workspace root or backend/ directly
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from arcd_agent.model.training import (  # noqa: E402
    ARCDLoss,
    ARCDModel,
    ARCDTrainer,
    MetricsSuite,
)

logger = logging.getLogger("arcd_train")


# ─────────────────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────────────────

def build_graph_tensors(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    vocab: dict,
    d_skill_embed: int,
    device: torch.device,
    data_dir: Path | None = None,
) -> dict[str, torch.Tensor]:
    """Build all 6 graph tensors from Parquet/vocab data.

    Loads real KG adjacency matrices (A_pre, A_vs, A_rs) from parquet files
    exported by synthgen if available, falling back to identity/dummy otherwise.

    Returns
    -------
    H_skill_raw : [n_skills, d_skill_embed]   Xavier-init skill features
    A_pre       : [n_skills, n_skills]          row-norm prerequisite adj
    A_qs        : [n_questions, n_skills]        row-norm question-skill adj
    A_vs        : [n_videos, n_skills]           row-norm video-skill adj
    A_rs        : [n_readings, n_skills]         row-norm reading-skill adj
    A_uq        : [n_students, n_questions]      row-norm user-question adj
    """
    n_skills    = len(vocab["concept"])
    n_questions = len(vocab["question"])
    n_students  = len(vocab["user"])
    concept_idx: dict[str, int] = vocab["concept"]

    # H_skill_raw: Xavier-uniform initialisation
    H = torch.empty(n_skills, d_skill_embed)
    nn.init.xavier_uniform_(H)
    H_skill_raw = H.to(device)

    # ── A_pre: prerequisite adjacency ────────────────────────────────────
    A_pre = _load_prereq_adjacency(data_dir, n_skills, concept_idx, device)

    # ── A_qs: question → skill ───────────────────────────────────────────
    all_df = pd.concat([train_df, test_df], ignore_index=True)
    A_qs_raw = torch.zeros(n_questions, n_skills, device=device)
    pairs = (
        all_df[["question_idx", "skill_idx"]]
        .drop_duplicates()
        .values.tolist()
    )
    for qi, si in pairs:
        qi, si = int(qi), int(si)
        if 0 <= qi < n_questions and 0 <= si < n_skills:
            A_qs_raw[qi, si] = 1.0
    row_sum = A_qs_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
    A_qs = A_qs_raw / row_sum

    # ── A_vs / A_rs: real video/reading adjacency ────────────────────────
    A_vs = _load_video_adjacency(data_dir, vocab, n_skills, device)
    A_rs = _load_reading_adjacency(data_dir, vocab, n_skills, device)

    # ── A_uq: student → question ──────────────────────────────────────────
    A_uq_raw = torch.zeros(n_students, n_questions, device=device)
    train_pairs = (
        train_df[["student_idx", "question_idx"]]
        .drop_duplicates()
        .values.tolist()
    )
    for ui, qi in train_pairs:
        ui, qi = int(ui), int(qi)
        if 0 <= ui < n_students and 0 <= qi < n_questions:
            A_uq_raw[ui, qi] = 1.0
    uq_sum = A_uq_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
    A_uq = A_uq_raw / uq_sum

    logger.info(
        "Graph tensors — n_skills=%d  n_questions=%d  n_students=%d  "
        "n_videos=%d  n_readings=%d",
        n_skills, n_questions, n_students, A_vs.size(0), A_rs.size(0),
    )
    return {
        "H_skill_raw": H_skill_raw,
        "A_pre":       A_pre,
        "A_qs":        A_qs,
        "A_vs":        A_vs,
        "A_rs":        A_rs,
        "A_uq":        A_uq,
    }


def _load_prereq_adjacency(
    data_dir: Path | None,
    n_skills: int,
    concept_idx: dict[str, int],
    device: torch.device,
) -> torch.Tensor:
    """Load prerequisite adjacency from prereq_edges.parquet, fall back to identity."""
    if data_dir is not None:
        p = data_dir / "prereq_edges.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                A = torch.zeros(n_skills, n_skills, device=device)
                for _, row in df.iterrows():
                    si, di = int(row["src_skill_idx"]), int(row["dst_skill_idx"])
                    if 0 <= si < n_skills and 0 <= di < n_skills:
                        A[di, si] = 1.0  # prerequisite si → di (si is prereq of di)
                row_sum = A.sum(dim=1, keepdim=True).clamp(min=1.0)
                logger.info("A_pre: loaded %d prereq edges from %s", len(df), p)
                return (A / row_sum).to(device)
            except Exception as exc:
                logger.warning("Failed to load prereq_edges.parquet (%s) — using identity", exc)
    logger.warning("A_pre: no prereq_edges.parquet found — using identity matrix")
    return torch.eye(n_skills, device=device)


def _load_video_adjacency(
    data_dir: Path | None,
    vocab: dict,
    n_skills: int,
    device: torch.device,
) -> torch.Tensor:
    """Load video-skill adjacency from skill_videos.parquet, fall back to dummy."""
    if data_dir is not None:
        p = data_dir / "skill_videos.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                n_videos = len(vocab.get("video", {})) or (df["video_idx"].max() + 1 if len(df) else 1)
                n_videos = max(n_videos, 1)
                A = torch.zeros(n_videos, n_skills, device=device)
                for _, row in df.iterrows():
                    vi, si = int(row["video_idx"]), int(row["skill_idx"])
                    if 0 <= vi < n_videos and 0 <= si < n_skills:
                        A[vi, si] = 1.0
                row_sum = A.sum(dim=1, keepdim=True).clamp(min=1.0)
                logger.info("A_vs: loaded %d video-skill edges, n_videos=%d", len(df), n_videos)
                return (A / row_sum).to(device)
            except Exception as exc:
                logger.warning("Failed to load skill_videos.parquet (%s) — using dummy", exc)
    logger.warning("A_vs: no skill_videos.parquet found — using dummy (1, n_skills)")
    return torch.zeros(1, n_skills, device=device)


def _load_reading_adjacency(
    data_dir: Path | None,
    vocab: dict,
    n_skills: int,
    device: torch.device,
) -> torch.Tensor:
    """Load reading-skill adjacency from skill_readings.parquet, fall back to dummy."""
    if data_dir is not None:
        p = data_dir / "skill_readings.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                n_readings = len(vocab.get("reading", {})) or (df["reading_idx"].max() + 1 if len(df) else 1)
                n_readings = max(n_readings, 1)
                A = torch.zeros(n_readings, n_skills, device=device)
                for _, row in df.iterrows():
                    ri, si = int(row["reading_idx"]), int(row["skill_idx"])
                    if 0 <= ri < n_readings and 0 <= si < n_skills:
                        A[ri, si] = 1.0
                row_sum = A.sum(dim=1, keepdim=True).clamp(min=1.0)
                logger.info("A_rs: loaded %d reading-skill edges, n_readings=%d", len(df), n_readings)
                return (A / row_sum).to(device)
            except Exception as exc:
                logger.warning("Failed to load skill_readings.parquet (%s) — using dummy", exc)
    logger.warning("A_rs: no skill_readings.parquet found — using dummy (1, n_skills)")
    return torch.zeros(1, n_skills, device=device)


# ─────────────────────────────────────────────────────────────────────────────
# Mastery lookup
# ─────────────────────────────────────────────────────────────────────────────

def build_mastery_lookup(
    mastery_df: pd.DataFrame,
    concept_to_idx: dict[str, int],
) -> dict[int, np.ndarray]:
    """Build {student_idx → float32[n_skills]} from mastery_ground_truth.parquet.

    student_id format: "synth_{i:04d}_{run_id}" → student_idx = i
    (valid because zero-padded IDs sort in numeric order, making sorted-position = i).
    """
    n_skills = len(concept_to_idx)
    lookup: dict[int, np.ndarray] = {}

    grouped = mastery_df.groupby("student_id")
    for sid, grp in grouped:
        try:
            student_idx = int(str(sid).split("_")[1])
        except (IndexError, ValueError):
            logger.debug("Cannot parse student_idx from %r — skipping", sid)
            continue

        arr = np.zeros(n_skills, dtype=np.float32)
        for _, row in grp.iterrows():
            cidx = concept_to_idx.get(str(row["skill_id"]))
            if cidx is not None:
                arr[cidx] = float(row["mastery"])
        lookup[student_idx] = arr

    logger.info("Mastery lookup: %d / %d students have mastery targets",
                len(lookup), mastery_df["student_id"].nunique())
    return lookup


# ─────────────────────────────────────────────────────────────────────────────
# Sequence Dataset
# ─────────────────────────────────────────────────────────────────────────────

class SynthgenSequenceDataset(Dataset):
    """Sliding-window sequence dataset for ARCD training.

    Each example is:
        history: `seq_len - 1` interactions (right-padded if shorter)
        target: the next interaction to predict

    Padding convention (matches TemporalAttentionModel):
        pad_mask = True  → valid (real) event  — placed at the LEFT
        pad_mask = False → padding position    — placed at the RIGHT
    This lets last_idx = pad_mask.sum() - 1 resolve to the last real event,
    and ~pad_mask correctly blocks padding keys in temporal attention.

    Batch keys
    ----------
    student_ids, event_types, entity_indices, outcomes, timestamps,
    decay_values, pad_mask, target_type, target_idx,
    response_target, mastery_target
    """

    def __init__(
        self,
        df: pd.DataFrame,
        mastery_lookup: dict[int, np.ndarray],
        n_skills: int,
        seq_len: int = 50,
        stride: int = 1,
    ):
        self.seq_len = seq_len
        self.n_skills = n_skills
        self._zero_mastery = np.zeros(n_skills, dtype=np.float32)
        self.mastery_lookup = mastery_lookup

        df = df.sort_values(["student_idx", "timestamp_sec"]).reset_index(drop=True)

        student_events: dict[int, list[tuple]] = defaultdict(list)
        for row in df.itertuples(index=False):
            student_events[int(row.student_idx)].append((
                int(row.question_idx),
                int(row.correct),
                float(row.timestamp_sec),
            ))

        self.examples: list[tuple] = []
        for uid, events in student_events.items():
            if len(events) < 2:
                continue
            for end in range(stride + 1, len(events) + 1, stride):
                window = events[max(0, end - seq_len): end]
                if len(window) < 2:
                    continue
                self.examples.append((uid, window))

        logger.info(
            "Dataset: %d students → %d windows (seq_len=%d stride=%d)",
            len(student_events), len(self.examples), seq_len, stride,
        )

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        uid, window = self.examples[idx]
        hist = window[:-1]
        tgt_q, tgt_correct, _ = window[-1]

        T = self.seq_len - 1
        pad_len = T - len(hist)

        event_types    = [0] * len(hist) + [0] * pad_len
        entity_indices = [e[0] for e in hist] + [0] * pad_len
        outcomes       = [e[1] for e in hist] + [0.0] * pad_len
        timestamps     = [e[2] for e in hist] + [0.0] * pad_len
        decay_values   = [0.0] * T
        # Right-padding: True=valid events at left, False=padding at right.
        # Matches TemporalAttentionModel which uses `~pad_mask` to block keys
        # and `pad_mask.sum()-1` to index the last valid event.
        pad_mask       = [True] * len(hist) + [False] * pad_len

        mastery = self.mastery_lookup.get(uid, self._zero_mastery)

        return {
            "student_ids":     torch.tensor(uid,            dtype=torch.long),
            "event_types":     torch.tensor(event_types,    dtype=torch.long),
            "entity_indices":  torch.tensor(entity_indices, dtype=torch.long),
            "outcomes":        torch.tensor(outcomes,        dtype=torch.float32),
            "timestamps":      torch.tensor(timestamps,      dtype=torch.float32),
            "decay_values":    torch.tensor(decay_values,    dtype=torch.float32),
            "pad_mask":        torch.tensor(pad_mask,        dtype=torch.bool),
            "target_type":     torch.tensor(0,               dtype=torch.long),
            "target_idx":      torch.tensor(tgt_q,           dtype=torch.long),
            "response_target": torch.tensor(float(tgt_correct), dtype=torch.float32),
            "mastery_target":  torch.tensor(mastery,         dtype=torch.float32),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation with MetricsSuite
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate_metrics(
    trainer: ARCDTrainer,
    loader: DataLoader,
    suite: MetricsSuite,
    title: str,
) -> dict:
    """Collect predictions via trainer and compute full MetricsSuite report."""
    trainer.model.eval()
    gcn_cache = trainer.model.run_gcn_cached(*trainer._build_gcn_args())

    all_logits, all_targets = [], []
    for batch in loader:
        out = trainer._forward(batch, gcn_cache=gcn_cache)
        all_logits.append(out["response_logit"].cpu())
        all_targets.append(batch["response_target"])

    probs   = torch.sigmoid(torch.cat(all_logits)).numpy()
    targets = torch.cat(all_targets).numpy()
    return suite.report(targets, probs, title=title)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="arcd_train",
        description="Train ARCDModel on synthgen Parquet artifacts.",
    )
    parser.add_argument(
        "--data-dir", type=Path, required=True,
        help="synthgen run directory (train.parquet / test.parquet / vocab.json)",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("checkpoints/synthgen"),
        help="Output directory for checkpoints and metrics",
    )
    parser.add_argument("--epochs",       type=int,   default=50)
    parser.add_argument("--batch-size",   type=int,   default=256)
    parser.add_argument("--seq-len",      type=int,   default=50)
    parser.add_argument("--stride",       type=int,   default=5,
                        help="Sliding-window stride (lower = more examples, slower)")
    parser.add_argument("--lr",           type=float, default=1e-3)
    parser.add_argument("--d",            type=int,   default=64,
                        help="Model hidden dim")
    parser.add_argument("--d-skill",      type=int,   default=32,
                        help="Skill embedding dim")
    parser.add_argument("--n-gat-layers", type=int,   default=2)
    parser.add_argument("--n-attn-layers",type=int,   default=2)
    parser.add_argument("--patience",     type=int,   default=15)
    parser.add_argument("--warmup-epochs", type=int,  default=5,
                        help="Linear LR warmup epochs before cosine annealing")
    parser.add_argument("--seed",         type=int,   default=42)
    parser.add_argument("--workers",      type=int,   default=0)
    parser.add_argument("--verbose", "-v",action="store_true")
    parser.add_argument("--mastery-weight", type=float, default=0.2,
                        help="Weight for mastery loss in ARCDLoss")
    parser.add_argument("--focal-alpha",    type=float, default=0.75,
                        help="Focal loss alpha (class-balance weight) in ARCDLoss")
    parser.add_argument("--dropout",        type=float, default=0.1,
                        help="Dropout rate for ARCDModel")
    parser.add_argument("--student-emb-dropout", type=float, default=0.0,
                        help="Probability of zeroing student embedding per sample during "
                             "training (cold-start dropout). 0 = disabled, 0.5 recommended "
                             "when train/test split is by student.")
    parser.add_argument("--weight-decay",   type=float, default=1e-4,
                        help="AdamW weight decay for regularization")
    parser.add_argument("--rdrop-alpha",    type=float, default=0.3,
                        help="R-Drop KL consistency loss weight (0 = disabled)")
    parser.add_argument("--label-smoothing", type=float, default=0.1,
                        help="Label smoothing epsilon for FocalLoss (0 = hard targets)")
    parser.add_argument(
        "--data-fraction", type=float, default=1.0, metavar="FRAC",
        help="Fraction of students to keep (0 < FRAC ≤ 1.0). "
             "Students are sampled by ID so every sequence in their "
             "history is preserved.  Default: 1.0 (all data).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    # Device selection
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    logger.info("Device: %s", device)

    # ── Load data ─────────────────────────────────────────────────────────
    data_dir = args.data_dir.resolve()
    logger.info("Loading data from %s …", data_dir)

    train_df   = pd.read_parquet(data_dir / "train.parquet")
    test_df    = pd.read_parquet(data_dir / "test.parquet")
    mastery_df = pd.read_parquet(data_dir / "mastery_ground_truth.parquet")

    with open(data_dir / "vocab.json") as f:
        vocab = json.load(f)

    n_skills    = len(vocab["concept"])
    n_questions = len(vocab["question"])
    n_students  = len(vocab["user"])
    concept_to_idx: dict[str, int] = vocab["concept"]

    logger.info(
        "Dataset: train=%d  test=%d  mastery=%d rows  "
        "(skills=%d  questions=%d  students=%d)",
        len(train_df), len(test_df), len(mastery_df),
        n_skills, n_questions, n_students,
    )

    # ── Optional data-fraction sub-sampling ────────────────────────────────
    # Sample students (not raw rows) so every student's full sequence stays
    # intact and the temporal model still sees coherent histories.
    if 0.0 < args.data_fraction < 1.0:
        rng = np.random.default_rng(args.seed)

        all_train_students = train_df["student_idx"].unique()
        n_keep = max(1, int(round(len(all_train_students) * args.data_fraction)))
        kept_students = rng.choice(all_train_students, size=n_keep, replace=False)
        kept_set = set(kept_students.tolist())

        train_df   = train_df[train_df["student_idx"].isin(kept_set)].reset_index(drop=True)
        test_df    = test_df[test_df["student_idx"].isin(kept_set)].reset_index(drop=True)
        mastery_df = mastery_df[mastery_df["student_id"].isin(
            {f"synth_{i:04d}_{data_dir.name}" for i in kept_set}
        )].reset_index(drop=True)

        logger.info(
            "data-fraction=%.2f → kept %d/%d students  "
            "(train=%d  test=%d rows)",
            args.data_fraction, n_keep, len(all_train_students),
            len(train_df), len(test_df),
        )
    elif args.data_fraction != 1.0:
        raise ValueError(f"--data-fraction must be in (0, 1], got {args.data_fraction}")

    # ── Mastery lookup ─────────────────────────────────────────────────────
    mastery_lookup = build_mastery_lookup(mastery_df, concept_to_idx)

    # ── Build datasets & loaders ──────────────────────────────────────────
    train_ds = SynthgenSequenceDataset(
        train_df, mastery_lookup, n_skills,
        seq_len=args.seq_len, stride=args.stride,
    )
    test_ds = SynthgenSequenceDataset(
        test_df, mastery_lookup, n_skills,
        seq_len=args.seq_len, stride=args.stride,
    )

    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=args.workers, pin_memory=(device.type == "cuda"),
        drop_last=True,
    )
    test_loader = DataLoader(
        test_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=args.workers,
    )
    logger.info(
        "Batches: train=%d  test=%d  (batch_size=%d)",
        len(train_loader), len(test_loader), args.batch_size,
    )

    # ── Build graph tensors ────────────────────────────────────────────────
    graph_data = build_graph_tensors(
        train_df, test_df, vocab,
        d_skill_embed=args.d_skill,
        device=device,
        data_dir=args.data_dir,
    )

    # ── Build model ────────────────────────────────────────────────────────
    model = ARCDModel(
        d_skill_embed=args.d_skill,
        d=args.d,
        n_gat_layers=args.n_gat_layers,
        n_questions=n_questions,
        n_videos=graph_data["A_vs"].size(0),
        n_readings=graph_data["A_rs"].size(0),
        n_students=n_students,
        n_skills=n_skills,
        n_heads_gat=2,    # small for CPU/MPS training
        d_type=16,
        n_heads=2,
        d_ff=args.d * 4,
        n_attn_layers=args.n_attn_layers,
        dropout=args.dropout,
        use_gat=True,
        student_emb_drop_p=args.student_emb_dropout,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Model parameters: %s", f"{n_params:,}")

    criterion = ARCDLoss(
        gamma=2.0, alpha=args.focal_alpha,
        label_smoothing=args.label_smoothing,
        mastery_weight=args.mastery_weight
    )

    trainer = ARCDTrainer(
        model=model,
        criterion=criterion,
        graph_data=graph_data,
        lr=args.lr,
        weight_decay=args.weight_decay,
        grad_clip=1.0,
        patience=args.patience,
        t0=10,
        warmup_epochs=args.warmup_epochs,
        rdrop_alpha=args.rdrop_alpha,
        device=device,
        use_amp=(device.type == "cuda"),
        gcn_refresh_every=5,
    )

    # ── Train ──────────────────────────────────────────────────────────────
    t0 = time.time()
    logger.info("=" * 60)
    logger.info(
        "Starting training — epochs=%d  seq_len=%d  batch=%d  device=%s",
        args.epochs, args.seq_len, args.batch_size, device,
    )
    logger.info("=" * 60)

    history = trainer.fit(train_loader, test_loader, n_epochs=args.epochs, verbose=True)
    elapsed = time.time() - t0
    logger.info(
        "Training complete in %.1fs — best val AUC: %.4f",
        elapsed, trainer.best_val_auc,
    )

    # ── Save checkpoint ────────────────────────────────────────────────────
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "model_state_dict": model.state_dict(),
        "model_config": {
            "d_skill_embed": args.d_skill,
            "d":              args.d,
            "n_gat_layers":   args.n_gat_layers,
            "n_questions":    n_questions,
            "n_videos":       graph_data["A_vs"].size(0),
            "n_readings":     graph_data["A_rs"].size(0),
            "n_students":     n_students,
            "n_skills":       n_skills,
            "n_heads_gat":    2,
            "d_type":         16,
            "n_heads":        2,
            "d_ff":           args.d * 4,
            "n_attn_layers":  args.n_attn_layers,
            "dropout":        args.dropout,
            "use_gat":        True,
            "student_emb_drop_p": args.student_emb_dropout,
        },
        "vocab_path":       str(data_dir / "vocab.json"),
        "best_val_auc":     trainer.best_val_auc,
        "epochs_trained":   len(history["val_auc"]),
        "training_time_s":  elapsed,
    }
    checkpoint_path = out_dir / "best_model.pt"
    torch.save(checkpoint, checkpoint_path)
    logger.info("Checkpoint saved → %s", checkpoint_path)

    # Copy vocab.json into the checkpoint dir so ModelRegistry can always find it.
    import shutil as _shutil
    _vocab_src = data_dir / "vocab.json"
    _vocab_dst = out_dir / "vocab.json"
    if _vocab_src.exists() and not _vocab_dst.exists():
        _shutil.copy(_vocab_src, _vocab_dst)

    (out_dir / "training_history.json").write_text(
        json.dumps(history, indent=2)
    )

    # ── Full MetricsSuite evaluation ───────────────────────────────────────
    logger.info("Running MetricsSuite on test set …")
    suite = MetricsSuite()
    try:
        metrics = evaluate_metrics(
            trainer, test_loader, suite,
            title=f"ARCD — {data_dir.name} (test)",
        )
    except Exception as exc:
        logger.warning("MetricsSuite failed: %s", exc)
        metrics = {"error": str(exc)}

    metrics_path = out_dir / "metrics_report.json"
    metrics_path.write_text(json.dumps(metrics, indent=2))
    logger.info("Metrics saved → %s", metrics_path)

    # ── Summary ────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Run complete.")
    logger.info("  Checkpoint  : %s", checkpoint_path)
    logger.info("  History     : %s", out_dir / 'training_history.json')
    logger.info("  Metrics     : %s", metrics_path)
    logger.info("  Best val AUC: %.4f", trainer.best_val_auc)
    logger.info("  Total time  : %.1fs", elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
