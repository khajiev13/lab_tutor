from __future__ import annotations

import torch
import torch.nn as nn


class PerformanceHead(nn.Module):
    """Predicts correctness probability for a specific question.

    P(u, q, t) = σ(MLP([e_u ∥ e_q ∥ h_u(t) ∥ δ̄_q]))

    MLP architecture: (3D+1) → 256 → 128 → 1, ReLU + dropout.
    """

    def __init__(self, d: int = 128, dropout: float = 0.1):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(3 * d + 1, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 1),
        )
        for m in self.mlp:
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)

    def forward(
        self,
        e_u: torch.Tensor,
        e_q: torch.Tensor,
        h_u_t: torch.Tensor,
        decay_bar_q: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            e_u:         [B, D] student embeddings (GCN-refined)
            e_q:         [B, D] question embeddings (GCN-refined)
            h_u_t:       [B, D] temporal context vector from attention
            decay_bar_q: [B] mean decay across skills tested by question q
        Returns:
            [B] performance probability in [0, 1]
        """
        x = torch.cat([e_u, e_q, h_u_t, decay_bar_q.unsqueeze(-1)], dim=-1)
        return torch.sigmoid(self.mlp(x)).squeeze(-1)
