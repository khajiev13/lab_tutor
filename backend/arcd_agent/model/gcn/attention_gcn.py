from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class AttentionGCNLayer(nn.Module):
    """GAT-style multi-head attention graph convolution.

    alpha_ij = softmax_j(LeakyReLU(a_l^T Wh_i + a_r^T Wh_j))
    h_i^(l) = ELU(sum_j alpha_ij * W h_j)
    """

    def __init__(
        self,
        in_dim: int,
        out_dim: int,
        n_heads: int = 4,
        negative_slope: float = 0.2,
        dropout: float = 0.1,
    ):
        super().__init__()
        assert out_dim % n_heads == 0, "out_dim must be divisible by n_heads"
        self.n_heads = n_heads
        self.d_k = out_dim // n_heads
        self.out_dim = out_dim

        self.W = nn.Linear(in_dim, out_dim, bias=False)
        nn.init.xavier_uniform_(self.W.weight)

        self.a_l = nn.Parameter(torch.empty(n_heads, self.d_k))
        self.a_r = nn.Parameter(torch.empty(n_heads, self.d_k))
        nn.init.xavier_uniform_(self.a_l.unsqueeze(0))
        nn.init.xavier_uniform_(self.a_r.unsqueeze(0))

        self.leaky_relu = nn.LeakyReLU(negative_slope)
        self.dropout = nn.Dropout(dropout)

    def forward(self, H: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        N = H.size(0)
        A_tilde = A + torch.eye(N, device=A.device)
        mask = A_tilde > 0

        Wh = self.W(H).view(N, self.n_heads, self.d_k)

        score_l = (Wh * self.a_l).sum(dim=-1)  # [N, K]
        score_r = (Wh * self.a_r).sum(dim=-1)  # [N, K]
        e = score_l.unsqueeze(2) + score_r.permute(1, 0).unsqueeze(0)  # [N, K, N]
        e = self.leaky_relu(e)

        mask_k = mask.unsqueeze(1).expand(-1, self.n_heads, -1)
        e = e.masked_fill(~mask_k, float("-inf"))
        alpha = F.softmax(e, dim=2)
        alpha = self.dropout(alpha)

        out = torch.bmm(alpha.permute(1, 0, 2), Wh.permute(1, 0, 2))
        out = out.permute(1, 0, 2).reshape(N, self.out_dim)
        return F.elu(out)
