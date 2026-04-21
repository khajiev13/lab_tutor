from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class BasicGCNLayer(nn.Module):
    """Graph convolution with symmetric normalized adjacency.

    A_hat = D^{-1/2} (A + I) D^{-1/2}
    H^(l) = sigma(A_hat @ H^(l-1) @ W^(l))
    """

    def __init__(self, in_dim: int, out_dim: int, bias: bool = True):
        super().__init__()
        self.W = nn.Linear(in_dim, out_dim, bias=bias)
        nn.init.xavier_uniform_(self.W.weight)

    @staticmethod
    def _norm_adj(A: torch.Tensor) -> torch.Tensor:
        N = A.size(0)
        A_tilde = A + torch.eye(N, device=A.device)
        D = A_tilde.sum(dim=1)
        D_inv_sqrt = torch.where(D > 0, D.pow(-0.5), torch.zeros_like(D))
        D_mat = torch.diag(D_inv_sqrt)
        return D_mat @ A_tilde @ D_mat

    def forward(self, H: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        A_hat = self._norm_adj(A)
        return F.relu(A_hat @ self.W(H))
