"""ARCD Model Registry — loads a trained checkpoint for inference.

The registry wraps a trained ARCDModel checkpoint (produced by arcd_train.py)
and exposes a single :py:meth:`predict_mastery` helper that takes a list of
recent interactions and a concept name list and returns predicted mastery
scores.

Usage
-----
    from arcd_agent.model_registry import ModelRegistry

    registry = ModelRegistry.from_dir(Path("checkpoints/roma_synth_v6_2048"))
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
        # The reserved <UNK_STUDENT> slot.  Set by _load() from the v4
        # checkpoint config; defaults to 0 (effectively "no UNK") when the
        # registry has not been loaded yet.
        self._unk_student_idx: int = 0
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
        # v4 checkpoints reserve the LAST student row as the <UNK_STUDENT>
        # slot.  Older v3 checkpoints have no such slot — fall back to
        # n_students - 1 (still safe; just means UNK == last real student).
        self._unk_student_idx = cfg.get("unk_student_idx", n_students - 1)

        model = ARCDModel(
            d_skill_embed=cfg.get("d_skill_embed", 2048),
            d=cfg.get("d", 2048),
            n_gat_layers=cfg.get("n_gat_layers", cfg.get("n_gcn_layers", 2)),
            n_questions=n_questions,
            n_videos=cfg.get("n_videos", 1),
            n_readings=cfg.get("n_readings", 1),
            n_students=n_students,
            n_skills=n_skills,
            n_heads_gat=cfg.get("n_heads_gat", 2),
            d_type=cfg.get("d_type", 16),
            n_heads=cfg.get("n_heads", 2),
            d_ff=cfg.get("d_ff", cfg.get("d", 2048) * 4),
            n_attn_layers=cfg.get("n_attn_layers", 2),
            dropout=0.0,
            use_gat=cfg.get("use_gat", True),
            student_emb_drop_p=0.0,  # disabled at inference time
            unk_student_idx=self._unk_student_idx,
        )
        state_key = "model_state_dict" if "model_state_dict" in ckpt else "state_dict"
        # Extract rel_decay weights before load_state_dict.  The module is installed
        # lazily via set_prerequisite_graph() (needs A_pre from graph tensors), so
        # its keys must be stripped from the state dict to allow strict loading.
        # For old checkpoints (pre-RelationalDecay) there are no rel_decay keys.
        raw_state = ckpt[state_key]
        rel_decay_state = {
            k: v for k, v in raw_state.items() if k.startswith("rel_decay.")
        }
        clean_state = {
            k: v for k, v in raw_state.items() if not k.startswith("rel_decay.")
        }
        model.load_state_dict(clean_state)
        model.eval()
        self._model = model

        # H_skill_raw: restore from checkpoint (saved by arcd_train.py).
        # This avoids re-randomisation at inference time and ensures the GAT
        # starts from the same 2048-dim name_embedding that was used at training.
        H_skill_raw = ckpt.get("H_skill_raw")
        if H_skill_raw is None:
            raise KeyError(
                "Checkpoint does not contain 'H_skill_raw'. "
                "Re-train with the updated arcd_train.py which persists H_skill_raw, "
                "or run arcd_train.py --neo4j-uri ... to generate a new checkpoint."
            )

        # Build minimal graph tensors (identity A_pre, question-skill from vocab)
        self._graph_data = self._build_graph_tensors(vocab_path, H_skill_raw)

        # Install RelationalDecay from the real prerequisite graph now that A_pre
        # is available.  Restore the trained w_p_logit if the checkpoint had one.
        model.set_prerequisite_graph(self._graph_data["A_pre"])
        if "rel_decay.w_p_logit" in rel_decay_state:
            model.rel_decay.w_p_logit.data.copy_(rel_decay_state["rel_decay.w_p_logit"])  # type: ignore[union-attr]

        self.model_version = ckpt.get("model_version", "arcd_v2_model")
        self.best_val_auc = float(ckpt.get("best_val_auc", 0.0))
        self._model_config = cfg

        # Load calibration temperature from metrics_report.json if present.
        # Temperature T = Calib_Slope from logistic calibration regression.
        # sigmoid(logit / T) produces well-spread probabilities at inference time.
        self._calibration_temperature: float = 1.0  # default: no scaling
        metrics_path = ckpt_path.parent / "metrics_report.json"
        if metrics_path.exists():
            try:
                with open(metrics_path) as _mf:
                    _metrics = json.load(_mf)
                slope = float(_metrics.get("Calib Slope", 1.0))
                if slope > 1.2:  # only apply if model is meaningfully uncalibrated
                    self._calibration_temperature = slope
                    logger.info(
                        "ModelRegistry: temperature scaling T=%.3f loaded from metrics_report.json",
                        self._calibration_temperature,
                    )
            except Exception as _e:
                logger.debug(
                    "ModelRegistry: could not load calibration temperature: %s", _e
                )

        self.is_available = True
        logger.info(
            "ModelRegistry: loaded checkpoint — n_skills=%d  n_questions=%d  "
            "n_students=%d  val_AUC=%.4f  calib_T=%.3f",
            n_skills,
            n_questions,
            n_students,
            self.best_val_auc,
            self._calibration_temperature,
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

    def _build_graph_tensors(
        self, vocab_path: Path, H_skill_raw: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        """Build graph tensors from vocab, parquet files, and the checkpoint's H_skill_raw.

        Reads skill_videos.parquet, skill_readings.parquet, and prereq_edges.parquet
        from the same directory as vocab.json when available, matching what arcd_train.py
        uses during training.  Falls back to identity / zeros when files are absent.

        H_skill_raw is restored directly from the checkpoint (set by arcd_train.py
        from Neo4j name_embedding). No Xavier init fallback — checkpoints that
        pre-date this change must be retrained.
        """
        import pandas as pd

        data_dir = vocab_path.parent
        vocab = self._vocab
        n_skills = len(vocab.get("concept", {}))
        n_questions = len(vocab.get("question", {}))
        n_videos = max(len(vocab.get("video", {})), 1)
        n_readings = max(len(vocab.get("reading", {})), 1)
        n_students = len(vocab.get("user", {}))
        concept_idx: dict[str, int] = vocab.get("concept", {})

        # A_pre: prerequisite adjacency (row-normalised)
        prereq_path = data_dir / "prereq_edges.parquet"
        if prereq_path.exists():
            df_pre = pd.read_parquet(prereq_path)
            A_pre_raw = torch.zeros(n_skills, n_skills)
            for _, row in df_pre.iterrows():
                si, di = int(row["src_skill_idx"]), int(row["dst_skill_idx"])
                if 0 <= si < n_skills and 0 <= di < n_skills:
                    A_pre_raw[di, si] = 1.0  # si is prereq of di
            row_sum = A_pre_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
            A_pre = A_pre_raw / row_sum
        else:
            A_pre = torch.eye(n_skills)

        # A_qs: question-skill adjacency
        # Primary: use vocab["question_skill"] name->name mapping (written by arcd_train
        # for new checkpoints).  Fallback: read directly from train/test parquet files
        # using integer indices — handles older checkpoints where question_skill was not
        # written into vocab.json.
        A_qs_raw = torch.zeros(n_questions, n_skills)
        qs_map: dict = vocab.get("question_skill", {})
        if qs_map:
            for q_name, skill_name in qs_map.items():
                qi = vocab["question"].get(q_name)
                si = concept_idx.get(skill_name)
                if qi is not None and si is not None:
                    A_qs_raw[qi, si] = 1.0
        else:
            # Fallback: build from train.parquet + test.parquet integer indices
            for fname in ("train.parquet", "test.parquet"):
                fp = data_dir / fname
                if not fp.exists():
                    continue
                df_all = pd.read_parquet(fp)
                if "event_type" in df_all.columns and "entity_idx" in df_all.columns:
                    df_qs = df_all[df_all["event_type"] == 0][
                        ["entity_idx", "skill_idx"]
                    ].drop_duplicates()
                    pairs = df_qs.values.tolist()
                else:
                    df_qs = df_all[["question_idx", "skill_idx"]].drop_duplicates()
                    pairs = df_qs.values.tolist()
                for qi, si in pairs:
                    qi, si = int(qi), int(si)
                    if 0 <= qi < n_questions and 0 <= si < n_skills:
                        A_qs_raw[qi, si] = 1.0
        row_sum = A_qs_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
        A_qs = A_qs_raw / row_sum

        # A_vs: video-skill adjacency — integer index columns (video_idx, skill_idx)
        vs_path = data_dir / "skill_videos.parquet"
        if vs_path.exists():
            df_vs = pd.read_parquet(vs_path)
            A_vs_raw = torch.zeros(n_videos, n_skills)
            for _, row in df_vs.iterrows():
                vi, si = int(row["video_idx"]), int(row["skill_idx"])
                if 0 <= vi < n_videos and 0 <= si < n_skills:
                    A_vs_raw[vi, si] = 1.0
            row_sum = A_vs_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
            A_vs = A_vs_raw / row_sum
        else:
            A_vs = torch.zeros(1, n_skills)

        # A_rs: reading-skill adjacency — integer index columns (reading_idx, skill_idx)
        rs_path = data_dir / "skill_readings.parquet"
        if rs_path.exists():
            df_rs = pd.read_parquet(rs_path)
            A_rs_raw = torch.zeros(n_readings, n_skills)
            for _, row in df_rs.iterrows():
                ri, si = int(row["reading_idx"]), int(row["skill_idx"])
                if 0 <= ri < n_readings and 0 <= si < n_skills:
                    A_rs_raw[ri, si] = 1.0
            row_sum = A_rs_raw.sum(dim=1, keepdim=True).clamp(min=1.0)
            A_rs = A_rs_raw / row_sum
        else:
            A_rs = torch.zeros(1, n_skills)

        A_uq = torch.zeros(n_students, n_questions)

        return {
            "H_skill_raw": H_skill_raw.float(),
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

        # OOV students at inference are routed through the reserved UNK slot
        # (v3 had a contamination bug that used real student 0's embedding).
        batch = {
            "student_ids": torch.full((N,), self._unk_student_idx, dtype=torch.long),
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

        # Apply temperature scaling calibration when T > 1 (uncalibrated checkpoint).
        # sigmoid(logit / T) spreads probabilities so threshold=0.5 discriminates properly.
        T = self._calibration_temperature
        if T != 1.0:
            p_correct = torch.sigmoid(out["response_logit"] / T).numpy()
        else:
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

        # OOV student → route to the reserved UNK slot rather than hijacking
        # real student 0's trained embedding (the v3 contamination bug).
        batch = {
            "student_ids": torch.tensor([self._unk_student_idx], dtype=torch.long),
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
        ``backend/checkpoints/roma_synth_v6_2048`` relative to this file's
        package root — trained with corrected focal-alpha=0.25, masked
        MasteryLoss, and the reserved UNK student slot.
    """
    global _registry
    if _registry is None:
        if checkpoint_dir is None:
            _pkg_root = Path(__file__).resolve().parent.parent
            checkpoint_dir = _pkg_root / "checkpoints" / "roma_synth_v6_2048"
        _registry = ModelRegistry.from_dir(Path(checkpoint_dir))
    return _registry
