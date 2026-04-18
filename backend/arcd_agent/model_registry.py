"""ARCD Model Registry — loads a trained checkpoint for inference.

The registry wraps a trained ARCDModel checkpoint (produced by arcd_train.py)
and exposes a single :py:meth:`predict_mastery` helper that takes a list of
recent interactions and a concept name list and returns predicted mastery
scores.

Usage
-----
    from arcd_agent.model_registry import ModelRegistry

    registry = ModelRegistry.from_dir(Path("checkpoints/roma_synth_v1_reg"))
    if registry.is_available:
        mastery = registry.predict_mastery(interactions, concept_names)

Fallback
--------
If the checkpoint directory is missing, the model file is absent, or
anything goes wrong during loading, ``is_available`` is ``False`` and
:py:meth:`predict_mastery` raises ``RuntimeError``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Thread-safe (read-only) wrapper around a trained ARCD checkpoint.

    Attributes
    ----------
    is_available : bool
        True when a valid checkpoint was found and loaded successfully.
    model_version : str
        The version tag stored in the checkpoint, or "unknown".
    best_val_auc : float
        Validation AUC reported at training time, or 0.0.
    """

    def __init__(self) -> None:
        self._model: Any = None  # ARCDModel
        self._vocab: dict = {}
        self._config: dict = {}
        self._graph_data: dict = {}
        self.is_available: bool = False
        self.model_version: str = "unknown"
        self.best_val_auc: float = 0.0

    # ── Construction ──────────────────────────────────────────────────────────

    @classmethod
    def from_dir(cls, checkpoint_dir: Path | str) -> ModelRegistry:
        """Load from the arcd_train output directory.

        Expected files
        --------------
        <checkpoint_dir>/best_model.pt  — state_dict + config dict
        <checkpoint_dir>/../vocab.json  — synthgen vocab (same run)
          or
        <vocab_dir>/vocab.json          — explicitly passed via env var
        """
        reg = cls()
        checkpoint_dir = Path(checkpoint_dir)
        ckpt_path = checkpoint_dir / "best_model.pt"

        if not ckpt_path.exists():
            logger.info(
                "ModelRegistry: checkpoint not found at %s — using heuristic fallback",
                ckpt_path,
            )
            return reg

        try:
            reg._load(ckpt_path)
        except Exception as exc:
            logger.warning(
                "ModelRegistry: failed to load checkpoint (%s) — fallback", exc
            )

        return reg

    def _load(self, ckpt_path: Path) -> None:
        from arcd_agent.model.training import ARCDModel

        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        # Support both key naming conventions (old: config/state_dict, new: model_config/model_state_dict)
        cfg = ckpt.get("model_config", ckpt.get("config", {}))
        self._config = cfg

        # Vocab path: try checkpoint dir first (extended vocab with question_skill),
        # then fall back to the original path stored in the checkpoint, then search.
        vocab_path = self._find_vocab(ckpt_path) or (
            Path(ckpt.get("vocab_path", ""))
            if ckpt.get("vocab_path") and Path(ckpt["vocab_path"]).exists()
            else None
        )
        if vocab_path is None:
            raise FileNotFoundError(
                "vocab.json not found adjacent to checkpoint — cannot build graph tensors"
            )
        with open(vocab_path) as f:
            self._vocab = json.load(f)

        n_skills = cfg.get("n_skills", len(self._vocab.get("concept", {})))
        n_questions = cfg.get("n_questions", len(self._vocab.get("question", {})))
        n_students = cfg.get("n_students", len(self._vocab.get("user", {})))

        model = ARCDModel(
            d_skill_embed=cfg.get("d_skill_embed", 32),
            d=cfg.get("d", 64),
            n_gat_layers=cfg.get("n_gat_layers", cfg.get("n_gcn_layers", 2)),
            n_questions=n_questions,
            n_videos=cfg.get("n_videos", 1),
            n_readings=cfg.get("n_readings", 1),
            n_students=n_students,
            n_skills=n_skills,
            n_heads_gat=cfg.get("n_heads_gat", 2),
            d_type=cfg.get("d_type", 16),
            n_heads=cfg.get("n_heads", 2),
            d_ff=cfg.get("d_ff", cfg.get("d", 64) * 4),
            n_attn_layers=cfg.get("n_attn_layers", 2),
            dropout=0.0,
            use_gat=cfg.get("use_gat", True),
            student_emb_drop_p=0.0,  # disabled at inference time
        )
        state_key = "model_state_dict" if "model_state_dict" in ckpt else "state_dict"
        model.load_state_dict(ckpt[state_key])
        model.eval()
        self._model = model

        # Build minimal graph tensors (identity A_pre, question-skill from vocab)
        self._graph_data = self._build_graph_tensors(vocab_path)

        self.model_version = ckpt.get("model_version", "arcd_v2_model")
        self.best_val_auc = float(ckpt.get("best_val_auc", 0.0))
        self.is_available = True
        logger.info(
            "ModelRegistry: loaded checkpoint — n_skills=%d  n_questions=%d  "
            "n_students=%d  val_AUC=%.4f",
            n_skills,
            n_questions,
            n_students,
            self.best_val_auc,
        )

    @staticmethod
    def _find_vocab(ckpt_path: Path) -> Path | None:
        """Search for vocab.json relative to the checkpoint path."""
        # 1. Same dir
        p = ckpt_path.parent / "vocab.json"
        if p.exists():
            return p
        # 2. Sibling synthgen data dirs (arcd_train uses --data-dir)
        for candidate in ckpt_path.parent.parent.rglob("vocab.json"):
            return candidate
        return None

    def _build_graph_tensors(self, vocab_path: Path) -> dict[str, torch.Tensor]:
        """Build minimal graph tensors from vocab alone.

        Used during inference where we don't have the full Parquet files.
        A_qs is built from the question→skill mapping stored in the vocab.
        A_uq is zeros (no student-question history available at inference time).
        """
        vocab = self._vocab
        n_skills = len(vocab.get("concept", {}))
        n_questions = len(vocab.get("question", {}))
        n_students = len(vocab.get("user", {}))

        H = torch.empty(n_skills, self._config.get("d_skill_embed", 32))
        nn.init.xavier_uniform_(H)

        A_pre = torch.eye(n_skills)

        # Rebuild A_qs from vocab — vocab stores question-id → question-idx mapping;
        # question_skill stored separately only if the vocab was extended.
        A_qs_raw = torch.zeros(n_questions, n_skills)
        qs_map: dict = vocab.get("question_skill", {})
        for q_name, skill_name in qs_map.items():
            qi = vocab["question"].get(q_name)
            si = vocab["concept"].get(skill_name)
            if qi is not None and si is not None:
                A_qs_raw[qi, si] = 1.0
        row_sum = A_qs_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
        A_qs = A_qs_raw / row_sum

        A_vs = torch.zeros(1, n_skills)
        A_rs = torch.zeros(1, n_skills)
        A_uq = torch.zeros(n_students, n_questions)

        return {
            "H_skill_raw": H,
            "A_pre": A_pre,
            "A_qs": A_qs,
            "A_vs": A_vs,
            "A_rs": A_rs,
            "A_uq": A_uq,
        }

    # ── Inference ─────────────────────────────────────────────────────────────

    @torch.no_grad()
    def predict_correctness(
        self,
        interactions: list[dict],
        target_questions: list[str],
        seq_len: int = 50,
    ) -> dict[str, float]:
        """Predict P(correct) for each target question given a student's history.

        Parameters
        ----------
        interactions:
            Same format as :py:meth:`predict_mastery` —
            ``[{question_name, correct, timestamp_sec}, ...]``
        target_questions:
            Question names to predict correctness for.  Unknown names map to 0.5.
        seq_len:
            Max context window (last N interactions used).

        Returns
        -------
        dict[question_name, float]  P(correct) in [0, 1].
        """
        if not self.is_available:
            raise RuntimeError("ModelRegistry: no checkpoint loaded")
        if not target_questions:
            return {}

        vocab = self._vocab
        q_to_idx: dict[str, int] = vocab.get("question", {})

        # Build the sequence tensors once.
        recent = interactions[-(seq_len - 1) :]
        hist = [
            (
                q_to_idx.get(r.get("question_name", ""), 0),
                int(r.get("correct", 0)),
                float(r.get("timestamp_sec", 0)),
            )
            for r in recent
            if r.get("question_name") in q_to_idx
        ]

        T = seq_len - 1
        pad_len = T - len(hist)
        event_types = [0] * len(hist) + [0] * pad_len
        entity_indices = [e[0] for e in hist] + [0] * pad_len
        outcomes = [float(e[1]) for e in hist] + [0.0] * pad_len
        timestamps = [e[2] for e in hist] + [0.0] * pad_len
        decay_values = [0.0] * T
        pad_mask = [True] * len(hist) + [False] * pad_len

        # Separate known vs unknown questions.
        known_names = [q for q in target_questions if q in q_to_idx]
        unknown_names = [q for q in target_questions if q not in q_to_idx]
        result: dict[str, float] = {q: 0.5 for q in unknown_names}

        if not known_names:
            return result

        N = len(known_names)
        gd = self._graph_data

        # Batch: repeat the same sequence N times, one target question per row.
        # GAT is called once via gat_cache to avoid redundant graph convolutions.
        gat_cache: dict[str, torch.Tensor] = self._model.gat(
            gd["H_skill_raw"],
            gd["A_pre"],
            gd["A_qs"],
            gd["A_vs"],
            gd["A_rs"],
            gd["A_uq"],
        )

        target_idxs = torch.tensor([q_to_idx[q] for q in known_names], dtype=torch.long)

        batch = {
            "student_ids": torch.zeros(N, dtype=torch.long),
            "event_types": torch.tensor([event_types], dtype=torch.long).expand(N, -1),
            "entity_indices": torch.tensor([entity_indices], dtype=torch.long).expand(
                N, -1
            ),
            "outcomes": torch.tensor([outcomes], dtype=torch.float32).expand(N, -1),
            "timestamps": torch.tensor([timestamps], dtype=torch.float32).expand(N, -1),
            "decay_values": torch.tensor([decay_values], dtype=torch.float32).expand(
                N, -1
            ),
            "pad_mask": torch.tensor([pad_mask], dtype=torch.bool).expand(N, -1),
            "target_type": torch.zeros(N, dtype=torch.long),
            "target_idx": target_idxs,
        }

        out = self._model(
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
            gat_cache=gat_cache,
        )

        p_correct = torch.sigmoid(out["response_logit"]).numpy()  # [N]
        for name, p in zip(known_names, p_correct, strict=False):
            result[name] = float(p)

        return result

    @torch.no_grad()
    def predict_mastery(
        self,
        interactions: list[dict],
        concept_names: list[str],
        seq_len: int = 50,
    ) -> dict[str, float]:
        """Predict skill mastery from a sequence of recent interactions.

        Parameters
        ----------
        interactions:
            Ordered list of dicts, each with keys:
                ``question_name`` (str)  — must match vocab
                ``correct``       (int)  — 0 or 1
                ``timestamp_sec`` (float | int)
        concept_names:
            Ordered list of concept/skill names to return mastery for.
        seq_len:
            Max context window (last N interactions used).

        Returns
        -------
        dict[concept_name, float]  mastery in [0, 1].
        """
        if not self.is_available:
            raise RuntimeError("ModelRegistry: no checkpoint loaded")

        vocab = self._vocab
        q_to_idx: dict[str, int] = vocab.get("question", {})
        c_to_idx: dict[str, int] = vocab.get("concept", {})

        # Build sequence tensor (right-padded, true events first)
        recent = interactions[-(seq_len - 1) :]
        hist = [
            (
                q_to_idx.get(r.get("question_name", ""), 0),
                int(r.get("correct", 0)),
                float(r.get("timestamp_sec", 0)),
            )
            for r in recent
            if r.get("question_name") in q_to_idx
        ]

        T = seq_len - 1
        pad_len = T - len(hist)

        # event_types: 0=question (all synthgen events are questions)
        event_types = [0] * len(hist) + [0] * pad_len
        entity_indices = [e[0] for e in hist] + [0] * pad_len
        outcomes = [float(e[1]) for e in hist] + [0.0] * pad_len
        timestamps = [e[2] for e in hist] + [0.0] * pad_len
        decay_values = [0.0] * T
        pad_mask = [True] * len(hist) + [False] * pad_len

        batch = {
            "student_ids": torch.tensor([0], dtype=torch.long),
            "event_types": torch.tensor([event_types], dtype=torch.long),
            "entity_indices": torch.tensor([entity_indices], dtype=torch.long),
            "outcomes": torch.tensor([outcomes], dtype=torch.float32),
            "timestamps": torch.tensor([timestamps], dtype=torch.float32),
            "decay_values": torch.tensor([decay_values], dtype=torch.float32),
            "pad_mask": torch.tensor([pad_mask], dtype=torch.bool),
            "target_type": torch.tensor([0], dtype=torch.long),
            "target_idx": torch.tensor([0], dtype=torch.long),
        }

        gd = self._graph_data
        out = self._model(
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

        mastery_vec: np.ndarray = out["mastery"][0].numpy()  # [n_skills]

        result: dict[str, float] = {}
        for name in concept_names:
            idx = c_to_idx.get(name)
            result[name] = float(mastery_vec[idx]) if idx is not None else 0.0
        return result


# ── Module-level singleton (lazy, loaded on first access) ─────────────────────

_registry: ModelRegistry | None = None


def get_registry(checkpoint_dir: Path | str | None = None) -> ModelRegistry:
    """Return the module-level registry, loading it on first call.

    Parameters
    ----------
    checkpoint_dir:
        Path to the arcd_train output directory.  Defaults to
        ``backend/checkpoints/roma_synth_v1_reg`` relative to this file's package root.
    """
    global _registry
    if _registry is None:
        if checkpoint_dir is None:
            # Default: look two levels up from this module to backend/
            _pkg_root = Path(__file__).resolve().parent.parent
            checkpoint_dir = _pkg_root / "checkpoints" / "roma_synth_v1_reg"
        _registry = ModelRegistry.from_dir(Path(checkpoint_dir))
    return _registry
