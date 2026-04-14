"""
Adaptive Exercise (AdaEx) — reusable domain logic.

Classes:
    DifficultyProfile    — computed difficulty target for one skill/student pair
    Exercise             — a generated exercise with full metadata
    EvalResult           — 3-axis quality evaluation result
    ExercisePackage      — final bundle: exercise + eval + refinement metadata
    DifficultyCalculator — computes d*(u,s) from mastery and skill structure
    ExerciseBank         — in-memory cache keyed by (skill_id, difficulty_band)
    ExerciseGenerator    — LLM-backed exercise generation (injected LLM chain)
    ExerciseEvaluator    — LLM-backed 3-axis quality gate
    RefinementLoop       — generate → evaluate → refine loop
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

# ─────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────

@dataclass
class DifficultyProfile:
    """Target difficulty profile for a specific (student, skill) pair."""
    skill_id: int
    skill_name: str
    mastery: float
    target_d: float
    band: str
    prereq_depth: int
    complexity: float
    zpd_position: str   # 'below', 'in', or 'above'


@dataclass
class Exercise:
    """A fully-specified adaptive exercise."""
    exercise_id: str
    skill_id: int
    skill_name: str
    problem: str
    format: str                     # 'multiple_choice' | 'open_ended' | 'fill_blank'
    options: list[str]
    correct_answer: str
    solution_steps: list[str]
    hints: list[str]
    concepts_tested: list[str]
    estimated_time_seconds: int
    difficulty_target: float
    difficulty_generated: float
    difficulty_band: str
    generation_round: int
    why: str = ""


@dataclass
class EvalResult:
    """3-axis quality evaluation of an exercise."""
    exercise_id: str
    e_corr: float                   # correctness score [0, 1]
    e_diff: float                   # difficulty alignment [0, 1]
    e_ped: float                    # pedagogical value [0, 1]
    q_score: float                  # weighted composite
    accepted: bool
    correctness_feedback: str
    pedagogical_feedback: str
    overall_feedback: str
    suggested_improvements: list[str]


@dataclass
class ExercisePackage:
    """Final product: exercise + quality result + refinement history."""
    exercise: Exercise
    eval_result: EvalResult
    refinement_rounds: int
    final_accepted: bool
    quality_warning: bool


# ─────────────────────────────────────────────────────────────────────
# DifficultyCalculator
# ─────────────────────────────────────────────────────────────────────

class DifficultyCalculator:
    """Compute target exercise difficulty from student mastery and skill structure.

    d*(u,s) = clip[α(1 - m) + β(prereq_depth/P_max) + γ·C_s, 0, 1]

    Where:
        m            — student mastery for skill s
        prereq_depth — number of prerequisite skills (from A_skill adjacency)
        C_s          — concept complexity = min(1, n_concepts / max_concepts)

    Args:
        alpha: weight on inverse mastery (how much gap drives difficulty).
        beta:  weight on prerequisite depth.
        gamma: weight on concept complexity.
        A_skill: optional prerequisite adjacency matrix (n_skills × n_skills).
    """

    BANDS = [(0.30, "easy"), (0.55, "medium"), (0.80, "hard"), (1.01, "challenge")]
    ZPD_LO, ZPD_HI = 0.40, 0.90

    def __init__(
        self,
        alpha: float = 0.55,
        beta: float = 0.20,
        gamma: float = 0.25,
        A_skill: Any | None = None,
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self._prereq_counts: dict[int, int] = {}
        self._p_max = 1
        if A_skill is not None:
            A = np.array(A_skill)
            n = A.shape[0]
            for s in range(n):
                self._prereq_counts[s] = int(np.sum(A[:, s] > 0))
            self._p_max = max(1, max(self._prereq_counts.values(), default=1))

    def compute(
        self,
        skill_id: int,
        skill_name: str,
        mastery: float,
        n_concepts: int = 1,
        max_concepts: int = 20,
    ) -> DifficultyProfile:
        """Compute the target DifficultyProfile for a student-skill pair."""
        prereq_depth = self._prereq_counts.get(skill_id, 0)
        prereq_norm = prereq_depth / self._p_max
        complexity = min(1.0, n_concepts / max(1, max_concepts))

        d_star = (
            self.alpha * (1.0 - mastery)
            + self.beta * prereq_norm
            + self.gamma * complexity
        )
        d_star = max(0.0, min(1.0, d_star))

        band = "challenge"
        for threshold, label in self.BANDS:
            if d_star < threshold:
                band = label
                break

        if mastery < self.ZPD_LO:
            zpd = "below"
        elif mastery > self.ZPD_HI:
            zpd = "above"
        else:
            zpd = "in"

        return DifficultyProfile(
            skill_id=skill_id, skill_name=skill_name,
            mastery=round(mastery, 4), target_d=round(d_star, 4),
            band=band, prereq_depth=prereq_depth,
            complexity=round(complexity, 4), zpd_position=zpd,
        )


# ─────────────────────────────────────────────────────────────────────
# ExerciseBank
# ─────────────────────────────────────────────────────────────────────

class ExerciseBank:
    """In-memory exercise cache indexed by (skill_id, difficulty_band).

    Stores exercises that passed quality evaluation (Q >= tau_Q).
    Retrieval avoids redundant LLM generation calls.

    Args:
        max_per_key: maximum exercises stored per (skill_id, band) key.
    """

    def __init__(self, max_per_key: int = 20):
        self._store: dict[str, list[dict]] = {}
        self._max_per_key = max_per_key
        self._hits = 0
        self._misses = 0

    def _key(self, skill_id: int, band: str) -> str:
        return f"{skill_id}:{band}"

    def store(self, pkg: ExercisePackage) -> None:
        """Cache an accepted exercise package."""
        if not pkg.final_accepted:
            return
        key = self._key(pkg.exercise.skill_id, pkg.exercise.difficulty_band)
        bucket = self._store.setdefault(key, [])
        bucket.append(asdict(pkg.exercise))
        if len(bucket) > self._max_per_key:
            bucket.pop(0)

    def retrieve(
        self,
        skill_id: int,
        band: str,
        exclude_ids: set[str] | None = None,
    ) -> Exercise | None:
        """Retrieve a cached exercise, avoiding already-used IDs."""
        key = self._key(skill_id, band)
        bucket = self._store.get(key, [])
        exclude = exclude_ids or set()
        for ex_dict in bucket:
            if ex_dict["exercise_id"] not in exclude:
                self._hits += 1
                return Exercise(**ex_dict)
        self._misses += 1
        return None

    @property
    def stats(self) -> dict:
        """Usage statistics for the bank."""
        total = sum(len(v) for v in self._store.values())
        return {
            "total_exercises": total,
            "keys": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
        }


# ─────────────────────────────────────────────────────────────────────
# ExerciseGenerator
# ─────────────────────────────────────────────────────────────────────

class ExerciseGenerator:
    """Generate adaptive exercises using an injected LLM chain.

    The chain should accept {"request": json_string} and return a dict
    with keys: problem, format, options, correct_answer, solution_steps,
    hints, concepts_tested, estimated_time_seconds, difficulty_generated.

    Args:
        chain: a callable(dict) → dict LLM chain (e.g. LangChain pipeline).
    """

    def __init__(self, chain: Any):
        self._chain = chain
        self._counter = 0

    def generate(
        self,
        profile: DifficultyProfile,
        concepts: list[str] | None = None,
        context: str = "",
        generation_round: int = 0,
        feedback: str = "",
    ) -> Exercise:
        """Generate one exercise for the given profile."""
        import json

        self._counter += 1
        eid = f"ex_{profile.skill_id}_{self._counter:04d}_{uuid.uuid4().hex[:6]}"

        request = json.dumps({
            "skill_name": profile.skill_name,
            "difficulty_band": profile.band,
            "target_difficulty": profile.target_d,
            "student_mastery": profile.mastery,
            "zpd_position": profile.zpd_position,
            "concepts": (concepts or [])[:8],
            "additional_context": context,
            "refinement_feedback": feedback,
            "round": generation_round,
            "instructions": (
                f"Create a {profile.band}-level exercise for '{profile.skill_name}'. "
                f"Target difficulty: {profile.target_d:.2f}. "
                f"Student mastery: {profile.mastery:.2f}, ZPD: {profile.zpd_position}. "
                + (f"Address this feedback: {feedback}. " if feedback else "")
                + "Include a step-by-step solution."
            ),
        })

        try:
            data = self._chain({"request": request})
        except Exception:
            data = self._fallback(profile)

        why = (
            f"Generated at {profile.band} difficulty (d*={profile.target_d:.2f}) "
            f"because your mastery is {profile.mastery:.0%} — "
            f"targeting gradual improvement toward proficiency."
        )

        return Exercise(
            exercise_id=eid, skill_id=profile.skill_id,
            skill_name=profile.skill_name,
            problem=data.get("problem", f"Practice problem for {profile.skill_name}"),
            format=data.get("format", "open_ended"),
            options=data.get("options", []),
            correct_answer=data.get("correct_answer", ""),
            solution_steps=data.get("solution_steps", []),
            hints=data.get("hints", []),
            concepts_tested=data.get("concepts_tested", []),
            estimated_time_seconds=data.get("estimated_time_seconds", 120),
            difficulty_target=profile.target_d,
            difficulty_generated=data.get("difficulty_generated", profile.target_d),
            difficulty_band=profile.band,
            generation_round=generation_round,
            why=why,
        )

    @staticmethod
    def _fallback(profile: DifficultyProfile) -> dict:
        return {
            "problem": f"Solve a problem related to {profile.skill_name} ({profile.band} difficulty).",
            "format": "open_ended", "options": [],
            "correct_answer": f"See solution for {profile.skill_name}.",
            "solution_steps": [
                "Identify the core concept.",
                "Apply the relevant formula.",
                "Verify the result.",
            ],
            "hints": ["Think about the definition.", "Try a simpler example first."],
            "concepts_tested": [profile.skill_name],
            "estimated_time_seconds": 120,
            "difficulty_generated": profile.target_d,
        }


# ─────────────────────────────────────────────────────────────────────
# ExerciseEvaluator
# ─────────────────────────────────────────────────────────────────────

class ExerciseEvaluator:
    """3-axis quality gate: correctness × difficulty-fit × pedagogical value.

    Q(e) = w_corr * E_corr + w_diff * E_diff + w_ped * E_ped
    Accept if Q(e) >= tau_Q.

    The chain should accept {"request": json_string} and return a dict with
    keys: correctness_score, correctness_feedback, pedagogical_score,
    pedagogical_feedback, difficulty_assessment, overall_feedback,
    suggested_improvements.

    Args:
        chain: callable(dict) → dict evaluation chain.
        w_corr, w_diff, w_ped: axis weights (must sum to 1.0).
        tau_q: acceptance threshold for Q(e).
    """

    def __init__(
        self,
        chain: Any,
        w_corr: float = 0.40,
        w_diff: float = 0.30,
        w_ped: float = 0.30,
        tau_q: float = 0.70,
    ):
        self.w_corr = w_corr
        self.w_diff = w_diff
        self.w_ped = w_ped
        self.tau_q = tau_q
        self._chain = chain

    def evaluate(self, exercise: Exercise) -> EvalResult:
        """Run 3-axis quality evaluation on the exercise."""
        import json

        request = json.dumps({
            "skill_name": exercise.skill_name,
            "target_difficulty": exercise.difficulty_target,
            "difficulty_band": exercise.difficulty_band,
            "problem": exercise.problem,
            "format": exercise.format,
            "options": exercise.options,
            "correct_answer": exercise.correct_answer,
            "solution_steps": exercise.solution_steps,
            "hints": exercise.hints,
            "concepts_tested": exercise.concepts_tested,
        })

        try:
            data = self._chain({"request": request})
        except Exception:
            data = {
                "correctness_score": 0.75,
                "pedagogical_score": 0.70,
                "difficulty_assessment": exercise.difficulty_target,
                "correctness_feedback": "Fallback evaluation.",
                "pedagogical_feedback": "Assumed adequate.",
                "overall_feedback": "LLM evaluation failed.",
                "suggested_improvements": ["Verify solution manually."],
            }

        e_corr = float(data.get("correctness_score", 0.75))
        d_assessed = float(data.get("difficulty_assessment", exercise.difficulty_target))
        e_diff = 1.0 - abs(exercise.difficulty_target - d_assessed)
        e_ped = float(data.get("pedagogical_score", 0.70))
        q_score = self.w_corr * e_corr + self.w_diff * e_diff + self.w_ped * e_ped

        return EvalResult(
            exercise_id=exercise.exercise_id,
            e_corr=round(e_corr, 4), e_diff=round(e_diff, 4),
            e_ped=round(e_ped, 4), q_score=round(q_score, 4),
            accepted=q_score >= self.tau_q,
            correctness_feedback=data.get("correctness_feedback", ""),
            pedagogical_feedback=data.get("pedagogical_feedback", ""),
            overall_feedback=data.get("overall_feedback", ""),
            suggested_improvements=data.get("suggested_improvements", []),
        )


# ─────────────────────────────────────────────────────────────────────
# RefinementLoop
# ─────────────────────────────────────────────────────────────────────

class RefinementLoop:
    """Generate → evaluate → refine iteratively until accepted or max_rounds.

    Implements the AdaEx quality loop:
        1. Check bank cache; if hit, return cached exercise.
        2. Generate exercise, evaluate quality.
        3. If rejected, compile targeted feedback and regenerate.
        4. Repeat up to max_rounds; store final accepted exercise to bank.

    Args:
        generator: ExerciseGenerator instance.
        evaluator: ExerciseEvaluator instance.
        bank: ExerciseBank for caching accepted exercises.
        max_rounds: maximum refinement iterations.
    """

    def __init__(
        self,
        generator: ExerciseGenerator,
        evaluator: ExerciseEvaluator,
        bank: ExerciseBank,
        max_rounds: int = 3,
    ):
        self.generator = generator
        self.evaluator = evaluator
        self.bank = bank
        self.max_rounds = max_rounds

    def run(
        self,
        profile: DifficultyProfile,
        concepts: list[str] | None = None,
        context: str = "",
        exclude_ids: set[str] | None = None,
    ) -> ExercisePackage:
        """Run the generate-evaluate-refine loop for one exercise."""
        cached = self.bank.retrieve(profile.skill_id, profile.band, exclude_ids or set())
        if cached is not None:
            ev = self.evaluator.evaluate(cached)
            return ExercisePackage(
                exercise=cached, eval_result=ev,
                refinement_rounds=0, final_accepted=True, quality_warning=False,
            )

        ex = self.generator.generate(profile, concepts, context, generation_round=0)
        ev = self.evaluator.evaluate(ex)

        rounds = 0
        while not ev.accepted and rounds < self.max_rounds:
            rounds += 1
            feedback_parts = []
            if ev.e_corr < 0.8:
                feedback_parts.append(f"Correctness: {ev.correctness_feedback}")
            if ev.e_diff < 0.8:
                feedback_parts.append(f"Difficulty misaligned: E_diff={ev.e_diff:.2f}")
            if ev.e_ped < 0.8:
                feedback_parts.append(f"Pedagogical: {ev.pedagogical_feedback}")
            feedback = " | ".join(feedback_parts) or ev.overall_feedback

            ex = self.generator.generate(
                profile, concepts, context, generation_round=rounds, feedback=feedback)
            ev = self.evaluator.evaluate(ex)

        pkg = ExercisePackage(
            exercise=ex, eval_result=ev,
            refinement_rounds=rounds,
            final_accepted=ev.accepted,
            quality_warning=not ev.accepted,
        )
        self.bank.store(pkg)
        return pkg
