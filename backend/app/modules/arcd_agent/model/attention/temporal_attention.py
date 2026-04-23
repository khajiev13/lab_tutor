from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class MultiEventInteractionEncoder(nn.Module):
    """Encodes heterogeneous learning events into a unified dense representation.

    Each event is described by:
        - type_j:       0 = question, 1 = video, 2 = reading
        - entity_idx_j: index into h_qa / h_v / h_r
        - outcome_j:    correctness (0/1) or completion fraction (0.0–1.0)
        - delta_t_j:    seconds since this event until the target interaction
    """

    def __init__(self, d: int, d_type: int = 16, n_event_types: int = 3):
        super().__init__()
        self.d = d
        self.d_type = d_type

        self.E_type = nn.Embedding(n_event_types, d_type)
        nn.init.xavier_uniform_(self.E_type.weight)

        self.W_o = nn.Parameter(torch.ones(1))
        self.W_delta = nn.Parameter(torch.ones(1))

        self.W_proj = nn.Linear(d + d_type + 2, d)
        nn.init.xavier_uniform_(self.W_proj.weight)

        self.layer_norm = nn.LayerNorm(d)

    def forward(
        self,
        event_types: torch.Tensor,
        entity_indices: torch.Tensor,
        outcomes: torch.Tensor,
        delta_ts: torch.Tensor,
        h_qa: torch.Tensor,
        h_v: torch.Tensor,
        h_r: torch.Tensor,
    ) -> torch.Tensor:
        B, L = event_types.shape
        max_entities = max(h_qa.size(0), h_v.size(0), h_r.size(0))

        def _pad(h: torch.Tensor) -> torch.Tensor:
            if h.size(0) < max_entities:
                pad = torch.zeros(max_entities - h.size(0), h.size(1), device=h.device)
                return torch.cat([h, pad], dim=0)
            return h

        entity_table = torch.stack([_pad(h_qa), _pad(h_v), _pad(h_r)], dim=0)

        type_flat = event_types.reshape(-1)
        idx_flat = entity_indices.reshape(-1)
        emb = entity_table[type_flat, idx_flat].reshape(B, L, self.d)

        type_emb = self.E_type(event_types)
        outcome_feat = (self.W_o * outcomes).unsqueeze(-1)
        delta_feat = (self.W_delta * delta_ts).unsqueeze(-1)

        concat = torch.cat([emb, type_emb, outcome_feat, delta_feat], dim=-1)
        return self.layer_norm(self.W_proj(concat))


class TemporalMultiHeadAttention(nn.Module):
    """Multi-head attention with temporal distance and forgetting-decay penalties.

    score(T, i) = (q_T . k_i) / sqrt(d_k)
                  - lambda_time  * |t_T - t_i|
                  - lambda_decay * decay_i
    """

    def __init__(
        self,
        d: int,
        n_heads: int = 8,
        lambda_time_init: float = 0.01,
        lambda_decay: float = 0.1,
        dropout: float = 0.1,
    ):
        super().__init__()
        assert d % n_heads == 0
        self.d = d
        self.n_heads = n_heads
        self.d_k = d // n_heads

        self.W_Q = nn.Linear(d, d, bias=False)
        self.W_K = nn.Linear(d, d, bias=False)
        self.W_V = nn.Linear(d, d, bias=False)
        self.W_out = nn.Linear(d, d)

        for w in (self.W_Q, self.W_K, self.W_V, self.W_out):
            nn.init.xavier_uniform_(w.weight)

        self.lambda_time = nn.Parameter(torch.tensor(lambda_time_init))
        self.lambda_decay = lambda_decay

        self.attn_dropout = nn.Dropout(dropout)
        self.out_dropout = nn.Dropout(dropout)

    def forward(
        self,
        X: torch.Tensor,
        timestamps: torch.Tensor,
        decay_values: torch.Tensor,
        pad_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        B, L, _ = X.shape
        H, d_k = self.n_heads, self.d_k

        Q = self.W_Q(X).view(B, L, H, d_k).transpose(1, 2)
        K = self.W_K(X).view(B, L, H, d_k).transpose(1, 2)
        V = self.W_V(X).view(B, L, H, d_k).transpose(1, 2)

        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(d_k)

        t = timestamps.unsqueeze(-1)
        time_penalty = self.lambda_time * (t - t.transpose(-2, -1)).abs().unsqueeze(1)
        decay_penalty = self.lambda_decay * decay_values.unsqueeze(-2).unsqueeze(1)
        scores = scores - time_penalty - decay_penalty

        causal = torch.triu(
            torch.ones(L, L, device=X.device, dtype=torch.bool), diagonal=1
        )
        scores = scores.masked_fill(causal.unsqueeze(0).unsqueeze(0), float("-inf"))

        if pad_mask is not None:
            key_mask = (~pad_mask).unsqueeze(1).unsqueeze(2)
            scores = scores.masked_fill(key_mask, float("-inf"))

        alpha = F.softmax(scores, dim=-1)
        alpha = self.attn_dropout(alpha)

        context = torch.matmul(alpha, V)
        context = context.transpose(1, 2).reshape(B, L, self.d)
        return self.out_dropout(self.W_out(context))
