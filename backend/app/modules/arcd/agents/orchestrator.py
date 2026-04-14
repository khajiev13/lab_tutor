"""
app/modules/arcd/agents/orchestrator.py — Multi-Agent ARCD Orchestrator.

Implements a LangGraph closed-loop cycle:
    assess → pathgen → review → exercises → reassess ⟲ (or finalize)

The orchestrator composes PathGenerator, PCODetector, FastReviewMode, and
DifficultyCalculator from the rest of agents/, providing a single entry
point to drive the full adaptive tutoring loop.

Usage (standalone):
    from app.modules.arcd.agents.orchestrator import ARCDOrchestrator

    orch = ARCDOrchestrator(A_skill=A, skill_names=names, llm=llm)
    result = orch.run(student_dict, skills_list)

Usage (LangGraph graph only):
    from app.modules.arcd.agents.orchestrator import build_orchestrator
    graph = build_orchestrator(A_skill=A, skill_names=names, llm=llm)
    state = graph.invoke(initial_state)
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Literal

import numpy as np

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore[assignment]

from app.modules.arcd.agents.adaex import DifficultyCalculator
from app.modules.arcd.agents.pathgen import PathGenConfig, PathGenerator
from app.modules.arcd.agents.revfell import (
    FastReviewMode,
    MasterySync,
    PCODetector,
)

# ── Orchestrator state ────────────────────────────────────────────────


class OrchestratorState(TypedDict, total=False):
    """LangGraph state dict shared across all orchestrator nodes."""

    # Input (set before first node)
    student: dict
    skills: list
    dataset_id: str
    A_skill: Any                    # np.ndarray prerequisite adjacency
    skill_names: dict               # {skill_id: str}

    # Computed by assess_node
    mastery: list
    timeline: list
    iteration: int
    max_iterations: int
    started_at: str

    # Computed by pathgen_node
    learning_path: dict

    # Computed by review_node
    review_result: dict
    post_review_mastery: list

    # Computed by exercise_node
    exercises: dict

    # Computed by reassess_node
    deviation_detected: bool

    # Accumulated across all nodes
    orchestrator_log: list
    completed_at: str


# ── Node builders ─────────────────────────────────────────────────────


def _make_pathgen_agent(state: OrchestratorState):
    """Build a PathGenerator from state."""
    A = state["A_skill"]
    names = state.get("skill_names", {})
    cfg = PathGenConfig(path_length=5)
    return PathGenerator(A_pre=A, skill_names=names, config=cfg)


def _skill_name(skills: list, sid: int) -> str:
    if 0 <= sid < len(skills):
        s = skills[sid]
        return s.get("name", f"Skill {sid}") if isinstance(s, dict) else str(s)
    return f"Skill {sid}"


# ── Individual graph nodes ────────────────────────────────────────────


def assess_node(state: OrchestratorState) -> dict:
    """Extract current mastery and timeline from the student profile."""
    s = state["student"]
    m = list(s.get("final_mastery", []))
    it = state.get("iteration", 0) + 1
    log = state.get("orchestrator_log", []) + [{
        "step": "assess", "iter": it,
        "avg_mastery": round(float(np.mean(m)), 4) if m else 0.0,
        "ts": datetime.datetime.now().isoformat(),
    }]
    return {
        "mastery": m,
        "timeline": s.get("timeline", []),
        "iteration": it,
        "started_at": state.get("started_at", datetime.datetime.now().isoformat()),
        "orchestrator_log": log,
    }


def _build_pathgen_node(A_skill, skill_names: dict, llm=None):
    """Return a pathgen_node closure bound to the given graph and LLM."""

    def pathgen_node(state: OrchestratorState) -> dict:
        from app.modules.arcd.agents.pathgen import PathGenConfig, PathGenerator
        cfg = PathGenConfig(path_length=5)
        gen = PathGenerator(A_pre=A_skill, skill_names=skill_names, config=cfg)

        mastery = list(state["mastery"])
        path = gen.generate(mastery=mastery)

        it = state.get("iteration", 1)
        return {
            "learning_path": path,
            "orchestrator_log": state.get("orchestrator_log", []) + [{
                "step": "pathgen", "iter": it,
                "path_len": path.get("path_length", 0),
                "gain": path.get("total_predicted_gain", 0.0),
                "ts": datetime.datetime.now().isoformat(),
            }],
        }

    return pathgen_node


def _build_review_node(A_skill, skills_list: list, llm=None):
    """Return a review_node closure."""
    n = A_skill.shape[0] if hasattr(A_skill, "shape") else len(skills_list)
    pco_det = PCODetector(phi=3, tau_m=0.60)
    fast_rev = FastReviewMode(mu=0.3, t_max=168.0)
    sync = MasterySync(eta_base=0.10)

    def review_node(state: OrchestratorState) -> dict:
        mastery = list(state["mastery"])
        timeline = state.get("timeline", [])
        it = state.get("iteration", 1)

        # PCO detection
        pco_ids = list(pco_det.pco_skills(timeline, mastery))

        # Hours since last practice
        now = time.time()
        last_ts: dict[int, float] = {}
        for e in timeline:
            sid = e.get("skill_id", -1)
            ts_str = e.get("timestamp", "")
            if 0 <= sid < n and ts_str:
                try:
                    ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                    if sid not in last_ts or ts > last_ts[sid]:
                        last_ts[sid] = ts
                except (ValueError, TypeError):
                    pass
        hours = {s: (now - last_ts.get(s, now - 168 * 3600)) / 3600 for s in range(n)}

        # Fast review ranking
        fast_reviews = []
        fast_candidates = fast_rev.rank_for_review(mastery, hours, n, set(pco_ids), top_k=3)
        for sid, urgency in fast_candidates:
            if 0 <= sid < len(skills_list):
                fast_reviews.append({
                    "skill_id": sid,
                    "skill_name": _skill_name(skills_list, sid),
                    "urgency": round(urgency, 4),
                    "mastery": round(mastery[sid] if sid < len(mastery) else 0.5, 4),
                })

        # Apply MasterySync for PCO skills (small penalty for forgetting)
        updated = list(mastery)
        for sid in pco_ids:
            sync.update(updated, sid, 0)

        pco_count = len(pco_ids)
        slow_plans = [{"skill_id": sid, "skill_name": _skill_name(skills_list, sid),
                        "mode": "slow_thinking"} for sid in pco_ids[:2]]

        # Replan if PCO detected or mastery changed significantly
        needs_replan = pco_count > 0

        exegen_requests = [{"skill_id": fr["skill_id"], "skill_name": fr["skill_name"],
                             "student_mastery": fr["mastery"]} for fr in fast_reviews[:2]]

        rv = {
            "updated_mastery": updated,
            "pco_skills_detected": pco_ids,
            "pco_count": pco_count,
            "fast_reviews": fast_reviews,
            "slow_thinking_plans": slow_plans,
            "mastery_delta": round(float(np.mean(np.abs(np.array(updated[:n]) - np.array(mastery[:n])))), 4),
            "needs_replan": needs_replan,
            "exegen_requests": exegen_requests,
        }

        return {
            "review_result": rv,
            "post_review_mastery": updated,
            "orchestrator_log": state.get("orchestrator_log", []) + [{
                "step": "review", "iter": it,
                "pco": pco_count,
                "fast": len(fast_reviews),
                "slow": len(slow_plans),
                "replan": needs_replan,
                "ts": datetime.datetime.now().isoformat(),
            }],
        }

    return review_node


def _build_exercise_node(A_skill):
    """Return an exercise_node closure."""
    diff_calc = DifficultyCalculator(A_skill=A_skill)

    def exercise_node(state: OrchestratorState) -> dict:
        mastery = state.get("post_review_mastery", state.get("mastery", []))
        skills_list = state.get("skills", [])
        rv = state.get("review_result", {})
        reqs = rv.get("exegen_requests", [])
        it = state.get("iteration", 1)

        exercises = []
        if reqs:
            targets = [(r.get("skill_id", 0), r.get("skill_name", ""),
                        r.get("student_mastery", 0.5)) for r in reqs]
        else:
            n = len(mastery)
            ranked = sorted(range(min(n, len(skills_list))), key=lambda s: mastery[s] if s < n else 1.0)
            targets = [(s, _skill_name(skills_list, s), mastery[s] if s < n else 0.5)
                       for s in ranked[:2]]

        for sid, sname, m in targets:
            profile = diff_calc.compute(sid, sname, float(m))
            exercises.append({
                "skill_id": sid,
                "skill_name": sname,
                "target_difficulty": profile.target_d,
                "difficulty_band": profile.band,
                "zpd_position": profile.zpd_position,
                "why": (f"Target difficulty {profile.target_d:.2f} ({profile.band}) "
                        f"for mastery {m:.0%} — generated without LLM in orchestrator baseline."),
            })

        ex_out = {
            "exercises": exercises,
            "stats": {"total_generated": len(exercises), "total_accepted": len(exercises)},
            "generated_at": datetime.datetime.now().isoformat(),
        }

        return {
            "exercises": ex_out,
            "orchestrator_log": state.get("orchestrator_log", []) + [{
                "step": "exercises", "iter": it,
                "n_ex": len(exercises),
                "from_revfell": len(reqs),
                "ts": datetime.datetime.now().isoformat(),
            }],
        }

    return exercise_node


def _reassess_node(state: OrchestratorState) -> dict:
    """Compare pre/post mastery to decide whether to replan."""
    pre = state.get("mastery", [])
    post = state.get("post_review_mastery", pre)
    n = min(len(pre), len(post))
    deltas = [abs(post[i] - pre[i]) for i in range(n)]
    mx = max(deltas) if deltas else 0.0
    mn = float(np.mean(deltas)) if deltas else 0.0

    rv = state.get("review_result", {})
    dev = (mx >= 0.10) or rv.get("needs_replan", False) or (rv.get("pco_count", 0) > 0)
    can_iterate = state.get("iteration", 1) < state.get("max_iterations", 2)
    it = state.get("iteration", 1)

    return {
        "deviation_detected": dev and can_iterate,
        "mastery": post,
        "orchestrator_log": state.get("orchestrator_log", []) + [{
            "step": "reassess", "iter": it,
            "max_delta": round(mx, 4), "mean_delta": round(mn, 4),
            "deviation": dev, "will_replan": dev and can_iterate,
            "ts": datetime.datetime.now().isoformat(),
        }],
    }


def _finalize_node(state: OrchestratorState) -> dict:
    """Write final results into the student dict and close the log."""
    s = state.get("student", {})
    s["final_mastery"] = state.get("post_review_mastery", state.get("mastery", []))
    s["learning_path"] = state.get("learning_path", {})
    s["review_session"] = state.get("review_result", {})
    s["adaex_session"] = state.get("exercises", {})
    s["orchestrator_log"] = state.get("orchestrator_log", [])
    it = state.get("iteration", 1)
    return {
        "student": s,
        "completed_at": datetime.datetime.now().isoformat(),
        "orchestrator_log": state.get("orchestrator_log", []) + [{
            "step": "finalize", "iter": it,
            "ts": datetime.datetime.now().isoformat(),
        }],
    }


def _route_reassess(state: OrchestratorState) -> Literal["pathgen", "finalize"]:
    return "pathgen" if state.get("deviation_detected", False) else "finalize"


# ── Public factory ────────────────────────────────────────────────────


def build_orchestrator(A_skill, skill_names: dict | None = None, llm=None,
                        max_iterations: int = 2):
    """Build and return a compiled LangGraph StateGraph for the ARCD orchestrator.

    Args:
        A_skill:        numpy prerequisite adjacency matrix (n_skills × n_skills).
        skill_names:    optional {skill_id: name} dict for human-readable logs.
        llm:            optional LangChain LLM for RevFell LLM-assisted features.
        max_iterations: maximum reassess-replan iterations (default 2).

    Returns:
        Compiled LangGraph app ready for `app.invoke(initial_state)`.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise ImportError(
            "langgraph is required. Install it with: pip install langgraph"
        ) from exc

    names = skill_names or {}
    skills_list = [{"name": names.get(i, f"Skill {i}")} for i in range(A_skill.shape[0])]

    pathgen_node = _build_pathgen_node(A_skill, names, llm)
    review_node  = _build_review_node(A_skill, skills_list, llm)
    exercise_node = _build_exercise_node(A_skill)

    wf = StateGraph(OrchestratorState)
    wf.add_node("assess",    assess_node)
    wf.add_node("pathgen",   pathgen_node)
    wf.add_node("review",    review_node)
    wf.add_node("exercises", exercise_node)
    wf.add_node("reassess",  _reassess_node)
    wf.add_node("finalize",  _finalize_node)

    wf.add_edge(START,       "assess")
    wf.add_edge("assess",    "pathgen")
    wf.add_edge("pathgen",   "review")
    wf.add_edge("review",    "exercises")
    wf.add_edge("exercises", "reassess")
    wf.add_conditional_edges("reassess", _route_reassess,
                              {"pathgen": "pathgen", "finalize": "finalize"})
    wf.add_edge("finalize", END)

    return wf.compile()


# ── Convenience wrapper ───────────────────────────────────────────────


class ARCDOrchestrator:
    """High-level wrapper for the ARCD multi-agent orchestration cycle.

    Example::

        orch = ARCDOrchestrator(A_skill=A, skill_names=names)
        updated_student = orch.run(student_dict, skills_list)
    """

    def __init__(self, A_skill, skill_names: dict | None = None,
                 llm=None, max_iterations: int = 2):
        self._app = build_orchestrator(A_skill, skill_names, llm, max_iterations)
        self._A = A_skill
        self._names = skill_names or {}
        self._max_iter = max_iterations

    def run(self, student: dict, skills: list,
            dataset_id: str = "default") -> dict:
        """Run the full orchestration cycle for one student.

        Args:
            student:    Student portfolio dict with ``final_mastery`` and ``timeline``.
            skills:     List of skill dicts from the dataset.
            dataset_id: Dataset identifier string (for logging).

        Returns:
            Updated student dict with ``learning_path``, ``review_session``,
            ``adaex_session``, and ``orchestrator_log`` attached.
        """
        initial: OrchestratorState = {
            "student":        student,
            "skills":         skills,
            "dataset_id":     dataset_id,
            "A_skill":        self._A,
            "skill_names":    self._names,
            "iteration":      0,
            "max_iterations": self._max_iter,
            "orchestrator_log": [],
            "started_at":     datetime.datetime.now().isoformat(),
        }
        final = self._app.invoke(initial)
        return final.get("student", student)
