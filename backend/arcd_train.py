"""ARCD training CLI — trains ARCDModel on synthetic (or real) Parquet data.

Usage
-----
    cd backend
    uv run python arcd_train.py \
        --data-dir ../knowledge_graph_builder/data/synthgen/<run_id> \
        --out-dir  checkpoints/<run_id> \
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
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset

# Allow running from workspace root or backend/ directly
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from app.modules.arcd_agent.model.training import (  # noqa: E402
    ARCDLoss,
    ARCDModel,
    ARCDTrainer,
    MetricsSuite,
)

logger = logging.getLogger("arcd_train")


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j skill embedding loader
# ─────────────────────────────────────────────────────────────────────────────


def _load_skill_embeddings_from_neo4j(
    concept_idx: dict[str, int],
    d_skill_embed: int,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_database: str = "neo4j",
) -> torch.Tensor:
    """Load name_embedding from Neo4j skill nodes, ordered by concept_idx.

    Connects to Neo4j and fetches the 2048-dim name_embedding property for each
    skill node (SKILL | BOOK_SKILL | MARKET_SKILL). Validates dimension and
    raises immediately if any skill is missing an embedding — no fallback to
    Xavier init per project requirements.

    Returns
    -------
    torch.Tensor  shape [n_skills, d_skill_embed], dtype float32
    """
    try:
        from neo4j import GraphDatabase  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "neo4j package required to load skill embeddings. Run: uv add neo4j"
        ) from exc

    n_skills = len(concept_idx)
    names = list(concept_idx.keys())

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        with driver.session(database=neo4j_database) as session:
            result = session.run(
                """
                MATCH (s)
                WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
                  AND s.name IN $names
                RETURN s.name AS name, s.name_embedding AS emb
                """,
                names=names,
            )
            rows = {r["name"]: r["emb"] for r in result}
    finally:
        driver.close()

    H = torch.zeros(n_skills, d_skill_embed)
    missing = []
    wrong_dim = []

    for skill_name, idx in concept_idx.items():
        emb = rows.get(skill_name)
        if emb is None:
            missing.append(skill_name)
            continue
        if len(emb) != d_skill_embed:
            wrong_dim.append((skill_name, len(emb)))
            continue
        H[idx] = torch.tensor(emb, dtype=torch.float32)

    if missing:
        raise ValueError(
            f"{len(missing)} skills missing name_embedding in Neo4j: "
            f"{missing[:5]}{'...' if len(missing) > 5 else ''}\n"
            "Run the KG builder embedding step before training."
        )
    if wrong_dim:
        bad = wrong_dim[:3]
        raise ValueError(
            f"{len(wrong_dim)} skills have wrong embedding dim (expected {d_skill_embed}): "
            f"{bad}. Update --d-skill to match the KG embedding dimension."
        )

    logger.info(
        "Loaded name_embedding for %d/%d skills from Neo4j (%s, db=%s)",
        n_skills,
        n_skills,
        neo4j_uri,
        neo4j_database,
    )
    return H


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
    neo4j_uri: str = "",
    neo4j_user: str = "",
    neo4j_password: str = "",
    neo4j_database: str = "neo4j",
) -> dict[str, torch.Tensor]:
    """Build all 6 graph tensors from Parquet/vocab data.

    H_skill_raw is loaded from Neo4j name_embedding (2048-dim) rather than
    Xavier-initialized. This ensures skill embeddings are semantically grounded
    from the first training step.

    Returns
    -------
    H_skill_raw : [n_skills, d_skill_embed]   Neo4j name_embedding (2048-dim)
    A_pre       : [n_skills, n_skills]          row-norm prerequisite adj
    A_qs        : [n_questions, n_skills]        row-norm question-skill adj
    A_vs        : [n_videos, n_skills]           row-norm video-skill adj
    A_rs        : [n_readings, n_skills]         row-norm reading-skill adj
    A_uq        : [n_students, n_questions]      row-norm user-question adj
    """
    n_skills = len(vocab["concept"])
    n_questions = len(vocab["question"])
    # Reserve the LAST student-table row as the <UNK_STUDENT> slot for
    # cold-start / out-of-vocabulary students.  Real synthetic students keep
    # their indices 0..n_real_students-1 (matches synthgen vocab.json), and
    # n_real_students is the UNK index.
    n_real_students = len(vocab["user"])
    n_students = n_real_students + 1
    concept_idx: dict[str, int] = vocab["concept"]

    # H_skill_raw: load from Neo4j name_embedding (2048-dim, semantically grounded)
    if not (neo4j_uri and neo4j_user and neo4j_password):
        raise RuntimeError(
            "Neo4j credentials are required to initialize H_skill_raw from "
            "name_embedding. Pass --neo4j-uri / --neo4j-user / --neo4j-password "
            "or set LAB_TUTOR_NEO4J_URI / LAB_TUTOR_NEO4J_USERNAME / "
            "LAB_TUTOR_NEO4J_PASSWORD environment variables."
        )
    H_skill_raw = _load_skill_embeddings_from_neo4j(
        concept_idx,
        d_skill_embed,
        neo4j_uri,
        neo4j_user,
        neo4j_password,
        neo4j_database,
    ).to(device)

    # ── A_pre: prerequisite adjacency ────────────────────────────────────
    A_pre = _load_prereq_adjacency(data_dir, n_skills, concept_idx, device)

    # ── A_qs: question → skill ───────────────────────────────────────────
    # Backward-compat: support both new (event_type/entity_idx) and old
    # (question_idx) parquet schemas.
    all_df = pd.concat([train_df, test_df], ignore_index=True)
    if "event_type" in all_df.columns and "entity_idx" in all_df.columns:
        q_only = all_df[all_df["event_type"] == 0]
        qs_pairs_df = q_only[["entity_idx", "skill_idx"]].drop_duplicates()
    else:
        qs_pairs_df = all_df[["question_idx", "skill_idx"]].drop_duplicates()
        qs_pairs_df = qs_pairs_df.rename(columns={"question_idx": "entity_idx"})
    A_qs_raw = torch.zeros(n_questions, n_skills, device=device)
    for qi, si in qs_pairs_df.values.tolist():
        qi, si = int(qi), int(si)
        if 0 <= qi < n_questions and 0 <= si < n_skills:
            A_qs_raw[qi, si] = 1.0
    row_sum = A_qs_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
    A_qs = A_qs_raw / row_sum

    # ── A_vs / A_rs: real video/reading adjacency ────────────────────────
    A_vs = _load_video_adjacency(data_dir, vocab, n_skills, device)
    A_rs = _load_reading_adjacency(data_dir, vocab, n_skills, device)

    # ── A_uq: student → question (question events only) ──────────────────
    if "event_type" in train_df.columns and "entity_idx" in train_df.columns:
        uq_df = train_df[train_df["event_type"] == 0]
        uq_pairs_df = uq_df[["student_idx", "entity_idx"]].drop_duplicates()
    else:
        uq_pairs_df = train_df[["student_idx", "question_idx"]].drop_duplicates()
        uq_pairs_df = uq_pairs_df.rename(columns={"question_idx": "entity_idx"})
    # Note: A_uq has shape [n_real_students + 1, n_questions].  The UNK row
    # (index n_real_students) is intentionally left all-zero so the GCN learns
    # the UNK student embedding purely from gradient signal during cold-start
    # dropout, never from any real student's interactions.
    A_uq_raw = torch.zeros(n_students, n_questions, device=device)
    for ui, qi in uq_pairs_df.values.tolist():
        ui, qi = int(ui), int(qi)
        if 0 <= ui < n_real_students and 0 <= qi < n_questions:
            A_uq_raw[ui, qi] = 1.0
    uq_sum = A_uq_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
    A_uq = A_uq_raw / uq_sum

    logger.info(
        "Graph tensors — n_skills=%d  n_questions=%d  n_students=%d "
        "(real=%d, +1 UNK)  n_videos=%d  n_readings=%d",
        n_skills,
        n_questions,
        n_students,
        n_real_students,
        A_vs.size(0),
        A_rs.size(0),
    )
    return {
        "H_skill_raw": H_skill_raw,
        "A_pre": A_pre,
        "A_qs": A_qs,
        "A_vs": A_vs,
        "A_rs": A_rs,
        "A_uq": A_uq,
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
                logger.warning(
                    "Failed to load prereq_edges.parquet (%s) — using identity", exc
                )
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
                n_videos = len(vocab.get("video", {})) or (
                    df["video_idx"].max() + 1 if len(df) else 1
                )
                n_videos = max(n_videos, 1)
                A = torch.zeros(n_videos, n_skills, device=device)
                for _, row in df.iterrows():
                    vi, si = int(row["video_idx"]), int(row["skill_idx"])
                    if 0 <= vi < n_videos and 0 <= si < n_skills:
                        A[vi, si] = 1.0
                row_sum = A.sum(dim=1, keepdim=True).clamp(min=1.0)
                logger.info(
                    "A_vs: loaded %d video-skill edges, n_videos=%d", len(df), n_videos
                )
                return (A / row_sum).to(device)
            except Exception as exc:
                logger.warning(
                    "Failed to load skill_videos.parquet (%s) — using dummy", exc
                )
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
                n_readings = len(vocab.get("reading", {})) or (
                    df["reading_idx"].max() + 1 if len(df) else 1
                )
                n_readings = max(n_readings, 1)
                A = torch.zeros(n_readings, n_skills, device=device)
                for _, row in df.iterrows():
                    ri, si = int(row["reading_idx"]), int(row["skill_idx"])
                    if 0 <= ri < n_readings and 0 <= si < n_skills:
                        A[ri, si] = 1.0
                row_sum = A.sum(dim=1, keepdim=True).clamp(min=1.0)
                logger.info(
                    "A_rs: loaded %d reading-skill edges, n_readings=%d",
                    len(df),
                    n_readings,
                )
                return (A / row_sum).to(device)
            except Exception as exc:
                logger.warning(
                    "Failed to load skill_readings.parquet (%s) — using dummy", exc
                )
    logger.warning("A_rs: no skill_readings.parquet found — using dummy (1, n_skills)")
    return torch.zeros(1, n_skills, device=device)


# ─────────────────────────────────────────────────────────────────────────────
# Mastery lookup
# ─────────────────────────────────────────────────────────────────────────────


def build_mastery_lookup(
    mastery_df: pd.DataFrame,
    concept_to_idx: dict[str, int],
) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    """Build mastery + mask lookups from mastery_ground_truth.parquet.

    Returns
    -------
    mastery_lookup : {student_idx → float32[n_skills]} ground-truth mastery,
                     0.0 for skills with no observed target.
    mask_lookup    : {student_idx → float32[n_skills]} 1.0 where mastery was
                     observed in the parquet, 0.0 otherwise.  Critical for the
                     masked MasteryLoss — without this the model collapses to
                     predicting zero everywhere because synthgen only emits
                     ground-truth mastery for ~5% of (student, skill) pairs.

    student_id format: "synth_{i:04d}_{run_id}" → student_idx = i
    (valid because zero-padded IDs sort in numeric order, making sorted-position = i).
    """
    n_skills = len(concept_to_idx)
    mastery_lookup: dict[int, np.ndarray] = {}
    mask_lookup: dict[int, np.ndarray] = {}

    grouped = mastery_df.groupby("student_id")
    for sid, grp in grouped:
        try:
            student_idx = int(str(sid).split("_")[1])
        except (IndexError, ValueError):
            logger.debug("Cannot parse student_idx from %r — skipping", sid)
            continue

        arr = np.zeros(n_skills, dtype=np.float32)
        mask = np.zeros(n_skills, dtype=np.float32)
        for _, row in grp.iterrows():
            cidx = concept_to_idx.get(str(row["skill_id"]))
            if cidx is not None:
                arr[cidx] = float(row["mastery"])
                mask[cidx] = 1.0
        mastery_lookup[student_idx] = arr
        mask_lookup[student_idx] = mask

    n_students_with_targets = len(mastery_lookup)
    if n_students_with_targets > 0:
        avg_observed = float(np.mean([m.sum() for m in mask_lookup.values()]))
        logger.info(
            "Mastery lookup: %d / %d students have targets — avg %.1f / %d "
            "skills observed per student (%.1f%% coverage)",
            n_students_with_targets,
            mastery_df["student_id"].nunique(),
            avg_observed,
            n_skills,
            100.0 * avg_observed / max(n_skills, 1),
        )
    return mastery_lookup, mask_lookup


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

    # Sentinel for skills the student has never practiced: 30 days in seconds.
    # BaseDecay divides by 86400 internally, so exp(-0.02 × 30) ≈ 0.55 retention.
    _NEVER_PRACTICED_SEC: float = 30.0 * 86400.0
    _MAX_DELTA_T_SEC: float = 365.0 * 86400.0  # 1-year hard cap

    def __init__(
        self,
        df: pd.DataFrame,
        mastery_lookup: dict[int, np.ndarray],
        n_skills: int,
        seq_len: int = 50,
        stride: int = 1,
        question_skill_map: dict[int, int] | None = None,
        mask_lookup: dict[int, np.ndarray] | None = None,
    ):
        self.seq_len = seq_len
        self.n_skills = n_skills
        self._zero_mastery = np.zeros(n_skills, dtype=np.float32)
        self._zero_mask = np.zeros(n_skills, dtype=np.float32)
        self.mastery_lookup = mastery_lookup
        # mask_lookup[uid][s] == 1.0 iff a ground-truth mastery exists for
        # (student uid, skill s).  Critical for masked MasteryLoss.
        self.mask_lookup: dict[int, np.ndarray] = mask_lookup or {}
        # Maps question entity_idx → skill_idx for delta_t_skills computation.
        # None means we fall back to zeros (pre-training-gap behaviour).
        self.q_to_skill: dict[int, int] = question_skill_map or {}

        df = df.sort_values(["student_idx", "timestamp_sec"]).reset_index(drop=True)

        # Backward-compat: old parquets may lack event_type / entity_idx and
        # only carry question events under "question_idx".
        has_event_cols = "event_type" in df.columns and "entity_idx" in df.columns
        if not has_event_cols:
            df = df.copy()
            df["event_type"] = 0
            df["entity_idx"] = df["question_idx"]

        # Per-student timeline of (event_type, entity_idx, outcome, timestamp)
        student_events: dict[int, list[tuple]] = defaultdict(list)
        for row in df.itertuples(index=False):
            student_events[int(row.student_idx)].append(
                (
                    int(row.event_type),
                    int(row.entity_idx),
                    float(row.correct),
                    float(row.timestamp_sec),
                )
            )

        # A valid training window must end on a QUESTION event (event_type=0)
        # — only questions carry a binary correctness label we can supervise on.
        # Video/reading events are kept in history for temporal attention.
        self.examples: list[tuple] = []
        n_q_targets = 0
        for uid, events in student_events.items():
            if len(events) < 2:
                continue
            for end in range(2, len(events) + 1, stride):
                if events[end - 1][0] != 0:
                    continue  # target must be a question
                window = events[max(0, end - seq_len) : end]
                if len(window) < 2:
                    continue
                self.examples.append((uid, window))
                n_q_targets += 1

        logger.info(
            "Dataset: %d students → %d question-target windows "
            "(seq_len=%d stride=%d, history may include video/reading)",
            len(student_events),
            n_q_targets,
            seq_len,
            stride,
        )

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        uid, window = self.examples[idx]
        hist = window[:-1]
        tgt_type, tgt_idx, tgt_correct, _ = window[-1]

        T = self.seq_len - 1
        pad_len = T - len(hist)

        # Right-padding: real events on the LEFT, padding on the RIGHT.
        # Matches TemporalAttentionModel which uses `~pad_mask` to block keys
        # and `pad_mask.sum()-1` to index the last valid event.
        event_types = [e[0] for e in hist] + [0] * pad_len
        entity_indices = [e[1] for e in hist] + [0] * pad_len
        outcomes = [e[2] for e in hist] + [0.0] * pad_len
        timestamps = [e[3] for e in hist] + [0.0] * pad_len
        decay_values = [0.0] * T
        pad_mask = [True] * len(hist) + [False] * pad_len

        mastery = self.mastery_lookup.get(uid, self._zero_mastery)
        mastery_mask = self.mask_lookup.get(uid, self._zero_mask)

        # Per-skill delta_t in seconds.  BaseDecay divides internally by 86400.
        # Skills never practiced in this window get the 30-day sentinel so the
        # model sees them as "mostly forgotten" rather than "just practiced".
        current_ts = window[-1][3]  # target event timestamp = "now"
        skill_last_ts_local: dict[int, float] = {}
        for ev_type, entity_idx, _, ts in hist:
            if ev_type == 0:  # question events carry skill signal
                si = self.q_to_skill.get(entity_idx)
                if si is not None and (
                    si not in skill_last_ts_local or ts > skill_last_ts_local[si]
                ):
                    skill_last_ts_local[si] = ts

        delta_t_skills = np.full(
            self.n_skills, self._NEVER_PRACTICED_SEC, dtype=np.float32
        )
        for si, last_ts in skill_last_ts_local.items():
            delta_t_skills[si] = min(
                max(0.0, current_ts - last_ts), self._MAX_DELTA_T_SEC
            )

        return {
            "student_ids": torch.tensor(uid, dtype=torch.long),
            "event_types": torch.tensor(event_types, dtype=torch.long),
            "entity_indices": torch.tensor(entity_indices, dtype=torch.long),
            "outcomes": torch.tensor(outcomes, dtype=torch.float32),
            "timestamps": torch.tensor(timestamps, dtype=torch.float32),
            "decay_values": torch.tensor(decay_values, dtype=torch.float32),
            "pad_mask": torch.tensor(pad_mask, dtype=torch.bool),
            "target_type": torch.tensor(int(tgt_type), dtype=torch.long),
            "target_idx": torch.tensor(int(tgt_idx), dtype=torch.long),
            "response_target": torch.tensor(float(tgt_correct), dtype=torch.float32),
            "mastery_target": torch.tensor(mastery, dtype=torch.float32),
            "mastery_mask": torch.tensor(mastery_mask, dtype=torch.float32),
            "delta_t_skills": torch.tensor(delta_t_skills, dtype=torch.float32),
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

    probs = torch.sigmoid(torch.cat(all_logits)).numpy()
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
        "--data-dir",
        type=Path,
        required=True,
        help="synthgen run directory (train.parquet / test.parquet / vocab.json)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("checkpoints/synthgen"),
        help="Output directory for checkpoints and metrics",
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--seq-len", type=int, default=50)
    parser.add_argument(
        "--stride",
        type=int,
        default=5,
        help="Sliding-window stride (lower = more examples, slower)",
    )
    parser.add_argument("--lr", type=float, default=1e-3)
    # NOTE: Both --d and --d-skill must equal 2048 to match the knowledge graph's
    # native node embedding dimension (name_embedding on skill nodes).
    # All 5 GAT stage outputs (h_s, h_qa, h_v, h_r, h_u) will be written back
    # to Neo4j at 2048-dim so they stay consistent with the existing KG embeddings.
    parser.add_argument(
        "--d",
        type=int,
        default=2048,
        help="Model hidden dim (must equal KG embedding dim = 2048)",
    )
    parser.add_argument(
        "--d-skill",
        type=int,
        default=2048,
        help="Skill input embedding dim (must equal KG embedding dim = 2048)",
    )
    parser.add_argument("--n-gat-layers", type=int, default=2)
    parser.add_argument("--n-attn-layers", type=int, default=2)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument(
        "--warmup-epochs",
        type=int,
        default=2,
        help="Linear LR warmup epochs before cosine annealing",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="DataLoader worker processes (default 8 for MPS)",
    )
    parser.add_argument(
        "--bf16",
        action="store_true",
        help="Enable bfloat16 autocast on MPS (~30-50%% speedup, no GradScaler needed)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Force device: cuda, mps, cpu (auto-detect if omitted)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--mastery-weight",
        type=float,
        default=0.2,
        help="Weight for the (now masked) MasteryLoss in ARCDLoss.  Kept low "
        "because mastery targets cover only ~5%% of skills per student, so the "
        "mastery gradient is sparse and noisy — 0.2 keeps it as a supporting "
        "signal without drowning out the correctness (focal) objective.",
    )
    parser.add_argument(
        "--focal-alpha",
        type=float,
        default=0.25,
        help="Focal loss alpha (positive-class weight). With ~79%% correct responses "
        "use 0.25 to down-weight the dominant positive class and focus on hard negatives.",
    )
    parser.add_argument(
        "--dropout", type=float, default=0.2, help="Dropout rate for ARCDModel"
    )
    parser.add_argument(
        "--student-emb-dropout",
        type=float,
        default=0.3,
        help="Probability of swapping a student id for the reserved UNK slot "
        "during training (cold-start dropout).  Trains the UNK row to act as "
        "a generic prior for OOV / unseen students at inference.  Note: this "
        "no longer ZEROES e_u (v3 behaviour) — it routes through UNK.",
    )
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=5e-4,
        help="AdamW weight decay for regularization",
    )
    parser.add_argument(
        "--rdrop-alpha",
        type=float,
        default=0.3,
        help="R-Drop KL consistency loss weight (0 = disabled)",
    )
    parser.add_argument(
        "--label-smoothing",
        type=float,
        default=0.1,
        help="Label smoothing epsilon for FocalLoss (0 = hard targets)",
    )
    parser.add_argument(
        "--data-fraction",
        type=float,
        default=1.0,
        metavar="FRAC",
        help="Fraction of students to keep (0 < FRAC ≤ 1.0). "
        "Students are sampled by ID so every sequence in their "
        "history is preserved.  Default: 1.0 (all data).",
    )
    # Neo4j credentials for H_skill_raw initialisation from name_embedding.
    # All 5 GAT outputs are written back to Neo4j after training.
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=os.environ.get("LAB_TUTOR_NEO4J_URI", ""),
        help="Neo4j bolt URI (env: LAB_TUTOR_NEO4J_URI)",
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=os.environ.get("LAB_TUTOR_NEO4J_USERNAME", ""),
        help="Neo4j username (env: LAB_TUTOR_NEO4J_USERNAME)",
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=os.environ.get("LAB_TUTOR_NEO4J_PASSWORD", ""),
        help="Neo4j password (env: LAB_TUTOR_NEO4J_PASSWORD)",
    )
    parser.add_argument(
        "--neo4j-database",
        type=str,
        default=os.environ.get("LAB_TUTOR_NEO4J_DATABASE", "neo4j"),
        help="Neo4j database name (env: LAB_TUTOR_NEO4J_DATABASE)",
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

    train_df = pd.read_parquet(data_dir / "train.parquet")
    test_df = pd.read_parquet(data_dir / "test.parquet")
    mastery_df = pd.read_parquet(data_dir / "mastery_ground_truth.parquet")

    with open(data_dir / "vocab.json") as f:
        vocab = json.load(f)

    n_skills = len(vocab["concept"])
    n_questions = len(vocab["question"])
    # Student table = real students + 1 reserved <UNK_STUDENT> slot at the
    # last index.  Cold-start dropout (training) and OOV inference both route
    # to this slot so the UNK row learns a generic prior instead of
    # contaminating real student 0 (the v3 bug).
    n_real_students = len(vocab["user"])
    n_students = n_real_students + 1
    unk_student_idx = n_real_students  # last row of the embedding tables
    concept_to_idx: dict[str, int] = vocab["concept"]

    logger.info(
        "Dataset: train=%d  test=%d  mastery=%d rows  "
        "(skills=%d  questions=%d  real_students=%d  unk_idx=%d)",
        len(train_df),
        len(test_df),
        len(mastery_df),
        n_skills,
        n_questions,
        n_real_students,
        unk_student_idx,
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

        train_df = train_df[train_df["student_idx"].isin(kept_set)].reset_index(
            drop=True
        )
        test_df = test_df[test_df["student_idx"].isin(kept_set)].reset_index(drop=True)
        mastery_df = mastery_df[
            mastery_df["student_id"].isin(
                {f"synth_{i:04d}_{data_dir.name}" for i in kept_set}
            )
        ].reset_index(drop=True)

        logger.info(
            "data-fraction=%.2f → kept %d/%d students  (train=%d  test=%d rows)",
            args.data_fraction,
            n_keep,
            len(all_train_students),
            len(train_df),
            len(test_df),
        )
    elif args.data_fraction != 1.0:
        raise ValueError(f"--data-fraction must be in (0, 1], got {args.data_fraction}")

    # ── Mastery lookup ─────────────────────────────────────────────────────
    mastery_lookup, mastery_mask_lookup = build_mastery_lookup(
        mastery_df, concept_to_idx
    )

    # ── Build datasets & loaders ──────────────────────────────────────────
    # ── question → skill map (used by dataset for delta_t_skills) ────────
    _qs_df_all = pd.concat([train_df, test_df], ignore_index=True)
    if "event_type" in _qs_df_all.columns and "entity_idx" in _qs_df_all.columns:
        _q_pairs = _qs_df_all[_qs_df_all["event_type"] == 0][
            ["entity_idx", "skill_idx"]
        ].drop_duplicates()
        question_skill_map: dict[int, int] = {
            int(r.entity_idx): int(r.skill_idx) for r in _q_pairs.itertuples()
        }
    else:
        _q_pairs = _qs_df_all[["question_idx", "skill_idx"]].drop_duplicates()
        question_skill_map = {
            int(r.question_idx): int(r.skill_idx) for r in _q_pairs.itertuples()
        }
    del _qs_df_all, _q_pairs

    train_ds = SynthgenSequenceDataset(
        train_df,
        mastery_lookup,
        n_skills,
        seq_len=args.seq_len,
        stride=args.stride,
        question_skill_map=question_skill_map,
        mask_lookup=mastery_mask_lookup,
    )
    test_ds = SynthgenSequenceDataset(
        test_df,
        mastery_lookup,
        n_skills,
        seq_len=args.seq_len,
        stride=args.stride,
        question_skill_map=question_skill_map,
        mask_lookup=mastery_mask_lookup,
    )

    _use_workers = args.workers > 0
    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.workers,
        pin_memory=(device.type == "cuda"),
        persistent_workers=_use_workers,
        drop_last=True,
    )
    test_loader = DataLoader(
        test_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        persistent_workers=_use_workers,
    )
    logger.info(
        "Batches: train=%d  test=%d  (batch_size=%d)",
        len(train_loader),
        len(test_loader),
        args.batch_size,
    )

    # ── Build graph tensors ────────────────────────────────────────────────
    graph_data = build_graph_tensors(
        train_df,
        test_df,
        vocab,
        d_skill_embed=args.d_skill,
        device=device,
        data_dir=args.data_dir,
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
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
        n_heads_gat=2,  # small for CPU/MPS training
        d_type=16,
        n_heads=2,
        d_ff=args.d * 4,
        n_attn_layers=args.n_attn_layers,
        dropout=args.dropout,
        use_gat=True,
        student_emb_drop_p=args.student_emb_dropout,
        unk_student_idx=unk_student_idx,
    ).to(device)

    # Wire RelationalDecay from the prerequisite graph — MUST happen before
    # ARCDTrainer is constructed so rel_decay.w_p_logit is included in
    # model.parameters() and picked up by the AdamW optimizer.
    model.set_prerequisite_graph(graph_data["A_pre"].cpu())

    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Model parameters: %s", f"{n_params:,}")

    criterion = ARCDLoss(
        gamma=2.0,
        alpha=args.focal_alpha,
        label_smoothing=args.label_smoothing,
        mastery_weight=args.mastery_weight,
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
        use_bf16=args.bf16 and device.type == "mps",
        gcn_refresh_every=3,
    )

    # ── Train ──────────────────────────────────────────────────────────────
    t0 = time.time()
    logger.info("=" * 60)
    logger.info(
        "Starting training — epochs=%d  seq_len=%d  batch=%d  device=%s",
        args.epochs,
        args.seq_len,
        args.batch_size,
        device,
    )
    logger.info("=" * 60)

    history = trainer.fit(train_loader, test_loader, n_epochs=args.epochs, verbose=True)
    elapsed = time.time() - t0
    logger.info(
        "Training complete in %.1fs — best val AUC: %.4f",
        elapsed,
        trainer.best_val_auc,
    )

    # ── Save checkpoint ────────────────────────────────────────────────────
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "model_state_dict": model.state_dict(),
        # H_skill_raw is persisted so model_registry.py can restore it exactly
        # rather than falling back to Xavier init.  Shape: [n_skills, d_skill_embed]
        "H_skill_raw": graph_data["H_skill_raw"].cpu(),
        "model_config": {
            "d_skill_embed": args.d_skill,
            "d": args.d,
            "n_gat_layers": args.n_gat_layers,
            "n_questions": n_questions,
            "n_videos": graph_data["A_vs"].size(0),
            "n_readings": graph_data["A_rs"].size(0),
            "n_students": n_students,
            "n_skills": n_skills,
            "n_heads_gat": 2,
            "d_type": 16,
            "n_heads": 2,
            "d_ff": args.d * 4,
            "n_attn_layers": args.n_attn_layers,
            "dropout": args.dropout,
            "use_gat": True,
            "student_emb_drop_p": args.student_emb_dropout,
            "unk_student_idx": unk_student_idx,
        },
        "vocab_path": str(data_dir / "vocab.json"),
        "best_val_auc": trainer.best_val_auc,
        "epochs_trained": len(history["val_auc"]),
        "training_time_s": elapsed,
    }
    checkpoint_path = out_dir / "best_model.pt"
    torch.save(checkpoint, checkpoint_path)
    logger.info("Checkpoint saved → %s", checkpoint_path)

    # Copy vocab + graph parquet files into the checkpoint dir so ModelRegistry
    # can always find them — it resolves data_dir as vocab_path.parent.
    # Also enrich vocab.json with a question_skill mapping (integer index → integer
    # index via the parquet) so A_qs is built without needing the parquet fallback.
    import shutil as _shutil

    all_df = pd.concat([train_df, test_df], ignore_index=True)
    if "event_type" in all_df.columns and "entity_idx" in all_df.columns:
        _q_df = all_df[all_df["event_type"] == 0][
            ["entity_idx", "skill_idx"]
        ].drop_duplicates()
    else:
        _q_df = (
            all_df[["question_idx", "skill_idx"]]
            .drop_duplicates()
            .rename(columns={"question_idx": "entity_idx"})
        )
    # Build name → name mapping for ModelRegistry (qi_name → si_name)
    _idx2q = {v: k for k, v in vocab["question"].items()}
    _idx2c = {v: k for k, v in vocab["concept"].items()}
    _qs_name_map: dict[str, str] = {}
    for _qi, _si in _q_df.values.tolist():
        _qn, _cn = _idx2q.get(int(_qi)), _idx2c.get(int(_si))
        if _qn and _cn:
            _qs_name_map[_qn] = _cn
    vocab["question_skill"] = _qs_name_map
    logger.info(
        "question_skill mapping: %d entries written to checkpoint vocab.json",
        len(_qs_name_map),
    )

    _vocab_dst = out_dir / "vocab.json"
    _vocab_dst.write_text(json.dumps(vocab, indent=2))

    for _fname in [
        "prereq_edges.parquet",
        "skill_videos.parquet",
        "skill_readings.parquet",
        "train.parquet",
        "test.parquet",
    ]:
        _src = data_dir / _fname
        _dst = out_dir / _fname
        if _src.exists() and not _dst.exists():
            _shutil.copy(_src, _dst)

    (out_dir / "training_history.json").write_text(json.dumps(history, indent=2))

    # ── Full MetricsSuite evaluation ───────────────────────────────────────
    logger.info("Running MetricsSuite on test set …")
    suite = MetricsSuite()
    try:
        metrics = evaluate_metrics(
            trainer,
            test_loader,
            suite,
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
    logger.info("  History     : %s", out_dir / "training_history.json")
    logger.info("  Metrics     : %s", metrics_path)
    logger.info("  Best val AUC: %.4f", trainer.best_val_auc)
    logger.info("  Total time  : %.1fs", elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
