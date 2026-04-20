"""synthgen.config — runtime configuration loaded from environment."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_HERE = Path(__file__).resolve()
_ENV = _HERE.parent.parent.parent / ".env"
if _ENV.exists():
    load_dotenv(_ENV, override=False)


@dataclass
class SynthGenConfig:
    # ── Database connections ───────────────────────────────────────────────
    neo4j_uri: str = field(
        default_factory=lambda: os.environ["LAB_TUTOR_NEO4J_URI"]
    )
    neo4j_user: str = field(
        default_factory=lambda: os.getenv("LAB_TUTOR_NEO4J_USERNAME", "neo4j")
    )
    neo4j_password: str = field(
        default_factory=lambda: os.environ["LAB_TUTOR_NEO4J_PASSWORD"]
    )
    neo4j_database: str = field(
        default_factory=lambda: os.getenv("LAB_TUTOR_NEO4J_DATABASE", "neo4j")
    )
    postgres_url: str = field(
        default_factory=lambda: os.environ["LAB_TUTOR_DATABASE_URL"]
    )

    # ── Run identity ───────────────────────────────────────────────────────
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # ── Population parameters ──────────────────────────────────────────────
    n_students: int = 1000
    target_interactions: int = 500_000

    # ── IRT 2PL parameters ────────────────────────────────────────────────
    theta_mu: float = 0.6       # student ability mean (tuned for class balance)
    theta_std: float = 1.2      # student ability std (tuned for class balance)
    pareto_alpha: float = 1.5   # sequence-length Pareto shape
    sim_days: int = 120         # simulation window in days

    # ── Question bank ─────────────────────────────────────────────────────
    questions_per_skill: int = 8

    # ── Per-student skill selection ────────────────────────────────────────
    # Each student is randomly assigned a personal subset of skills that
    # they practise.  Any skill outside this subset receives no interactions.
    min_student_skills: int = 15
    max_student_skills: int = 25

    # ── Resource engagement (video / reading opens) ────────────────────────
    # Base probability that a student opens a video / reading linked to one of
    # their selected skills.  Each student also draws a personal engagement
    # multiplier from Beta(2, 5), so actual probabilities vary across students.
    video_open_prob: float = 0.35
    reading_open_prob: float = 0.25
    # Maximum number of times a student can open the same resource.
    max_opens_per_resource: int = 4

    # ── Train/test split ──────────────────────────────────────────────────
    train_ratio: float = 0.8

    # ── Seed ──────────────────────────────────────────────────────────────
    random_seed: int = 42

    # ── Output directory ──────────────────────────────────────────────────
    out_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent
        / "data"
        / "synthgen"
    )

    # ── Teacher username (looked up in Postgres) ──────────────────────────
    teacher_username: str = "Roma"

    # ── Neo4j write batch size ────────────────────────────────────────────
    batch_size: int = 500


def default_config(**overrides) -> SynthGenConfig:
    cfg = SynthGenConfig()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg
