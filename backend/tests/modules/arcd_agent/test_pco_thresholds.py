"""Lock the PCODetector defaults to the ICCSE2026 paper-aligned values.

The Learning Fellow's PCO threshold (`tau_m`) was inconsistent across the
codebase before the ICCSE2026 integration:

* `learnfell.PCODetector.__init__` default: ``tau_m=0.50`` — paper-aligned.
* `cognitive_diagnosis/service.py` instantiation: ``tau_m=0.50`` — aligned.
* `agents/orchestrator.py` `_build_review_node`: ``tau_m=0.60`` — drifted.

The drift was fixed in the same commit as this test. The κ=0.902 calibration
result reported in the ICCSE2026 paper (and mirrored in
``backend/checkpoints/iccse2026_paper_results.json``) was measured at
``phi=3, tau_m=0.50, theta_decay=0.60`` — changing any of these silently
invalidates the calibration.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.modules.arcd_agent.agents.learnfell import PCODetector


def test_pco_detector_default_thresholds_match_paper() -> None:
    det = PCODetector()
    assert det.phi == 3
    assert det.tau_m == 0.50
    assert det.theta_decay == 0.60


def test_orchestrator_review_node_uses_paper_aligned_thresholds() -> None:
    """The orchestrator must instantiate PCODetector with paper-aligned thresholds.

    We grep the source rather than instantiate the orchestrator (which depends
    on full LangGraph state). The value is too small to be worth a heavyweight
    integration fixture but too important to leave unchecked — silent drift is
    exactly what introduced the bug we just fixed.
    """
    src = Path(__file__).resolve().parents[3] / (
        "app/modules/arcd_agent/agents/orchestrator.py"
    )
    text = src.read_text()
    matches = re.findall(r"PCODetector\(([^)]*)\)", text)
    assert matches, "Orchestrator must instantiate at least one PCODetector"

    for args in matches:
        assert "tau_m=0.50" in args.replace(" ", ""), (
            f"Orchestrator PCODetector must use tau_m=0.50 (paper-aligned), "
            f"got args: {args!r}"
        )
