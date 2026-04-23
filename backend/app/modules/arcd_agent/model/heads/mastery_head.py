from __future__ import annotations

import torch
import torch.nn as nn


class MasteryHead(nn.Module):
    """Predicts per-skill mastery for each student.

    m_{u,s}(t) = σ(MLP([e_u ∥ e_s ∥ δ_{u,s}(t)]))

    MLP architecture: (2D+1) → 256 → 128 → 1, ReLU + dropout.
    Applied to every (student, skill) pair to produce m_u(t) ∈ [0,1]^S.
    """

    def __init__(self, d: int = 128, dropout: float = 0.1):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(2 * d + 1, 256),
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
        e_s: torch.Tensor,
        decay: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            e_u:   [B, D] student embeddings (GCN-refined)
            e_s:   [S, D] skill embeddings (GCN-refined)
            decay: [B, S] unified decay values from the decay cascade
        Returns:
            [B, S] mastery predictions in [0, 1]
        """
        B = e_u.size(0)
        S = e_s.size(0)

        e_u_exp = e_u.unsqueeze(1).expand(B, S, -1)
        e_s_exp = e_s.unsqueeze(0).expand(B, S, -1)

        x = torch.cat([e_u_exp, e_s_exp, decay.unsqueeze(-1)], dim=-1)
        return torch.sigmoid(self.mlp(x)).squeeze(-1)
