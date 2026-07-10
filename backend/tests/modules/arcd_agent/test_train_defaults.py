"""Lock the ICCSE2026-corrected hyperparameter defaults in arcd_train.py.

The original baseline run (``roma_synth_v6_2048``) suffered from threshold
collapse — Recall 0.991, Specificity 0.031, MCC 0.082 — driven by
focal_alpha=0.25 in a ~79% positive-class corpus, mastery_weight=0.2 over a
~5%-coverage target, and aggressive label-smoothing/r-drop. The post-fix
defaults (committed alongside this test) are the same ones used by the
ICCSE2026 paper's gcnfix2 screening campaign.

Re-introducing any of the old defaults silently regresses the model to the
collapsed baseline; this test is the canary.
"""

from __future__ import annotations

import re
from pathlib import Path


def _argparse_default(arg_flag: str) -> tuple[str, str]:
    src = Path(__file__).resolve().parents[3] / "arcd_train.py"
    text = src.read_text()
    pattern = re.compile(
        r'parser\.add_argument\(\s*"'
        + re.escape(arg_flag)
        + r'"[^)]*?default=([^,)]+)',
        re.DOTALL,
    )
    m = pattern.search(text)
    assert m, f"argparse flag {arg_flag} not found in arcd_train.py"
    return arg_flag, m.group(1).strip()


def test_focal_alpha_default_is_paper_aligned() -> None:
    _, value = _argparse_default("--focal-alpha")
    assert value == "0.65", (
        f"--focal-alpha default must be 0.65 (paper-aligned post-fix), got {value}. "
        "0.25 is the pre-fix value that produced threshold collapse."
    )


def test_mastery_weight_default_is_paper_aligned() -> None:
    _, value = _argparse_default("--mastery-weight")
    assert value == "0.1", (
        f"--mastery-weight default must be 0.1, got {value}. "
        "Higher values dominate the focal correctness objective on sparse mastery targets."
    )


def test_rdrop_alpha_default_is_paper_aligned() -> None:
    _, value = _argparse_default("--rdrop-alpha")
    assert value == "0.1", (
        f"--rdrop-alpha default must be 0.1, got {value}. "
        "0.3 in the baseline run conflicted with focal calibration."
    )


def test_label_smoothing_default_is_paper_aligned() -> None:
    _, value = _argparse_default("--label-smoothing")
    assert value == "0.05", (
        f"--label-smoothing default must be 0.05, got {value}. "
        "0.1 in the baseline run pushed logits toward uniform."
    )


def test_d_and_d_skill_defaults_match_kg_dimension() -> None:
    """Both ``--d`` and ``--d-skill`` must default to 2048 (KG-native)."""
    _, d_value = _argparse_default("--d")
    _, d_skill_value = _argparse_default("--d-skill")
    assert d_value == "2048", (
        f"--d default must be 2048 (KG embedding dim), got {d_value}"
    )
    assert d_skill_value == "2048", (
        f"--d-skill default must be 2048 (KG embedding dim), got {d_skill_value}"
    )
