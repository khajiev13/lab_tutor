from __future__ import annotations

import torch
import torch.nn as nn


class UnifiedDecayMLP(nn.Module):
    """Combines four decay components into a single output.

    δ_{u,s}(t) = σ(MLP([δ^base, δ^diff, δ^rel, δ^mast]))

    MLP architecture: [4 → D → D/2 → 1] with ReLU and dropout.
    """

    def __init__(self, d: int = 128, dropout: float = 0.1):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(4, d),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d, d // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d // 2, 1),
        )
        for m in self.mlp:
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)

    def forward(
        self,
        delta_base: torch.Tensor,
        delta_diff: torch.Tensor,
        delta_rel: torch.Tensor,
        delta_mast: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            delta_base: [B, S] base retention
            delta_diff: [B, S] difficulty-adjusted retention
            delta_rel:  [B, S] relationally-adjusted retention
            delta_mast: [B, S] mastery-adjusted retention
        Returns:
            [B, S] unified decay value in [0, 1]
        """
        x = torch.stack(
            [delta_base, delta_diff, delta_rel, delta_mast], dim=-1
        )
        return torch.sigmoid(self.mlp(x)).squeeze(-1)
