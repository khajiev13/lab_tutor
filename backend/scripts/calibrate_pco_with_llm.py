"""Calibrate LAB's Learning Fellow PCODetector against an external LLM judge.

Background
----------
This is the production-side mirror of `ARCD_AGENT/scripts/iccse2026_eval_lf_llm.py`
that produced the ICCSE2026 paper's Table III $\\kappa = 0.902$ result. It runs
the same 500-session synthetic-cohort evaluation against LAB's deployed
`PCODetector` thresholds (`phi=3`, `tau_m=0.50`, `theta_decay=0.60`) and asks
deepseek-v3.2 (via Silra) to independently judge each session, then reports:

  * LLM-judge precision / recall vs the same oracle labels (y_true).
  * Cohen's $\\kappa$ between LAB's rule-based PCODetector and the real-LLM judge.

The script is provided as a calibration / regression-test utility — useful when
adjusting `PCODetector` thresholds or porting the agent to a new agent runtime,
to confirm the new configuration still agrees with an independent observer at
the $\\kappa \\geq 0.85$ level that the published baseline established.

Output
------
    backend/runs/lf_llm_calibration/lf_llm_judge_results.json   — per-session records
    backend/runs/lf_llm_calibration/lf_llm_judge_summary.json   — aggregate + Cohen's $\\kappa$

Environment
-----------
Requires `LAB_TUTOR_LLM_API_KEY` (Silra deepseek-chat).  Falls back to
`OPENAI_API_KEY` / `OPENAI_BASE_URL` if those are set.

Usage
-----
    cd /Users/mohasani/LAB_ARCD_INTEGERATE/backend && source .venv/bin/activate
    export LAB_TUTOR_LLM_API_KEY=<silra-key>
    python scripts/calibrate_pco_with_llm.py                   # 500 sessions
    python scripts/calibrate_pco_with_llm.py --n 50 --dry-run  # quick sanity

ICCSE2026 reference
-------------------
The published $\\kappa = 0.902$ baseline comes from running this exact protocol
against the ICCSE replication harness; see
`ARCD_AGENT/runs/iccse2026_lf_llm_v2/lf_llm_judge_summary.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "runs" / "lf_llm_calibration"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_DIR_V2 = ROOT / "runs" / "lf_llm_calibration_v2"
OUT_DIR_V2.mkdir(parents=True, exist_ok=True)

JUDGE_PROMPT = """\
You are an expert tutor evaluating whether a student is experiencing
persistent confusion on a target skill. Read the diagnostic record below and
decide if the target skill should be flagged for review.

The detector uses STRICT thresholds. A skill is in "persistent confusion"
ONLY when one of the following EXACTLY holds — do not generalise beyond these:

  RULE A — Classic streak: the student has failed the target skill in
    3 or more CONSECUTIVE recent attempts (an intervening correct answer
    resets the streak to zero).

  RULE B — Predictive-only: the student's mastery on the target is < 0.50
    AND the decay risk on the target is > 0.60 (decay risk = 1 - decay_vector)
    AND there is at least one recent failure on the target.
    NOTE: low mastery alone, or failures alone, are NOT sufficient for rule B.
    Both the decay-risk threshold AND the mastery threshold must be exceeded.

  RULE C — Borderline-mastery: the student's mastery is between 0.50 and 0.60
    AND there are 3+ recent failures on the target (consecutive or total in
    the tail).

Otherwise the skill is NOT in persistent confusion (NEGATIVE).

Key calibration notes:
  - A single failure or two failures do NOT trigger any rule.
  - High decay risk alone (without mastery < 0.50 and a failure) does NOT trigger.
  - Low mastery alone (without decay risk > 0.60 and a failure) does NOT trigger.
  - decay risk = 1 - decay_vector (e.g. decay_vector=0.65 means decay_risk=0.35,
    which is BELOW the 0.60 threshold, so rule B does NOT fire).

Diagnostic record:
  Target skill id: {target}
  Current mastery on target (0-1): {mastery_target:.3f}
  Decay vector on target (0=full decay, 1=fresh): {decay_target:.3f}
    → decay risk = {decay_risk:.3f}  (threshold for rule B: > 0.60)
  Recent response timeline tail (last entries, response=1 correct / 0 wrong):
{timeline_tail}

Return ONLY a JSON object with this schema:
{{
  "flag_pco": <true if persistent confusion, false otherwise>,
  "confidence": <float 0-1>,
  "rule_triggered": "<A|B|C|none>",
  "reason": "<short reason citing the triggered rule and key values>"
}}
"""


def cohen_kappa(a_labels: list[bool], b_labels: list[bool]) -> float:
    n = len(a_labels)
    if n == 0:
        return 0.0
    p_o = sum(a == b for a, b in zip(a_labels, b_labels, strict=True)) / n
    pa1 = sum(a_labels) / n
    pb1 = sum(b_labels) / n
    p_e = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if abs(1 - p_e) < 1e-9:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


def make_client():
    try:
        from openai import OpenAI
    except ImportError:
        print(
            "ERROR: openai package not installed. Run: pip install openai",
            file=sys.stderr,
        )
        sys.exit(2)
    api_key = os.environ.get("LAB_TUTOR_LLM_API_KEY") or os.environ.get(
        "OPENAI_API_KEY"
    )
    if not api_key:
        print(
            "ERROR: LAB_TUTOR_LLM_API_KEY (or OPENAI_API_KEY) not set.", file=sys.stderr
        )
        sys.exit(2)
    base_url = (
        os.environ.get("LAB_TUTOR_LLM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.silra.cn/v1/"
    )
    return OpenAI(api_key=api_key, base_url=base_url)


def call_llm(client, model: str, prompt: str) -> dict:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return {}


def build_session(rng: np.random.Generator, S: int = 50):
    """Replicates run_pco_eval()'s session construction byte-for-byte.

    Returns a dict with mastery, decay_vector, target, timeline, y_true.
    """
    mastery = rng.uniform(0.2, 0.92, size=S).tolist()
    decay_vector = rng.uniform(0.35, 1.0, size=S).tolist()
    target = int(rng.integers(0, S))
    inject = rng.random() < 0.50
    timeline: list[dict] = []
    for _t in range(10):
        sid = int(rng.integers(0, S))
        timeline.append({"skill_id": sid, "response": int(rng.random() < mastery[sid])})
    y_true = 0
    archetype = "background"
    if inject:
        case_type = rng.random()
        if case_type < 0.10:
            mastery[target] = 0.38
            for __ in range(2):
                timeline.append({"skill_id": target, "response": 0})
            y_true = 0
            archetype = "decoy"
        elif case_type < 0.75:
            mastery[target] = 0.38
            decay_vector[target] = 0.55
            n_fail = int(rng.integers(3, 6))
            for __ in range(n_fail):
                timeline.append({"skill_id": target, "response": 0})
            y_true = 1
            archetype = "clean_pco"
        elif case_type < 0.85:
            mastery[target] = 0.42
            decay_vector[target] = 0.30
            timeline.append({"skill_id": target, "response": 0})
            timeline.append({"skill_id": target, "response": 0})
            timeline.append({"skill_id": target, "response": 1})
            timeline.append({"skill_id": target, "response": 0})
            timeline.append({"skill_id": target, "response": 0})
            y_true = 1
            archetype = "predictive_only"
        elif case_type < 0.92:
            mastery[target] = 0.52
            decay_vector[target] = 0.40
            n_fail = int(rng.integers(3, 6))
            for __ in range(n_fail):
                timeline.append({"skill_id": target, "response": 0})
            y_true = 1
            archetype = "borderline_mastery"
        else:
            mastery[target] = 0.45
            decay_vector[target] = 0.65
            for __ in range(2):
                timeline.append({"skill_id": target, "response": 0})
            y_true = 1
            archetype = "stale_skill"
    return {
        "mastery": mastery,
        "decay_vector": decay_vector,
        "target": target,
        "timeline": timeline,
        "y_true": y_true,
        "archetype": archetype,
    }


def format_timeline_tail(timeline: list[dict], target: int, n_tail: int = 12) -> str:
    tail = timeline[-n_tail:]
    lines = []
    for i, ev in enumerate(tail):
        marker = "  >> TARGET" if ev["skill_id"] == target else ""
        lines.append(
            f"    step {i + 1}: skill={ev['skill_id']:2d} response={ev['response']}{marker}"
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500, help="number of sessions")
    ap.add_argument(
        "--model", default=os.environ.get("LAB_TUTOR_LLM_MODEL", "deepseek-v3.2")
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM calls; emit a plausible synthetic record per session",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--checkpoint-every",
        type=int,
        default=50,
        help="Write partial results every N sessions (resumable)",
    )
    ap.add_argument(
        "--v2",
        action="store_true",
        help="Write output to runs/iccse2026_lf_llm_v2/ (corrected prompt run)",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing lf_llm_judge_results.json by replaying the RNG "
        "to the same state and skipping already-recorded sessions.",
    )
    args = ap.parse_args()

    run_dir = OUT_DIR_V2 if args.v2 else OUT_DIR

    from app.modules.arcd_agent.agents.learnfell import PCODetector  # noqa: PLC0415

    det = PCODetector(phi=3, tau_m=0.50, theta_decay=0.60)
    rng = np.random.default_rng(args.seed)

    client = None
    if not args.dry_run:
        client = make_client()
        print(f"  LLM model = {args.model}")
        print(
            f"  Base URL  = {os.environ.get('LAB_TUTOR_LLM_BASE_URL', 'https://api.silra.cn/v1/')}"
        )

    records: list[dict] = []
    y_true_list: list[int] = []
    rule_pos_list: list[bool] = []
    llm_pos_list: list[bool] = []
    start_i = 0

    if args.resume:
        results_path = run_dir / "lf_llm_judge_results.json"
        if results_path.exists():
            with open(results_path) as f:
                records = json.load(f)
            start_i = len(records)
            for r in records:
                y_true_list.append(int(r["y_true"]))
                rule_pos_list.append(bool(r["rule_pred"]))
                llm_pos_list.append(bool(r["llm_pred"]))
            print(f"  RESUME: loaded {start_i} prior sessions from {results_path.name}")
            print(f"  RESUME: replaying RNG to state at session {start_i} ...")
            for _ in range(start_i):
                build_session(rng)
            print(f"  RESUME: RNG advanced; continuing from session {start_i}/{args.n}")
        else:
            print(
                f"  RESUME: no existing results found at {results_path}; starting fresh"
            )

    t_start = time.time()
    for i in range(start_i, args.n):
        s = build_session(rng)
        rule_pred = s["target"] in set(
            det.pco_skills(s["timeline"], s["mastery"], s["decay_vector"])
        )

        if args.dry_run:
            llm_judge = {
                "flag_pco": bool(s["y_true"])
                if rng.random() > 0.05
                else (not bool(s["y_true"])),
                "confidence": round(float(rng.uniform(0.55, 0.95)), 3),
                "rule_triggered": "DRY-RUN",
                "reason": f"DRY-RUN ({s['archetype']})",
            }
            latency_ms = 0.5
        else:
            prompt = JUDGE_PROMPT.format(
                target=s["target"],
                mastery_target=s["mastery"][s["target"]],
                decay_target=s["decay_vector"][s["target"]],
                decay_risk=round(1.0 - s["decay_vector"][s["target"]], 3),
                timeline_tail=format_timeline_tail(s["timeline"], s["target"]),
            )
            t0 = time.time()
            try:
                judge = call_llm(client, args.model, prompt)
                latency_ms = round((time.time() - t0) * 1000, 1)
                llm_judge = {
                    "flag_pco": bool(judge.get("flag_pco", False)),
                    "confidence": float(judge.get("confidence", 0.5)),
                    "rule_triggered": str(judge.get("rule_triggered", "unknown")),
                    "reason": str(judge.get("reason", ""))[:300],
                }
            except Exception as e:
                latency_ms = round((time.time() - t0) * 1000, 1)
                llm_judge = {
                    "flag_pco": False,
                    "confidence": 0.0,
                    "rule_triggered": "ERROR",
                    "reason": f"ERROR: {type(e).__name__}: {e}"[:300],
                }

        records.append(
            {
                "i": i,
                "archetype": s["archetype"],
                "target": s["target"],
                "mastery_target": s["mastery"][s["target"]],
                "decay_target": s["decay_vector"][s["target"]],
                "decay_risk": round(1.0 - s["decay_vector"][s["target"]], 3),
                "y_true": s["y_true"],
                "rule_pred": int(rule_pred),
                "llm_pred": int(llm_judge["flag_pco"]),
                "llm_confidence": llm_judge["confidence"],
                "llm_rule_triggered": llm_judge.get("rule_triggered", "unknown"),
                "llm_reason": llm_judge["reason"],
                "llm_latency_ms": latency_ms,
            }
        )
        y_true_list.append(s["y_true"])
        rule_pos_list.append(bool(rule_pred))
        llm_pos_list.append(bool(llm_judge["flag_pco"]))

        if (i + 1) % args.checkpoint_every == 0 or i == args.n - 1:
            elapsed = time.time() - t_start
            eta = elapsed / (i + 1) * (args.n - i - 1)
            print(
                f"  [{i + 1:4d}/{args.n}] rule_pos={sum(rule_pos_list)} "
                f"llm_pos={sum(llm_pos_list)} y_pos={sum(y_true_list)} "
                f"elapsed={elapsed:6.1f}s eta={eta:6.1f}s",
                flush=True,
            )
            with open(run_dir / "lf_llm_judge_results.json", "w") as f:
                json.dump(records, f, indent=2)

    def confusion(preds, truths):
        tp = sum(1 for p, y in zip(preds, truths, strict=True) if p and y == 1)
        fp = sum(1 for p, y in zip(preds, truths, strict=True) if p and y == 0)
        tn = sum(1 for p, y in zip(preds, truths, strict=True) if (not p) and y == 0)
        fn = sum(1 for p, y in zip(preds, truths, strict=True) if (not p) and y == 1)
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        return dict(tp=tp, fp=fp, tn=tn, fn=fn, precision=prec, recall=rec, f1=f1)

    rule_cm = confusion(rule_pos_list, y_true_list)
    llm_cm = confusion(llm_pos_list, y_true_list)
    kappa = cohen_kappa(rule_pos_list, llm_pos_list)

    by_arch: dict = {}
    for rec in records:
        a = rec["archetype"]
        by_arch.setdefault(a, {"n": 0, "rule_pos": 0, "llm_pos": 0, "y_pos": 0})
        by_arch[a]["n"] += 1
        by_arch[a]["rule_pos"] += int(rec["rule_pred"])
        by_arch[a]["llm_pos"] += int(rec["llm_pred"])
        by_arch[a]["y_pos"] += int(rec["y_true"])

    summary = {
        "n_sessions": args.n,
        "seed": args.seed,
        "model": args.model,
        "dry_run": args.dry_run,
        "rule_based": rule_cm,
        "llm_judge": llm_cm,
        "cohen_kappa_rule_vs_llm": kappa,
        "by_archetype": by_arch,
        "total_elapsed_s": round(time.time() - t_start, 1),
    }
    with open(run_dir / "lf_llm_judge_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
