from __future__ import annotations

import torch
import torch.nn as nn


class MasteryDecay(nn.Module):
    """Mastery-adjusted decay: high-mastery skills resist forgetting.

    δ^mast_{u,s} = (δ^rel_{u,s} + ε)^{1 / M_{u,s}(t)}

    M_{u,s}(t) is clamped to [1, 5] to prevent extreme exponents.
    """

    def __init__(self, epsilon: float = 1e-8):
        super().__init__()
        self.epsilon = epsilon

    def forward(self, delta_rel: torch.Tensor, mastery: torch.Tensor) -> torch.Tensor:
        """
        Args:
            delta_rel: [B, S] relationally-adjusted retention
            mastery:   [B, S] mastery estimates from MasteryHead
        Returns:
            [B, S] mastery-adjusted retention
        """
        M = mastery.clamp(1.0, 5.0)
        return (delta_rel + self.epsilon).pow(1.0 / M)
