"""synthgen.student_generator — IRT 2PL student population generator."""
from __future__ import annotations

import logging
import uuid

import numpy as np

from .config import SynthGenConfig

logger = logging.getLogger(__name__)


def generate_students(cfg: SynthGenConfig) -> list[dict]:
    """Generate N synthetic students with IRT ability θ ~ N(μ, σ).

    Each student dict:
        student_id   : str   unique raw id  (e.g. "synth_0000_<run>")
        email        : str   unique email for Postgres
        theta        : float IRT ability
        seq_len      : int   target interaction count (Pareto-sampled)
    """
    rng = np.random.default_rng(cfg.random_seed)

    thetas = rng.normal(cfg.theta_mu, cfg.theta_std, size=cfg.n_students)
    thetas = np.clip(thetas, -2.0, 4.0)

    # Pareto-distributed sequence lengths (min 20, max 2000)
    raw_lengths = (rng.pareto(cfg.pareto_alpha, size=cfg.n_students) + 1) * 80
    seq_lens = np.clip(raw_lengths.astype(int), 20, 2_000)

    students = []
    for i in range(cfg.n_students):
        sid = f"synth_{i:04d}_{cfg.run_id}"
        students.append(
            {
                "student_id": sid,
                "email": f"synth_{i}_{cfg.run_id}@labtutor.local",
                "first_name": f"Synth{i:04d}",
                "last_name": "Student",
                "theta": round(float(thetas[i]), 4),
                "seq_len": int(seq_lens[i]),
            }
        )

    theta_arr = np.array([s["theta"] for s in students])
    logger.info(
        "Generated %d students: θ μ=%.3f σ=%.3f range=[%.2f, %.2f]",
        cfg.n_students,
        float(theta_arr.mean()),
        float(theta_arr.std()),
        float(theta_arr.min()),
        float(theta_arr.max()),
    )
    return students
