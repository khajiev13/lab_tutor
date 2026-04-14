"""LLM-based cluster coherence validation and skill naming."""

from __future__ import annotations

from dataclasses import dataclass

from src.llm.base import BaseLLMProvider


@dataclass
class ClusterValidation:
    cluster_idx: int
    coherent: bool
    skill_name: str
    description: str
    action: str  # "keep", "split", "merge"


def validate_clusters(
    clusters: list[list[str]],
    llm_provider: BaseLLMProvider,
) -> list[ClusterValidation]:
    """Send each cluster to the LLM for coherence check and naming."""
    validations: list[ClusterValidation] = []
    for idx, concepts in enumerate(clusters):
        prompt = (
            f"You are an educational curriculum expert. Evaluate this group of concepts "
            f"that were automatically clustered together:\n\n"
            f"Cluster {idx + 1}: {concepts}\n\n"
            f"Respond in JSON with keys: coherent (bool), skill_name (str), "
            f"description (str 1-2 sentences), action (keep|split|merge)."
        )
        try:
            result = llm_provider.complete_json(prompt, temperature=0.0)
            validations.append(ClusterValidation(
                cluster_idx=idx,
                coherent=result.get("coherent", True),
                skill_name=result.get("skill_name", f"skill_{idx + 1:02d}"),
                description=result.get("description", ""),
                action=result.get("action", "keep"),
            ))
        except Exception:
            validations.append(ClusterValidation(
                cluster_idx=idx,
                coherent=True,
                skill_name=f"skill_{idx + 1:02d}",
                description="Auto-generated cluster",
                action="keep",
            ))
    return validations


def should_recluster(validations: list[ClusterValidation], threshold: float = 0.2) -> bool:
    """Return True if more than *threshold* fraction of clusters are incoherent."""
    if not validations:
        return False
    incoherent = sum(1 for v in validations if not v.coherent)
    return (incoherent / len(validations)) > threshold
