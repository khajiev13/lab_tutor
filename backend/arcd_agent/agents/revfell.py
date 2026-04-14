"""
Review Fellow — reusable domain logic.

Classes:
    PCOResult        — dataclass for a single skill's PCO analysis
    PCODetector      — hybrid rule-based + decay-signal PCO detection
    FastReviewMode   — urgency-based review scheduling
    MasterySync      — decay-aware online mastery update (EMA)
    EmotionalState   — lightweight student emotional state tracker
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PCOResult:
    """Result of PCO (Prior Correct to Overclaim) detection for one skill."""
    skill_id: int
    is_pco: bool
    failure_streak: int
    mastery: float
    total_attempts: int
    recent_accuracy: float
    decay_risk: float   # 0-1, 0 = fully retained
    why: str


class PCODetector:
    """Hybrid PCO detection: rule-based streak + ARCD decay signal.

    A skill is flagged PCO if EITHER:
      (a) Classic: tail failure streak >= phi AND mastery < tau_m, OR
      (b) Predictive: decay_risk > theta_decay AND mastery < tau_m
          (student hasn't failed yet but is about to forget)

    Args:
        phi: minimum consecutive tail failures to trigger classic PCO.
        tau_m: mastery threshold below which PCO can fire.
        theta_decay: decay risk threshold for predictive PCO.
    """

    def __init__(self, phi: int = 3, tau_m: float = 0.50, theta_decay: float = 0.60):
        self.phi = phi
        self.tau_m = tau_m
        self.theta_decay = theta_decay

    def detect(
        self,
        timeline: list[dict],
        mastery: list[float],
        decay_vector: list[float] | None = None,
    ) -> dict[int, PCOResult]:
        """Analyse timeline and mastery to detect PCO skills.

        Args:
            timeline: list of interaction dicts with keys skill_id, response.
            mastery: per-skill mastery values indexed by skill_id.
            decay_vector: optional per-skill decay values (0 = forgotten).

        Returns:
            dict mapping skill_id → PCOResult for all observed skills.
        """
        skill_events: dict[int, list[int]] = {}
        for entry in timeline:
            sid = entry.get("skill_id", -1)
            if sid >= 0:
                skill_events.setdefault(sid, []).append(entry.get("response", 0))

        n_skills = max(len(mastery), max(skill_events.keys(), default=-1) + 1)
        results: dict[int, PCOResult] = {}

        for sid in range(n_skills):
            responses = skill_events.get(sid, [])
            streak = self._max_tail_streak(responses) if responses else 0
            m = mastery[sid] if sid < len(mastery) else 0.0
            total = len(responses)
            recent = responses[-min(10, len(responses)):] if responses else []
            acc = sum(recent) / len(recent) if recent else 0.0
            d_risk = (
                float(1.0 - decay_vector[sid])
                if (decay_vector is not None and sid < len(decay_vector))
                else 0.0
            )

            classic_pco = streak >= self.phi and m < self.tau_m
            predictive_pco = d_risk > self.theta_decay and m < self.tau_m and total > 0
            is_pco = classic_pco or predictive_pco

            why = ""
            if classic_pco and predictive_pco:
                why = f"Failing (streak={streak}) AND high decay risk ({d_risk:.0%})"
            elif classic_pco:
                why = f"Consecutive failures (streak={streak}, mastery={m:.0%})"
            elif predictive_pco:
                why = f"Predicted forgetting: decay risk {d_risk:.0%}, mastery {m:.0%}"

            if sid in skill_events or is_pco:
                results[sid] = PCOResult(
                    skill_id=sid, is_pco=is_pco, failure_streak=streak,
                    mastery=round(m, 4), total_attempts=total,
                    recent_accuracy=round(acc, 4), decay_risk=round(d_risk, 4),
                    why=why,
                )
        return results

    def pco_skills(
        self,
        timeline: list[dict],
        mastery: list[float],
        decay_vector: list[float] | None = None,
    ) -> list[int]:
        """Return list of skill IDs flagged as PCO."""
        return [sid for sid, r in self.detect(timeline, mastery, decay_vector).items() if r.is_pco]

    @staticmethod
    def _max_tail_streak(responses: list[int]) -> int:
        streak = 0
        for r in reversed(responses):
            if r == 0:
                streak += 1
            else:
                break
        return streak


class FastReviewMode:
    """Urgency-based review scheduler.

    Computes per-skill urgency:
        U_s = (1 - m_s) * decay_s + mu * time_factor_s

    where decay_s = 1 - exp(-0.01 * hours_since_s)
    and   time_factor_s = min(1, hours_since_s / t_max)

    Args:
        mu: weight on the time-since-last-practice component.
        t_max: maximum hours to consider for time_factor (default 168 = 1 week).
    """

    def __init__(self, mu: float = 0.3, t_max: float = 168.0):
        self.mu = mu
        self.t_max = t_max

    def compute_urgency(
        self,
        mastery: list[float],
        hours_since: dict[int, float],
        n_skills: int,
    ) -> dict[int, float]:
        """Compute urgency score for all skills."""
        urgency: dict[int, float] = {}
        for s in range(n_skills):
            m = mastery[s] if s < len(mastery) else 0.5
            h = hours_since.get(s, 168.0)
            decay = 1.0 - math.exp(-0.01 * h)
            time_factor = min(1.0, h / self.t_max)
            urgency[s] = (1.0 - m) * decay + self.mu * time_factor
        return urgency

    def rank_for_review(
        self,
        mastery: list[float],
        hours_since: dict[int, float],
        n_skills: int,
        pco_set: set[int],
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        """Return top-k (skill_id, urgency) tuples, excluding PCO and near-mastered skills."""
        urgency = self.compute_urgency(mastery, hours_since, n_skills)
        candidates = [
            (s, u) for s, u in urgency.items()
            if s not in pco_set and (s >= len(mastery) or mastery[s] < 0.95)
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]


class MasterySync:
    """Decay-aware online mastery update (EMA).

    Standard update:  m_new = m_old + eta * (y - m_old)
    With decay boost: eta = eta_base + decay_boost * (1 - delta_s)

    The decay boost encodes the Ebbinghaus relearning effect: skills that
    have decayed more benefit from a higher effective learning rate when
    revisited.

    Args:
        eta_base: base learning rate.
        decay_boost: additional learning rate per unit of decay.
    """

    def __init__(self, eta_base: float = 0.10, decay_boost: float = 0.15):
        self.eta_base = eta_base
        self.decay_boost = decay_boost

    def update(
        self,
        mastery: list[float],
        skill_id: int,
        outcome: float,
        decay_value: float | None = None,
    ) -> None:
        """Update mastery in-place for skill_id given a binary outcome.

        Args:
            mastery: mutable list of mastery values.
            skill_id: index into mastery.
            outcome: 1.0 for correct, 0.0 for incorrect.
            decay_value: current decay value for the skill (0-1); if None, base eta is used.
        """
        if 0 <= skill_id < len(mastery):
            eta = self.eta_base
            if decay_value is not None:
                eta = self.eta_base + self.decay_boost * (1.0 - decay_value)
            mastery[skill_id] = mastery[skill_id] + eta * (outcome - mastery[skill_id])


class EmotionalState:
    """Lightweight student emotional state tracker.

    Tracks four states: engaged, confused, frustrated, bored.
    Transitions are driven by observable signals during a review session.
    """

    ENGAGED = "engaged"
    CONFUSED = "confused"
    FRUSTRATED = "frustrated"
    BORED = "bored"

    def __init__(self):
        self.state = self.ENGAGED
        self._consecutive_wrong = 0
        self._consecutive_correct = 0
        self._hint_requests = 0
        self._skip_count = 0

    def observe(self, event: str, **kwargs) -> None:
        """Update state based on an observable event.

        Supported events: 'correct', 'wrong', 'hint_request', 'skip', 'explain_request'
        """
        if event == "correct":
            self._consecutive_wrong = 0
            self._consecutive_correct += 1
            self._hint_requests = 0
            self.state = self.BORED if self._consecutive_correct >= 3 else self.ENGAGED

        elif event == "wrong":
            self._consecutive_correct = 0
            self._consecutive_wrong += 1
            if self._consecutive_wrong >= 3:
                self.state = self.FRUSTRATED
            elif self._consecutive_wrong >= 2:
                self.state = self.CONFUSED

        elif event in ("hint_request", "explain_request"):
            self._hint_requests += 1
            if self._hint_requests >= 2 and self._consecutive_wrong >= 1:
                self.state = self.CONFUSED

        elif event == "skip":
            self._skip_count += 1
            if self._skip_count >= 2:
                self.state = self.FRUSTRATED

    @property
    def teaching_strategy(self) -> dict:
        """Adaptive teaching adjustments based on the current emotional state."""
        strategies = {
            self.ENGAGED: {
                "difficulty_adjust": 0,
                "show_worked_example": False,
                "tone": "encouraging",
                "note": "",
            },
            self.CONFUSED: {
                "difficulty_adjust": 0,
                "show_worked_example": False,
                "tone": "supportive and clear",
                "note": (
                    "Student seems confused. Use simpler language, provide analogies, "
                    "and suggest reviewing prerequisite material."
                ),
            },
            self.FRUSTRATED: {
                "difficulty_adjust": -1,
                "show_worked_example": True,
                "tone": "warm and patient",
                "note": (
                    "Student is frustrated. Lower difficulty, show a worked example, "
                    "and acknowledge the challenge explicitly."
                ),
            },
            self.BORED: {
                "difficulty_adjust": +1,
                "show_worked_example": False,
                "tone": "challenging and energetic",
                "note": (
                    "Student seems bored (rapid correct answers). Increase difficulty "
                    "or present a creative challenge variant."
                ),
            },
        }
        return strategies.get(self.state, strategies[self.ENGAGED])

    def reset(self) -> None:
        """Reset to initial engaged state."""
        self.state = self.ENGAGED
        self._consecutive_wrong = 0
        self._consecutive_correct = 0
        self._hint_requests = 0
        self._skip_count = 0
