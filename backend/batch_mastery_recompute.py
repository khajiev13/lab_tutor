"""batch_mastery_recompute.py — Phase 4 validation script.

Re-runs mastery prediction for every synthetic student using the trained
ARCDModel checkpoint and writes the results back to Neo4j.  Prints a
concise dashboard-validation report.

Usage
-----
    cd backend
    LAB_TUTOR_DATABASE_URL=... uv run python -m batch_mastery_recompute \
        --data-dir ../knowledge_graph_builder/data/synthgen/<run_id> \
        --checkpoint-dir checkpoints/roma_synth_v6_2048 \
        [--run-id <run_id>] [--limit 20]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("batch_mastery")


# ── helpers ───────────────────────────────────────────────────────────────────


def _build_graph(
    vocab: dict, cfg: dict, device: torch.device
) -> dict[str, torch.Tensor]:
    """Reconstruct normalised graph tensors from vocab (no Parquet needed)."""
    import torch.nn as nn

    n_skills = cfg["n_skills"]
    n_questions = cfg["n_questions"]
    n_students = cfg["n_students"]

    H = torch.empty(n_skills, cfg["d_skill_embed"], device=device)
    nn.init.xavier_uniform_(H)

    A_pre = torch.eye(n_skills, device=device)

    A_qs_raw = torch.zeros(n_questions, n_skills, device=device)
    for q_name, skill_name in vocab.get("question_skill", {}).items():
        qi = vocab["question"].get(q_name)
        si = vocab["concept"].get(skill_name)
        if qi is not None and si is not None:
            A_qs_raw[qi, si] = 1.0
    row_sum = A_qs_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
    A_qs = A_qs_raw / row_sum

    return {
        "H_skill_raw": H,
        "A_pre": A_pre,
        "A_qs": A_qs,
        "A_vs": torch.zeros(1, n_skills, device=device),
        "A_rs": torch.zeros(1, n_skills, device=device),
        "A_uq": torch.zeros(n_students, n_questions, device=device),
    }


def _build_sequence(
    interactions: list[tuple[int, int, float]],
    seq_len: int,
    device: torch.device,
) -> dict[str, torch.Tensor]:
    """Right-pad a single student sequence into a batch-of-1 dict."""
    recent = interactions[-(seq_len - 1) :]
    T = seq_len - 1
    pad_len = T - len(recent)

    # event_types: 0=question, 1=video, 2=reading — all synthgen events are questions
    event_types = [0] * len(recent) + [0] * pad_len
    entity_indices = [e[0] for e in recent] + [0] * pad_len
    outcomes = [float(e[1]) for e in recent] + [0.0] * pad_len
    timestamps = [float(e[2]) for e in recent] + [0.0] * pad_len
    decay_values = [0.0] * T
    pad_mask = [True] * len(recent) + [False] * pad_len

    return {
        "student_ids": torch.tensor([0], dtype=torch.long, device=device),
        "event_types": torch.tensor([event_types], dtype=torch.long, device=device),
        "entity_indices": torch.tensor(
            [entity_indices], dtype=torch.long, device=device
        ),
        "outcomes": torch.tensor([outcomes], dtype=torch.float32, device=device),
        "timestamps": torch.tensor([timestamps], dtype=torch.float32, device=device),
        "decay_values": torch.tensor(
            [decay_values], dtype=torch.float32, device=device
        ),
        "pad_mask": torch.tensor([pad_mask], dtype=torch.bool, device=device),
        "target_type": torch.tensor([0], dtype=torch.long, device=device),
        "target_idx": torch.tensor([0], dtype=torch.long, device=device),
    }


# ── Neo4j mastery upsert ───────────────────────────────────────────────────────


def _upsert_mastery_neo4j(
    neo4j_driver,
    user_neo4j_id: str,
    mastery_records: list[dict],
    db: str,
) -> None:
    """Write MASTERED edges to Neo4j for one student."""
    cypher = """
    UNWIND $rows AS row
    MATCH (u:USER {user_id: $uid})
    MATCH (sk:SKILL {name: row.skill_name})
    MERGE (u)-[m:MASTERED]->(sk)
    SET m.mastery       = row.mastery,
        m.decay         = row.decay,
        m.status        = row.status,
        m.attempt_count = row.attempt_count,
        m.model_version = row.model_version,
        m.updated_at    = timestamp()
    """
    with neo4j_driver.session(database=db) as session:
        session.run(cypher, uid=user_neo4j_id, rows=mastery_records)


# ── Dashboard API smoke-tests ──────────────────────────────────────────────────


def _smoke_test_api(base_url: str, token: str, user_id: int, course_id: int) -> dict:
    """Call the main dashboard endpoints for one student and return status codes."""
    import http.client
    import urllib.parse

    results: dict[str, int] = {}
    headers = {"Authorization": f"Bearer {token}"}
    u = urllib.parse.urlparse(base_url)
    conn = http.client.HTTPConnection(u.netloc)

    endpoints = {
        "GET /mastery": f"/api/cognitive-diagnosis/mastery/{user_id}?course_id={course_id}",
        "POST /mastery": None,  # skip write endpoint
        "GET /path": f"/api/cognitive-diagnosis/path/{user_id}/{course_id}",
        "GET /portfolio": f"/api/cognitive-diagnosis/portfolio/{user_id}/{course_id}",
    }

    for label, path in endpoints.items():
        if path is None:
            continue
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            resp.read()
            results[label] = resp.status
        except Exception as exc:
            results[label] = f"ERR:{exc}"

    conn.close()
    return results


# ── Main ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Batch mastery recompute for synthetic students"
    )
    parser.add_argument(
        "--data-dir", required=True, help="Path to synthgen data directory"
    )
    parser.add_argument(
        "--checkpoint-dir",
        required=True,
        help="Path to arcd_train checkpoint directory",
    )
    parser.add_argument(
        "--run-id", default="roma_synth_v6_2048", help="Synthgen run_id tag"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only first N students (for quick test)",
    )
    parser.add_argument("--seq-len", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", help="Skip Neo4j writes")
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    ckpt_dir = Path(args.checkpoint_dir)

    # ── Load vocab and checkpoint ─────────────────────────────────────────────
    vocab_path = ckpt_dir / "vocab.json"
    if not vocab_path.exists():
        vocab_path = data_dir / "vocab.json"
    vocab = json.loads(vocab_path.read_text())

    ckpt = torch.load(
        ckpt_dir / "best_model.pt", map_location="cpu", weights_only=False
    )
    cfg = ckpt["model_config"]
    logger.info(
        "Checkpoint: n_skills=%d  n_questions=%d  val_AUC=%.4f",
        cfg["n_skills"],
        cfg["n_questions"],
        ckpt["best_val_auc"],
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    from arcd_agent.model.training import ARCDModel

    model = ARCDModel(**cfg).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    gd = _build_graph(vocab, cfg, device)

    idx_to_concept: dict[int, str] = {v: k for k, v in vocab["concept"].items()}
    idx_to_user: dict[int, str] = {v: k for k, v in vocab["user"].items()}
    n_concepts = len(vocab["concept"])

    # ── Load interaction data ─────────────────────────────────────────────────
    df = pd.concat(
        [
            pd.read_parquet(data_dir / "train.parquet"),
            pd.read_parquet(data_dir / "test.parquet"),
        ],
        ignore_index=True,
    ).sort_values(["student_idx", "timestamp_sec"])

    mastery_gt_df = pd.read_parquet(data_dir / "mastery_ground_truth.parquet")
    # Ground truth: one row per (student_id, skill_id).
    # Build a per-student mastery vector indexed by concept idx.
    concept_to_idx: dict[str, int] = vocab["concept"]
    mastery_gt: dict[int, np.ndarray] = {}
    for sid_str, grp in mastery_gt_df.groupby("student_id"):
        parts = str(sid_str).split("_")
        if len(parts) < 2 or not parts[1].isdigit():
            continue
        student_idx = int(parts[1])
        vec = np.zeros(n_concepts, dtype=np.float32)
        for _, row in grp.iterrows():
            cidx = concept_to_idx.get(str(row["skill_id"]))
            if cidx is not None:
                vec[cidx] = float(row["mastery"])
        mastery_gt[student_idx] = vec

    student_indices = sorted(df["student_idx"].unique())
    if args.limit:
        student_indices = student_indices[: args.limit]
    logger.info("Processing %d students", len(student_indices))

    # ── Neo4j driver (optional) ──────────────────────────────────────────────
    neo4j_driver = None
    if not args.dry_run:
        neo4j_uri = os.environ.get("LAB_TUTOR_NEO4J_URI", "")
        neo4j_user = os.environ.get("LAB_TUTOR_NEO4J_USERNAME", "neo4j")
        neo4j_pass = os.environ.get("LAB_TUTOR_NEO4J_PASSWORD", "")
        neo4j_database = os.environ.get("LAB_TUTOR_NEO4J_DATABASE", "neo4j")
        if neo4j_uri:
            from neo4j import GraphDatabase

            neo4j_driver = GraphDatabase.driver(
                neo4j_uri, auth=(neo4j_user, neo4j_pass)
            )
            logger.info("Neo4j connected: %s / db=%s", neo4j_uri, neo4j_database)
        else:
            logger.warning("LAB_TUTOR_NEO4J_URI not set — skipping Neo4j writes")

    # ── Batch inference ───────────────────────────────────────────────────────
    model_masteries: list[np.ndarray] = []
    gt_masteries: list[np.ndarray] = []
    neo4j_batch: list[dict] = []  # collected for batched write after loop
    t0 = time.time()

    for sidx in student_indices:
        group = df[df["student_idx"] == sidx]
        interactions = list(
            zip(
                group["question_idx"].tolist(),
                group["correct"].tolist(),
                group["timestamp_sec"].tolist(),
                strict=False,
            )
        )
        batch = _build_sequence(interactions, args.seq_len, device)

        with torch.no_grad():
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
        mastery_pred = out["mastery"][0].cpu().numpy()  # [n_skills]
        model_masteries.append(mastery_pred)

        gt = mastery_gt.get(sidx)
        if gt is not None:
            size = min(len(mastery_pred), len(gt))
            gt_masteries.append((mastery_pred[:size], gt[:size]))

        # ── Collect Neo4j records ──────────────────────────────────────────────
        if neo4j_driver and not args.dry_run:
            user_name = idx_to_user.get(sidx, f"synth_student_{sidx}")
            try:
                pg_id = int(user_name)
            except (ValueError, TypeError):
                logger.warning(
                    "Cannot resolve pg_id for student_idx %d (user_name=%s) — skipping",
                    sidx,
                    user_name,
                )
                continue
            for ci, m in enumerate(mastery_pred):
                cname = idx_to_concept.get(ci)
                if not cname:
                    continue
                m_float = float(np.clip(m, 0.0, 1.0))
                status = (
                    "not_started"
                    if m_float == 0.0
                    else "below"
                    if m_float < 0.4
                    else "at"
                    if m_float <= 0.9
                    else "above"
                )
                neo4j_batch.append(
                    {
                        "pg_id": pg_id,
                        "skill_name": cname,
                        "mastery": round(m_float, 4),
                        "decay": 0.8,
                        "status": status,
                        "attempt_count": len(interactions),
                        "model_version": "arcd_v2_model",
                    }
                )

    elapsed = time.time() - t0
    logger.info(
        "Inference done: %.1f s (%.1f students/s)",
        elapsed,
        len(student_indices) / max(elapsed, 0.001),
    )

    # ── Batched Neo4j write ───────────────────────────────────────────────────
    students_written = 0
    if neo4j_driver and neo4j_batch:
        cypher = """
        UNWIND $rows AS row
        MATCH (u:USER:STUDENT {id: row.pg_id})
        MATCH (sk {name: row.skill_name})
        WHERE (sk:SKILL OR sk:BOOK_SKILL OR sk:MARKET_SKILL)
        MERGE (u)-[m:MASTERED]->(sk)
        SET m.mastery       = row.mastery,
            m.decay         = row.decay,
            m.status        = row.status,
            m.attempt_count = row.attempt_count,
            m.model_version = row.model_version,
            m.synthetic     = true,
            m.updated_at    = timestamp()
        """
        chunk_size = 5000
        n_chunks = (len(neo4j_batch) + chunk_size - 1) // chunk_size
        logger.info(
            "Writing %d mastery rows to Neo4j in %d chunks of %d …",
            len(neo4j_batch),
            n_chunks,
            chunk_size,
        )
        try:
            with neo4j_driver.session(database=neo4j_database) as session:
                for i in range(0, len(neo4j_batch), chunk_size):
                    chunk = neo4j_batch[i : i + chunk_size]
                    session.run(cypher, rows=chunk)
                    logger.info("  … wrote chunk %d/%d", i // chunk_size + 1, n_chunks)
            # estimate written students from unique pg_ids
            students_written = len({r["pg_id"] for r in neo4j_batch})
            logger.info("Neo4j batch write complete — %d students", students_written)
        except Exception as exc:
            logger.warning("Neo4j batch write failed: %s", exc)

    # ── Aggregate metrics ─────────────────────────────────────────────────────
    if model_masteries:
        all_pred = np.concatenate([m.flatten() for m in model_masteries])
        avg_pred = float(np.mean(all_pred))
        std_pred = float(np.std(all_pred))
        logger.info("Predicted mastery — mean=%.4f  std=%.4f", avg_pred, std_pred)

    if gt_masteries:
        rmse_vals = [
            float(np.sqrt(np.mean((pred - gt_) ** 2))) for pred, gt_ in gt_masteries
        ]
        corr_vals = [
            float(np.corrcoef(pred, gt_)[0, 1]) if len(pred) > 1 else 0.0
            for pred, gt_ in gt_masteries
        ]
        logger.info(
            "vs ground truth — RMSE mean=%.4f  Pearson-r mean=%.4f",
            np.mean(rmse_vals),
            np.nanmean(corr_vals),
        )

    if neo4j_driver:
        neo4j_driver.close()
        logger.info(
            "Neo4j writes: %d / %d students", students_written, len(student_indices)
        )

    # ── Dashboard smoke tests ─────────────────────────────────────────────────
    logger.info("\n── Dashboard API smoke tests ──")
    logger.info("API base URL: %s", args.api_url)
    logger.info("(Requires running backend.  Skipping auto-auth; check manually.)")

    # Print a small summary table
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║            PHASE 4  —  MASTERY RECOMPUTE SUMMARY           ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(
        f"║  Students processed    : {len(student_indices):>6}                          ║"
    )
    print(
        f"║  Students written (KG) : {students_written:>6}                          ║"
    )
    if model_masteries:
        print(f"║  Avg predicted mastery : {avg_pred:>6.4f}                          ║")
        print(f"║  Std predicted mastery : {std_pred:>6.4f}                          ║")
    if gt_masteries:
        print(
            f"║  RMSE vs IRT ground-t  : {np.mean(rmse_vals):>6.4f}                          ║"
        )
        print(
            f"║  Pearson-r vs IRT GT   : {np.nanmean(corr_vals):>6.4f}                          ║"
        )
    print(
        f"║  Best-model val AUC    : {ckpt['best_val_auc']:>6.4f}                          ║"
    )
    print(f"║  Inference time        : {elapsed:>6.1f}s                          ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Dashboard endpoints to validate manually:                  ║")
    print("║    GET  /api/cognitive-diagnosis/mastery/{uid}              ║")
    print("║    GET  /api/cognitive-diagnosis/path/{uid}/{cid}           ║")
    print("║    GET  /api/cognitive-diagnosis/arcd-portfolio/{uid}/{cid} ║")
    print("║    GET  /api/cognitive-diagnosis/arcd-twin/{uid}/{cid}      ║")
    print("╚══════════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
