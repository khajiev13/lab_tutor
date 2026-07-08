from __future__ import annotations

from pydantic import BaseModel


class SkillGapRead(BaseModel):
    skill_name: str
    coverage: str
    reason: str


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def score_market_skill_coverage(
    *,
    cv_skill_names: list[str],
    market_skill_names: list[str],
) -> list[SkillGapRead]:
    cv_norms = {_norm(name) for name in cv_skill_names if name.strip()}
    scores: list[SkillGapRead] = []
    for skill_name in market_skill_names:
        covered = _norm(skill_name) in cv_norms
        scores.append(
            SkillGapRead(
                skill_name=skill_name,
                coverage="covered" if covered else "gap",
                reason=(
                    "Exact normalized CV skill match"
                    if covered
                    else "No exact CV skill match"
                ),
            )
        )
    return scores
