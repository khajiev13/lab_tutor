"""Lift concept-level prerequisites to skill-level prerequisite edges."""

from __future__ import annotations

from src.skill_derivation.models import SkillCluster, SkillPrerequisite


def fetch_concept_prereqs(driver, course_id: str | None = None) -> list[tuple[str, str]]:
    """Query PREREQ_OF edges between CONCEPT nodes."""
    with driver.session() as session:
        if course_id:
            result = session.run(
                "MATCH (c1:CONCEPT)-[:PREREQ_OF]->(c2:CONCEPT) "
                "WHERE (c1.area = $cid OR c1.course_id = $cid) "
                "RETURN c1.concept_id AS src, c2.concept_id AS dst",
                cid=course_id,
            )
        else:
            result = session.run(
                "MATCH (c1:CONCEPT)-[:PREREQ_OF]->(c2:CONCEPT) "
                "RETURN c1.concept_id AS src, c2.concept_id AS dst"
            )
        return [(r["src"] or "", r["dst"] or "") for r in result if r["src"] and r["dst"]]


def derive_skill_prerequisites(
    skills: list[SkillCluster],
    concept_prereqs: list[tuple[str, str]],
    tau: float = 0.1,
) -> list[SkillPrerequisite]:
    """Compute skill-level prerequisite edges from concept-level ones."""
    concept_to_skill: dict[str, int] = {}
    for idx, sk in enumerate(skills):
        for cid in sk.concept_ids:
            concept_to_skill[cid] = idx

    cross_counts: dict[tuple[int, int], int] = {}
    for src, dst in concept_prereqs:
        s_a = concept_to_skill.get(src)
        s_b = concept_to_skill.get(dst)
        if s_a is not None and s_b is not None and s_a != s_b:
            cross_counts[(s_a, s_b)] = cross_counts.get((s_a, s_b), 0) + 1

    prereqs: list[SkillPrerequisite] = []
    for (a, b), count in cross_counts.items():
        strength = count / max(len(skills[b].concept_ids), 1)
        if strength >= tau:
            prereqs.append(SkillPrerequisite(
                from_skill=skills[a].skill_id,
                to_skill=skills[b].skill_id,
                strength=round(strength, 4),
            ))
    return prereqs
