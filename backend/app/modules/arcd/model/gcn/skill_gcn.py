from __future__ import annotations

import torch
import torch.nn as nn

from .attention_gcn import AttentionGCNLayer
from .basic_gcn import BasicGCNLayer


class SkillGCN(nn.Module):
    """Stage 1 of the 5-stage multi-relational GCN.

    Propagates prerequisite information across skills:
        BasicGCN(d_in → d_hidden) → Dropout → AttentionGCN(d_hidden → d_out)
    with a residual connection and layer norm.
    """

    def __init__(
        self,
        d_in: int,
        d_hidden: int,
        d_out: int,
        n_heads: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.gcn1 = BasicGCNLayer(d_in, d_hidden)
        self.gcn2 = AttentionGCNLayer(d_hidden, d_out, n_heads=n_heads, dropout=dropout)
        self.dropout = nn.Dropout(dropout)
        self.layer_norm = nn.LayerNorm(d_out)
        self.use_residual = d_in == d_out
        self.residual_proj = (
            None if self.use_residual else nn.Linear(d_in, d_out, bias=False)
        )

    def forward(self, H: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        residual = H if self.use_residual else self.residual_proj(H)
        x = self.gcn1(H, A)
        x = self.dropout(x)
        x = self.gcn2(x, A)
        return self.layer_norm(x + residual)
