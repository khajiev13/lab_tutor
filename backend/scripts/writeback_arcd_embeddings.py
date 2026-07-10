#!/usr/bin/env python3
"""Write the 5-stage GAT outputs from a trained ARCD checkpoint back to Neo4j.

Per CLAUDE.md "Required changes" section, after every successful retrain we
must persist the contextual embeddings into Neo4j as new properties so the
production agents (Learning Fellow, Learning Path Generator, Adaptive
Exercise) can read them at inference time.

| GAT stage | Output  | Neo4j label                                | Property         |
|-----------|---------|--------------------------------------------|------------------|
| Stage 1   | h_s     | :SKILL / :BOOK_SKILL / :MARKET_SKILL       | arcd_h_skill     |
| Stage 2   | h_qa    | :QUESTION                                  | arcd_h_question  |
| Stage 3   | h_v     | :VIDEO_RESOURCE                            | arcd_h_video     |
| Stage 4   | h_r     | :READING_RESOURCE                          | arcd_h_reading   |
| Stage 5   | h_u     | :USER / :STUDENT (real synth students only)| arcd_h_student   |

Usage
-----
    cd backend
    uv run python scripts/writeback_arcd_embeddings.py \\
        --checkpoint-dir checkpoints/roma_synth_v6_iccse_smoke \\
        [--dry-run]                  # preview counts without writing
        [--skills-only]              # writeback only h_s (paper minimum)

Idempotency
-----------
Each stage uses a single ``MATCH ... SET`` per node, so re-running the script
overwrites whatever was previously written. Nothing else is touched.

Dry-run mode
------------
``--dry-run`` runs the entire pipeline (load checkpoint, run forward pass)
but skips the Neo4j writes. The script reports counts and matched samples.
This is the recommended way to verify a checkpoint before promoting it.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import torch

logger = logging.getLogger("writeback_arcd_embeddings")

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.modules.arcd_agent.model_registry import ModelRegistry  # noqa: E402


def _connect():
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise SystemExit(
            "neo4j package missing. Run: cd backend && uv add neo4j"
        ) from exc

    uri = os.environ.get("LAB_TUTOR_NEO4J_URI", "")
    user = os.environ.get("LAB_TUTOR_NEO4J_USERNAME", "")
    pwd = os.environ.get("LAB_TUTOR_NEO4J_PASSWORD", "")
    db = os.environ.get("LAB_TUTOR_NEO4J_DATABASE", "neo4j")

    if not (uri and user and pwd):
        raise SystemExit(
            "Neo4j credentials missing. Set LAB_TUTOR_NEO4J_URI / "
            "LAB_TUTOR_NEO4J_USERNAME / LAB_TUTOR_NEO4J_PASSWORD."
        )

    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    return driver, db


def _embeddings_from_checkpoint(checkpoint_dir: Path) -> dict[str, torch.Tensor]:
    """Load the checkpoint and return all 5 GAT stage outputs (CPU float32)."""
    reg = ModelRegistry.from_dir(checkpoint_dir)
    if not reg.is_available:
        raise RuntimeError(
            f"Checkpoint at {checkpoint_dir} did not load (registry.is_available=False). "
            "Check the smoke log and state-dict compatibility."
        )

    model = reg._model
    gd = reg._graph_data

    with torch.no_grad():
        out = model.gat(
            gd["H_skill_raw"],
            gd["A_pre"],
            gd["A_qs"],
            gd["A_vs"],
            gd["A_rs"],
            gd["A_uq"],
        )
    return {k: v.detach().cpu().float() for k, v in out.items()}, reg._vocab


def _write_skill_embeddings(
    session, vocab: dict, h_s: torch.Tensor, dry_run: bool
) -> int:
    concept_idx: dict[str, int] = vocab.get("concept", {})
    n = 0
    for skill_name, idx in concept_idx.items():
        emb = h_s[idx].tolist()
        if dry_run:
            n += 1
            continue
        result = session.run(
            """
            MATCH (s) WHERE (s:SKILL OR s:BOOK_SKILL OR s:MARKET_SKILL)
              AND s.name = $name
            SET s.arcd_h_skill = $emb
            RETURN count(s) AS c
            """,
            name=skill_name,
            emb=emb,
        ).single()
        n += int(result["c"]) if result else 0
    return n


def _write_question_embeddings(
    session, vocab: dict, h_qa: torch.Tensor, dry_run: bool
) -> int:
    q_idx: dict[str, int] = vocab.get("question", {})
    n = 0
    for q_id, idx in q_idx.items():
        emb = h_qa[idx].tolist()
        if dry_run:
            n += 1
            continue
        result = session.run(
            "MATCH (q:QUESTION {id: $id}) SET q.arcd_h_question = $emb RETURN count(q) AS c",
            id=q_id,
            emb=emb,
        ).single()
        n += int(result["c"]) if result else 0
    return n


def _write_video_embeddings(
    session, vocab: dict, h_v: torch.Tensor, dry_run: bool
) -> int:
    v_idx: dict[str, int] = vocab.get("video", {})
    n = 0
    for v_id, idx in v_idx.items():
        emb = h_v[idx].tolist()
        if dry_run:
            n += 1
            continue
        result = session.run(
            "MATCH (v:VIDEO_RESOURCE) WHERE coalesce(v.id, v.url) = $id "
            "SET v.arcd_h_video = $emb RETURN count(v) AS c",
            id=v_id,
            emb=emb,
        ).single()
        n += int(result["c"]) if result else 0
    return n


def _write_reading_embeddings(
    session, vocab: dict, h_r: torch.Tensor, dry_run: bool
) -> int:
    r_idx: dict[str, int] = vocab.get("reading", {})
    n = 0
    for r_id, idx in r_idx.items():
        emb = h_r[idx].tolist()
        if dry_run:
            n += 1
            continue
        result = session.run(
            "MATCH (r:READING_RESOURCE) WHERE coalesce(r.id, r.url) = $id "
            "SET r.arcd_h_reading = $emb RETURN count(r) AS c",
            id=r_id,
            emb=emb,
        ).single()
        n += int(result["c"]) if result else 0
    return n


def _write_student_embeddings(
    session, vocab: dict, h_u: torch.Tensor, dry_run: bool
) -> int:
    """Skip the reserved <UNK_STUDENT> slot at index n_real_students."""
    u_idx: dict[str, int] = vocab.get("user", {})
    n_real_students = len(u_idx)
    n = 0
    for u_id, idx in u_idx.items():
        if idx >= n_real_students:
            continue
        emb = h_u[idx].tolist()
        if dry_run:
            n += 1
            continue
        try:
            sid = int(u_id)
        except (TypeError, ValueError):
            sid = u_id
        result = session.run(
            "MATCH (u) WHERE (u:USER OR u:STUDENT) AND coalesce(u.id, '') = $id "
            "SET u.arcd_h_student = $emb RETURN count(u) AS c",
            id=sid,
            emb=emb,
        ).single()
        n += int(result["c"]) if result else 0
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--checkpoint-dir",
        type=Path,
        required=True,
        help="ARCD checkpoint directory (must contain best_model.pt, vocab.json)",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Compute only; do not write to Neo4j"
    )
    p.add_argument(
        "--skills-only",
        action="store_true",
        help="Only write h_s to :SKILL nodes (paper minimum)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    if not args.checkpoint_dir.exists():
        logger.error("Checkpoint dir not found: %s", args.checkpoint_dir)
        return 1

    logger.info("Loading checkpoint from %s …", args.checkpoint_dir)
    embeddings, vocab = _embeddings_from_checkpoint(args.checkpoint_dir)
    logger.info(
        "GAT outputs — h_s=%s  h_qa=%s  h_v=%s  h_r=%s  h_u=%s",
        tuple(embeddings["h_s"].shape),
        tuple(embeddings["h_qa"].shape),
        tuple(embeddings["h_v"].shape),
        tuple(embeddings["h_r"].shape),
        tuple(embeddings["h_u"].shape),
    )

    if args.dry_run:
        driver, db = None, None
        session_ctx = _NullSession()
        logger.info("Dry-run mode — Neo4j writes skipped.")
    else:
        driver, db = _connect()
        session_ctx = driver.session(database=db)

    with session_ctx as session:
        n_s = _write_skill_embeddings(session, vocab, embeddings["h_s"], args.dry_run)
        logger.info(
            "Stage 1 (h_skill):   %d skill nodes %supdated",
            n_s,
            "would-be " if args.dry_run else "",
        )

        if not args.skills_only:
            n_q = _write_question_embeddings(
                session, vocab, embeddings["h_qa"], args.dry_run
            )
            logger.info(
                "Stage 2 (h_question): %d question nodes %supdated",
                n_q,
                "would-be " if args.dry_run else "",
            )

            n_v = _write_video_embeddings(
                session, vocab, embeddings["h_v"], args.dry_run
            )
            logger.info(
                "Stage 3 (h_video):    %d video nodes %supdated",
                n_v,
                "would-be " if args.dry_run else "",
            )

            n_r = _write_reading_embeddings(
                session, vocab, embeddings["h_r"], args.dry_run
            )
            logger.info(
                "Stage 4 (h_reading):  %d reading nodes %supdated",
                n_r,
                "would-be " if args.dry_run else "",
            )

            n_u = _write_student_embeddings(
                session, vocab, embeddings["h_u"], args.dry_run
            )
            logger.info(
                "Stage 5 (h_student):  %d student nodes %supdated",
                n_u,
                "would-be " if args.dry_run else "",
            )

    if driver is not None:
        driver.close()
    return 0


class _NullSession:
    """No-op session used only in dry-run mode."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, *args, **kwargs):  # pragma: no cover - never called
        raise RuntimeError("Dry-run path attempted to run a Cypher query")


if __name__ == "__main__":
    raise SystemExit(main())
