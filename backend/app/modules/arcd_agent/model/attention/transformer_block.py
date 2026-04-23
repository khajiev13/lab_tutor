from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from .temporal_attention import TemporalMultiHeadAttention


class FeedForward(nn.Module):
    """Position-wise FFN with GELU activation and expansion."""

    def __init__(self, d: int, d_ff: int, dropout: float = 0.1):
        super().__init__()
        self.w1 = nn.Linear(d, d_ff)
        self.w2 = nn.Linear(d_ff, d)
        self.dropout = nn.Dropout(dropout)
        nn.init.xavier_uniform_(self.w1.weight)
        nn.init.xavier_uniform_(self.w2.weight)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.w2(self.dropout(F.gelu(self.w1(x))))


class TransformerBlock(nn.Module):
    """Pre-norm Transformer block: TemporalMHA + FFN with residual connections."""

    def __init__(
        self,
        d: int,
        n_heads: int = 8,
        d_ff: int = 512,
        lambda_time_init: float = 0.01,
        lambda_decay: float = 0.1,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.ln1 = nn.LayerNorm(d)
        self.attn = TemporalMultiHeadAttention(
            d,
            n_heads=n_heads,
            lambda_time_init=lambda_time_init,
            lambda_decay=lambda_decay,
            dropout=dropout,
        )
        self.ln2 = nn.LayerNorm(d)
        self.ffn = FeedForward(d, d_ff, dropout=dropout)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        X: torch.Tensor,
        timestamps: torch.Tensor,
        decay_values: torch.Tensor,
        pad_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        X = X + self.dropout(self.attn(self.ln1(X), timestamps, decay_values, pad_mask))
        X = X + self.dropout(self.ffn(self.ln2(X)))
        return X


class TemporalAttentionModel(nn.Module):
    """Full temporal encoder: event encoding -> Transformer blocks -> h_u(t)."""

    def __init__(
        self,
        d: int = 128,
        d_type: int = 16,
        n_heads: int = 8,
        d_ff: int = 512,
        n_layers: int = 4,
        dropout: float = 0.1,
        lambda_time_init: float = 0.01,
        lambda_decay: float = 0.1,
    ):
        super().__init__()
        from .temporal_attention import MultiEventInteractionEncoder

        self.encoder = MultiEventInteractionEncoder(d=d, d_type=d_type)
        self.blocks = nn.ModuleList(
            [
                TransformerBlock(
                    d=d,
                    n_heads=n_heads,
                    d_ff=d_ff,
                    lambda_time_init=lambda_time_init,
                    lambda_decay=lambda_decay,
                    dropout=dropout,
                )
                for _ in range(n_layers)
            ]
        )
        self.final_ln = nn.LayerNorm(d)

    def forward(
        self,
        event_types: torch.Tensor,
        entity_indices: torch.Tensor,
        outcomes: torch.Tensor,
        timestamps: torch.Tensor,
        decay_values: torch.Tensor,
        pad_mask: torch.Tensor,
        h_qa: torch.Tensor,
        h_v: torch.Tensor,
        h_r: torch.Tensor,
    ) -> torch.Tensor:
        last_ts = timestamps.max(dim=1, keepdim=True).values
        delta_ts = (last_ts - timestamps).clamp(min=0)

        X = self.encoder(
            event_types, entity_indices, outcomes, delta_ts, h_qa, h_v, h_r
        )

        for block in self.blocks:
            X = block(X, timestamps, decay_values, pad_mask)

        X = self.final_ln(X)

        actual_lens = pad_mask.sum(dim=1).long()
        last_idx = (actual_lens - 1).clamp(min=0)
        batch_idx = torch.arange(X.size(0), device=X.device)
        return X[batch_idx, last_idx]
