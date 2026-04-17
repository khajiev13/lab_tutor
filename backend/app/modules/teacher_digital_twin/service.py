"""Teacher Digital Twin — service layer.

Implements the 5 digital twin features:
  1. Skill difficulty based on actual student mastery (PerceivedDifficulty)
  2. Most/least studied skills by class (skill popularity)
  3. Class mastery overview per student
  4. Student group paths (students grouped by shared skill sets)
  5. What-if forward simulation (manual + automatic modes)
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict

from neo4j import Driver as Neo4jDriver

from app.core.settings import settings

from .repository import TeacherDigitalTwinRepository
from .schemas import (
    ClassMasteryResponse,
    MultiSkillSimulationRequest,
    MultiSkillSimulationResponse,
    SkillCoherencePair,
    SkillCoherenceResult,
    SkillDifficultyItem,
    SkillDifficultyResponse,
    SkillInterventionImpact,
    SkillPopularityItem,
    SkillPopularityResponse,
    SkillSimResult,
    SkillSimulationResponse,
    SkillTarget,
    StudentGroup,
    StudentGroupMember,
    StudentGroupsResponse,
    StudentMasterySummary,
    WhatIfRequest,
    WhatIfResponse,
)

logger = logging.getLogger(__name__)


class TeacherDigitalTwinService:
    """Aggregated class-level analytics for the Teacher Digital Twin."""

    def __init__(self, neo4j_driver: Neo4jDriver) -> None:
        self._driver = neo4j_driver

    def _repo(self, session) -> TeacherDigitalTwinRepository:
        return TeacherDigitalTwinRepository(session)

    # ── Feature 1: Skill Difficulty ───────────────────────────────────

    def get_skill_difficulty(self, course_id: int) -> SkillDifficultyResponse:
        """
        Perceived difficulty per skill based on student mastery.

        Formula:
          AvgMastery(s) = (1/N) * SUM_{i=1}^{N} m_{i,s}
          PerceivedDifficulty(s) = 1 - AvgMastery(s)
        """
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            rows = self._repo(session).get_skill_difficulty(course_id)

        skills = [
            SkillDifficultyItem(
                skill_name=r["skill_name"],
                student_count=int(r["student_count"] or 0),
                avg_mastery=round(float(r["avg_mastery"] or 0.0), 4),
                perceived_difficulty=round(float(r["perceived_difficulty"] or 1.0), 4),
            )
            for r in rows
            if r["skill_name"]
        ]
        return SkillDifficultyResponse(
            course_id=course_id,
            skills=skills,
            total_skills=len(skills),
        )

    # ── Feature 2: Skill Popularity ───────────────────────────────────

    def get_skill_popularity(self, course_id: int) -> SkillPopularityResponse:
        """Return most and least selected skills across the class."""
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)
            rows = repo.get_skill_popularity(course_id)
            total_students = repo.get_total_students(course_id)

        all_skills = [
            SkillPopularityItem(
                skill_name=r["skill_name"],
                selection_count=int(r["selection_count"] or 0),
                rank=i + 1,
            )
            for i, r in enumerate(rows)
            if r["skill_name"]
        ]
        top5 = all_skills[:5]
        bottom5 = (
            list(reversed(all_skills[-5:]))
            if len(all_skills) >= 5
            else list(reversed(all_skills))
        )

        return SkillPopularityResponse(
            course_id=course_id,
            all_skills=all_skills,
            most_popular=top5,
            least_popular=bottom5,
            total_students=total_students,
        )

    # ── Feature 3: Class Mastery Overview ─────────────────────────────

    def get_class_mastery(self, course_id: int) -> ClassMasteryResponse:
        """
        Per-student mastery summary.

        at_risk = True if avg_mastery < 0.40 OR pco_count > 2
        """
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)
            rows = repo.get_class_mastery(course_id)
            pco_counts = repo.get_class_pco_counts(course_id)

        students = []
        for r in rows:
            uid = r["user_id"]
            avg_m = float(r["avg_mastery"] or 0.0)
            pco = pco_counts.get(uid, 0)
            students.append(
                StudentMasterySummary(
                    user_id=uid,
                    full_name=r.get("full_name") or r.get("email") or str(uid),
                    email=r.get("email") or "",
                    selected_skill_count=int(r.get("selected_skill_count") or 0),
                    avg_mastery=round(avg_m, 4),
                    mastered_count=int(r.get("mastered_count") or 0),
                    struggling_count=int(r.get("struggling_count") or 0),
                    pco_count=pco,
                    at_risk=avg_m < 0.50 or pco > 2,
                )
            )

        class_avg = (
            sum(s.avg_mastery for s in students) / max(len(students), 1)
            if students
            else 0.0
        )
        return ClassMasteryResponse(
            course_id=course_id,
            students=students,
            class_avg_mastery=round(class_avg, 4),
            at_risk_count=sum(1 for s in students if s.at_risk),
            total_students=len(students),
        )

    # ── Feature 4: Student Group Paths ────────────────────────────────

    def get_student_groups(self, course_id: int) -> StudentGroupsResponse:
        """
        Group students by performance tier (mastery level).

        Tier thresholds:
          - Advanced (≥ 80%)
          - Developing (50-79%)
          - Foundational (< 50%)

        Within each tier, suggest a shared learning path based on weakest common skills.
        """
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            rows = self._repo(session).get_student_skills_for_grouping(course_id)

        # Group by performance tier
        TIERS = [
            ("advanced", 0.80, 1.01, "Advanced Learners"),
            ("developing", 0.50, 0.80, "Developing Learners"),
            ("foundational", 0.0, 0.50, "Foundational Learners"),
        ]

        tier_buckets: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            avg = float(r.get("avg_mastery") or 0.0)
            tier_id = "developing"
            for tid, lo, hi, _ in TIERS:
                if lo <= avg < hi:
                    tier_id = tid
                    break
            tier_buckets[tier_id].append(r)

        groups: list[StudentGroup] = []

        for tier_id, _lo, _hi, tier_label in TIERS:
            members = tier_buckets.get(tier_id, [])
            if not members:
                continue

            skill_set = sorted(
                set(s for m in members for s in (m.get("skill_names") or []))
            )
            member_objs = [
                StudentGroupMember(
                    user_id=m["user_id"],
                    full_name=m.get("full_name") or str(m["user_id"]),
                    avg_mastery=round(float(m.get("avg_mastery") or 0.0), 4),
                )
                for m in members
            ]
            group_avg = sum(mb.avg_mastery for mb in member_objs) / max(
                len(member_objs), 1
            )
            suggested_path = self._suggest_group_path(members, skill_set)

            key = hashlib.md5(tier_id.encode()).hexdigest()[:8]
            if len(members) >= 1:
                groups.append(
                    StudentGroup(
                        group_id=key,
                        group_name=tier_label,
                        performance_tier=tier_id,
                        skill_set=skill_set,
                        member_count=len(members),
                        members=member_objs,
                        group_avg_mastery=round(group_avg, 4),
                        suggested_path=suggested_path,
                    )
                )

        groups.sort(key=lambda g: g.group_avg_mastery, reverse=True)

        return StudentGroupsResponse(
            course_id=course_id,
            groups=groups,
            ungrouped_students=[],
            total_groups=len(groups),
        )

    def _suggest_group_path(
        self, members: list[dict], skill_set: list[str]
    ) -> list[str]:
        """Compute group average mastery and return skills sorted by mastery ascending (ZPD order)."""
        if not skill_set:
            return []
        # Aggregate mastery per skill using simple average across members
        skill_mastery: dict[str, list[float]] = defaultdict(list)
        for m in members:
            avg = float(m.get("avg_mastery") or 0.0)
            for s in m.get("skill_names") or []:
                skill_mastery[s].append(avg)

        scored = []
        for s in skill_set:
            vals = skill_mastery.get(s, [0.0])
            avg_m = sum(vals) / max(len(vals), 1)
            # ZPD priority: skills in [0.40, 0.90] get higher score
            if 0.40 <= avg_m <= 0.90:
                score = 1.0 - avg_m  # lower mastery = higher urgency within ZPD
            elif avg_m < 0.40:
                score = 0.5 - avg_m  # below ZPD but still needs work
            else:
                score = 0.0  # already mastered
            scored.append((s, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:8]]

    # ── Feature 5: What-If Forward Simulation ─────────────────────────

    def run_what_if(self, course_id: int, req: WhatIfRequest) -> WhatIfResponse:
        """
        Simulate the impact of teaching specific skills.

        Manual mode: teacher selects skills + hypothetical mastery values.
        Automatic mode:
          - Identify struggling skills (class avg < 0.50)
          - Simulate Delta boost for each
          - ClassGain(s_k) = SUM_{i} (min(1, m_{i,s_k} + Delta) - m_{i,s_k})
          - Rank by ClassGain descending
        """
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            skill_data = self._repo(session).get_class_skill_mastery(course_id)

        # skill_data: [{skill_name, student_masteries: [{user_id, mastery}]}]
        class_mastery: dict[str, list[float]] = {}
        for row in skill_data:
            name = row["skill_name"]
            vals = [
                float(sm["mastery"] or 0.0) for sm in (row["student_masteries"] or [])
            ]
            class_mastery[name] = vals

        skill_impacts: list[SkillInterventionImpact] = []
        recommendations: list[str] = []
        simulated_path: list[str] = []
        pco_analysis: list[str] = []
        llm_recommendation: str | None = None

        if req.mode == "manual" and req.skills:
            # Manual: use the teacher's specified hypothetical mastery
            for ws in req.skills:
                name = ws.skill_name
                hypo = float(ws.hypothetical_mastery)
                current_vals = class_mastery.get(name, [0.0])
                current_avg = sum(current_vals) / max(len(current_vals), 1)
                gain = (hypo - current_avg) * len(current_vals)
                students_helped = sum(1 for v in current_vals if v < hypo)
                recommendation_score = (
                    max(0.0, hypo - current_avg) * 0.6
                    + (students_helped / max(len(current_vals), 1)) * 0.4
                )
                skill_impacts.append(
                    SkillInterventionImpact(
                        skill_name=name,
                        current_avg_mastery=round(current_avg, 4),
                        simulated_avg_mastery=round(hypo, 4),
                        class_gain=round(gain, 4),
                        students_helped=students_helped,
                        recommendation_score=round(recommendation_score, 4),
                    )
                )

            skill_impacts.sort(key=lambda x: x.recommendation_score, reverse=True)
            simulated_path = [
                imp.skill_name for imp in skill_impacts[: max(1, req.top_k)]
            ]

            struggling_manual = [
                imp for imp in skill_impacts if imp.current_avg_mastery < 0.50
            ]
            if struggling_manual:
                recommendations = [
                    f"Focus on '{imp.skill_name}' — current avg mastery is "
                    f"{imp.current_avg_mastery:.0%}, simulated gain: {imp.class_gain:.1f} mastery points"
                    for imp in sorted(
                        struggling_manual, key=lambda x: x.class_gain, reverse=True
                    )[:3]
                ]

        else:
            # Automatic: simulate delta boost on each skill
            delta = float(req.delta or req.target_gain or 0.20)
            for name, current_vals in class_mastery.items():
                if not current_vals:
                    continue
                current_avg = sum(current_vals) / len(current_vals)
                simulated_vals = [min(1.0, v + delta) for v in current_vals]
                simulated_avg = sum(simulated_vals) / len(simulated_vals)
                class_gain = sum(
                    sv - cv for sv, cv in zip(simulated_vals, current_vals, strict=True)
                )
                students_helped = sum(1 for cv in current_vals if cv < 0.90)
                recommendation_score = (
                    (0.5 - current_avg if current_avg < 0.5 else 0.0) * 0.5
                    + (class_gain / max(len(current_vals), 1)) * 0.3
                    + (students_helped / max(len(current_vals), 1)) * 0.2
                )
                skill_impacts.append(
                    SkillInterventionImpact(
                        skill_name=name,
                        current_avg_mastery=round(current_avg, 4),
                        simulated_avg_mastery=round(simulated_avg, 4),
                        class_gain=round(class_gain, 4),
                        students_helped=students_helped,
                        recommendation_score=round(recommendation_score, 4),
                    )
                )

            # Dynamic best strategy score instead of only class_gain
            skill_impacts.sort(key=lambda x: x.recommendation_score, reverse=True)

            # Identify struggling skills for recommendations
            struggling = [
                imp for imp in skill_impacts if imp.current_avg_mastery < 0.50
            ]
            recommendations = [
                f"Teach '{imp.skill_name}' — class avg {imp.current_avg_mastery:.0%}, "
                f"estimated gain: {imp.class_gain:.1f} mastery points across {imp.students_helped} students"
                for imp in struggling[:5]
            ]

            # Simulated path = top-impact skills in ZPD order
            zpd_skills = [
                imp for imp in skill_impacts if 0.40 <= imp.current_avg_mastery <= 0.90
            ]
            simulated_path = [imp.skill_name for imp in zpd_skills[: max(1, req.top_k)]]
            if not simulated_path:
                simulated_path = [
                    imp.skill_name for imp in skill_impacts[: max(1, req.top_k)]
                ]

            # PCO analysis: skills with low mastery and high difficulty
            pco_candidates = [
                imp for imp in skill_impacts if imp.current_avg_mastery < 0.40
            ]
            pco_analysis = [
                f"'{imp.skill_name}' — only {imp.current_avg_mastery:.0%} class mastery, "
                f"high risk of concept overclaiming"
                for imp in pco_candidates[:3]
            ]

        summary = (
            f"Simulated {len(skill_impacts)} skills. "
            f"Top recommendation: {recommendations[0] if recommendations else 'No struggling skills found.'}"
        )

        if req.enable_llm:
            llm_recommendation = self._build_llm_recommendation(
                course_id=course_id,
                mode=req.mode,
                skill_impacts=skill_impacts[: max(1, req.top_k)],
                recommendations=recommendations[:3],
                summary=summary,
            )

        return WhatIfResponse(
            mode=req.mode,
            course_id=course_id,
            simulated_path=simulated_path,
            pco_analysis=pco_analysis,
            recommendations=recommendations,
            skill_impacts=skill_impacts[:20],  # cap response size
            summary=summary,
            llm_recommendation=llm_recommendation,
        )

    # ── Feature 6b: Multi-Skill Simulation with Coherence ─────────────────────

    def simulate_multiple_skills(
        self,
        course_id: int,
        req: MultiSkillSimulationRequest,
    ) -> MultiSkillSimulationResponse:
        """
        Simulate multiple skills in one pass.

        For each skill:
        - Generate an adaptive exercise at the specified (or class-average) mastery.
        - Return difficulty / mastery stats.

        Across all skills:
        - Compute pairwise Jaccard similarity from co-selection data.
        - Cluster highly-related skills (Jaccard ≥ 0.40).
        - Suggest a teaching order (foundations → advanced by avg mastery).
        """
        from app.modules.cognitive_diagnosis.service import CognitiveDiagnosisService

        db = settings.neo4j_database
        cd_service = CognitiveDiagnosisService(self._driver)
        auto_selected_skills: list[str] = []

        # ── 0. Automatic mode: pick top-K most difficult skills if none provided ──
        if req.mode == "automatic" or not req.skills:
            with self._driver.session(database=db) as session:
                all_difficulty = self._repo(session).get_skill_difficulty(course_id)
            # Sort by perceived difficulty (highest first = lowest mastery)
            sorted_diff = sorted(
                all_difficulty, key=lambda r: float(r.get("avg_mastery") or 1.0)
            )
            top_k = max(1, min(req.top_k, 10, len(sorted_diff)))
            skill_names = [r["skill_name"] for r in sorted_diff[:top_k]]
            auto_selected_skills = list(skill_names)
            # Build SkillTarget list for uniform downstream handling
            req = MultiSkillSimulationRequest(
                mode=req.mode,
                skills=[SkillTarget(skill_name=sn) for sn in skill_names],
                top_k=req.top_k,
                default_mastery=req.default_mastery,
            )
        else:
            skill_names = [t.skill_name for t in req.skills]

        # ── 1. Fetch class-level difficulty stats for all selected skills ──────
        with self._driver.session(database=db) as session:
            difficulty_rows = self._repo(session).get_skill_difficulty(course_id)

        difficulty_map: dict[str, dict] = {r["skill_name"]: r for r in difficulty_rows}

        # ── 2. Generate per-skill exercise + stats ────────────────────────────
        skill_results: list[SkillSimResult] = []
        for target in req.skills:
            sname = target.skill_name
            row = difficulty_map.get(sname)
            avg_class = float(row["avg_mastery"] or 0.0) if row else 0.0
            student_count = int(row["student_count"] or 0) if row else 0
            perceived_diff = round(1.0 - avg_class, 4)

            mastery = (
                target.simulated_mastery
                if target.simulated_mastery is not None
                else req.default_mastery
            )

            exercise = cd_service.generate_exercise(
                user_id=0,
                skill_name=sname,
                context=f"teacher_simulation:mastery={mastery:.2f}",
            )

            opts = exercise.options or []
            ans = exercise.correct_answer or ""
            try:
                cidx = opts.index(ans)
            except ValueError:
                cidx = 0
            skill_results.append(
                SkillSimResult(
                    skill_name=sname,
                    simulated_mastery=round(mastery, 4),
                    avg_class_mastery=round(avg_class, 4),
                    perceived_difficulty=perceived_diff,
                    student_count=student_count,
                    question=exercise.problem,
                    options=opts,
                    correct_index=cidx,
                    explanation=exercise.why,
                )
            )

        # ── 3. Coherence analysis via co-selection data ───────────────────────
        with self._driver.session(database=db) as session:
            co_rows = self._repo(session).get_skill_co_selection(course_id, skill_names)

        # skill_selections[skill] = set of user_ids who selected it
        skill_selections: dict[str, set] = defaultdict(set)
        skill_mastery_vals: dict[str, list[float]] = defaultdict(list)
        for row in co_rows:
            sn = row["skill_name"]
            uid = row["user_id"]
            score = float(row["mastery_score"])
            skill_selections[sn].add(uid)
            if score >= 0:
                skill_mastery_vals[sn].append(score)

        # Pairwise Jaccard
        pairs: list[SkillCoherencePair] = []
        for i in range(len(skill_names)):
            for j in range(i + 1, len(skill_names)):
                a, b = skill_names[i], skill_names[j]
                set_a = skill_selections.get(a, set())
                set_b = skill_selections.get(b, set())
                union = len(set_a | set_b)
                jaccard = len(set_a & set_b) / union if union > 0 else 0.0
                pairs.append(
                    SkillCoherencePair(
                        skill_a=a, skill_b=b, jaccard_score=round(jaccard, 3)
                    )
                )

        overall = round(sum(p.jaccard_score for p in pairs) / max(len(pairs), 1), 3)
        label = "High" if overall >= 0.6 else ("Medium" if overall >= 0.3 else "Low")

        # Teaching order: sort by ascending avg mastery (foundational skills first)
        def _avg_mastery(sn: str) -> float:
            vals = skill_mastery_vals.get(sn, [])
            return sum(vals) / len(vals) if vals else 0.5

        teaching_order = sorted(skill_names, key=_avg_mastery)

        # Clusters: connected components with Jaccard ≥ 0.40
        adj: dict[str, set] = defaultdict(set)
        for p in pairs:
            if p.jaccard_score >= 0.40:
                adj[p.skill_a].add(p.skill_b)
                adj[p.skill_b].add(p.skill_a)

        visited: set[str] = set()
        clusters: list[list[str]] = []
        for sn in skill_names:
            if sn not in visited:
                cluster: list[str] = []
                queue = [sn]
                while queue:
                    cur = queue.pop()
                    if cur in visited:
                        continue
                    visited.add(cur)
                    cluster.append(cur)
                    queue.extend(adj[cur] - visited)
                clusters.append(cluster)

        # Common students: those who selected ≥ 2 of the chosen skills
        student_skill_count: dict[int, int] = defaultdict(int)
        for s_set in skill_selections.values():
            for uid in s_set:
                student_skill_count[uid] += 1
        common_students = sum(1 for cnt in student_skill_count.values() if cnt >= 2)

        coherence = SkillCoherenceResult(
            overall_score=overall,
            label=label,
            pairs=pairs,
            teaching_order=teaching_order,
            clusters=clusters,
            common_students=common_students,
        )

        # LLM insights in automatic mode or when skills > 1
        llm_insights: str | None = None
        if req.mode == "automatic" or len(skill_results) > 1:
            llm_insights = self._generate_simulator_insights(
                course_id, skill_results, coherence, req.mode
            )

        return MultiSkillSimulationResponse(
            mode=req.mode,
            course_id=course_id,
            auto_selected_skills=auto_selected_skills,
            skill_results=skill_results,
            coherence=coherence,
            llm_insights=llm_insights,
        )

    def simulate_skill(
        self, course_id: int, skill_name: str, simulated_mastery: float
    ) -> SkillSimulationResponse:
        """
        Generate an adaptive exercise for a given skill at a specified mastery level.
        Used by teachers to test how difficult a skill exercise feels.
        """
        from app.modules.cognitive_diagnosis.service import CognitiveDiagnosisService

        # Reuse AdaEx for the exercise — pass mastery=simulated_mastery as context
        cd_service = CognitiveDiagnosisService(self._driver)
        exercise = cd_service.generate_exercise(
            user_id=0,  # teacher context; no real student
            skill_name=skill_name,
            context=f"teacher_simulation:mastery={simulated_mastery:.2f}",
        )

        # Get class-level difficulty stats for this skill
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            rows = self._repo(session).get_skill_difficulty(course_id)

        skill_row = next((r for r in rows if r["skill_name"] == skill_name), None)
        avg_class_mastery = float(skill_row["avg_mastery"] or 0.0) if skill_row else 0.0
        student_count = int(skill_row["student_count"] or 0) if skill_row else 0
        perceived_difficulty = 1.0 - avg_class_mastery

        opts = exercise.options or []
        ans = exercise.correct_answer or ""
        try:
            cidx = opts.index(ans)
        except ValueError:
            cidx = 0
        return SkillSimulationResponse(
            skill_name=skill_name,
            simulated_mastery=round(simulated_mastery, 4),
            perceived_difficulty=round(perceived_difficulty, 4),
            avg_class_mastery=round(avg_class_mastery, 4),
            student_count=student_count,
            question=exercise.problem,
            options=opts,
            correct_index=cidx,
            explanation=exercise.why,
        )

    # ── Teacher-scoped student drilldown (read-only proxy) ─────────────────

    def get_student_portfolio(
        self, teacher_id: int, student_id: int, course_id: int
    ) -> dict:
        """Return a student's ARCD portfolio — only if teacher teaches the class."""
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            teaches = self._repo(session).teacher_teaches_class(teacher_id, course_id)
        if not teaches:
            from fastapi import HTTPException, status

            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="You do not teach this class.",
            )
        from app.modules.cognitive_diagnosis.service import CognitiveDiagnosisService

        return CognitiveDiagnosisService(self._driver).get_arcd_portfolio(
            student_id, course_id
        )

    def get_student_twin(
        self, teacher_id: int, student_id: int, course_id: int
    ) -> dict:
        """Return a student's digital twin data — only if teacher teaches the class."""
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            teaches = self._repo(session).teacher_teaches_class(teacher_id, course_id)
        if not teaches:
            from fastapi import HTTPException, status

            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="You do not teach this class.",
            )
        from app.modules.cognitive_diagnosis.service import CognitiveDiagnosisService

        return CognitiveDiagnosisService(self._driver).get_arcd_twin(
            student_id, course_id
        )

    def _generate_simulator_insights(
        self,
        course_id: int,
        skill_results: list,
        coherence: SkillCoherenceResult,
        mode: str,
    ) -> str | None:
        """Generate LLM-powered pedagogical insights for the skill simulation results."""
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.llm_api_key or "no-key",
                base_url=settings.llm_base_url,
            )
            skills_summary = "\n".join(
                f"- {r.skill_name}: difficulty={r.perceived_difficulty:.0%}, "
                f"class mastery={r.avg_class_mastery:.0%}, "
                f"simulated mastery={r.simulated_mastery:.0%}, "
                f"students={r.student_count}"
                for r in skill_results[:8]
            )
            order_str = " → ".join(coherence.teaching_order[:6])
            clusters_str = ", ".join(
                "[" + ", ".join(c) + "]" for c in coherence.clusters[:4]
            )
            prompt = (
                f"Course ID: {course_id}  |  Mode: {mode}\n\n"
                f"Skill simulation results (sorted by difficulty):\n{skills_summary}\n\n"
                f"Coherence: {coherence.label} ({coherence.overall_score:.0%} Jaccard), "
                f"{coherence.common_students} students share ≥2 of these skills.\n"
                f"Recommended teaching order: {order_str}\n"
                f"Skill clusters: {clusters_str}\n\n"
                "As an instructional strategy assistant, provide:\n"
                "1. Why these skills are challenging (1-2 sentences)\n"
                "2. Recommended teaching sequence with brief justification\n"
                "3. One actionable intervention for the hardest skill\n"
                "4. Which skill clusters should be taught together and why\n"
                "Keep the response concise (under 200 words), practical, and teacher-facing."
            )
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert instructional designer helping teachers improve student outcomes. Provide concise, actionable insights.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=400,
            )
            return (response.choices[0].message.content or "").strip() or None
        except Exception as exc:
            logger.warning("Simulator LLM insights failed: %s", exc)
            return None

    def _build_llm_recommendation(
        self,
        course_id: int,
        mode: str,
        skill_impacts: list[SkillInterventionImpact],
        recommendations: list[str],
        summary: str,
    ) -> str | None:
        """Optional LLM narrative for the What-If panel."""
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.llm_api_key or "no-key",
                base_url=settings.llm_base_url,
            )
            top_lines = [
                f"{i + 1}. {s.skill_name} | gain={s.class_gain:.2f} | score={s.recommendation_score:.2f} | students={s.students_helped}"
                for i, s in enumerate(skill_impacts[:5])
            ]
            prompt = (
                f"Course: {course_id}\n"
                f"Mode: {mode}\n"
                f"Summary: {summary}\n"
                f"Top skill impacts:\n" + "\n".join(top_lines) + "\n"
                "Rule-based recommendations:\n"
                + "\n".join(recommendations[:3])
                + "\n\n"
                "Write a concise strategic recommendation (4-6 bullets) for a teacher. "
                "Include one 'why now' point and one action sequence for next week."
            )
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an instructional strategy assistant for teacher analytics.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            return (response.choices[0].message.content or "").strip() or None
        except Exception as exc:
            logger.warning("What-if LLM recommendation failed: %s", exc)
            return None
