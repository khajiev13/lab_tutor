from __future__ import annotations

import torch
import torch.nn as nn


class DifficultyDecay(nn.Module):
    """Difficulty-adjusted decay: harder skills are forgotten faster.

    δ^diff_{u,s} = (δ^base_{u,s})^{β_s}

    β_s is a learnable per-skill difficulty exponent,
    clamped to [0.5, 2.0].
    """

    def __init__(self, n_skills: int):
        super().__init__()
        self.beta_raw = nn.Parameter(torch.ones(n_skills))

    def forward(self, delta_base: torch.Tensor) -> torch.Tensor:
        """
        Args:
            delta_base: [B, S] base retention from BaseDecay
        Returns:
            [B, S] difficulty-adjusted retention
        """
        beta = self.beta_raw.clamp(0.5, 2.0)
        return delta_base.pow(beta.unsqueeze(0))
