from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class BipartiteGCNLayer(nn.Module):
    """Single bipartite message-passing layer.

    Propagates from source to target via row-normalized adjacency:
        H_target_new = sigma(A_norm @ H_source @ W)
    """

    def __init__(self, d_source: int, d_out: int, bias: bool = True):
        super().__init__()
        self.W = nn.Linear(d_source, d_out, bias=bias)
        nn.init.xavier_uniform_(self.W.weight)

    @staticmethod
    def _row_norm(A: torch.Tensor) -> torch.Tensor:
        # Dense path
        if not A.is_sparse:
            row_sum = A.sum(dim=1, keepdim=True).clamp(min=1e-8)
            return A / row_sum
        # Sparse COO: row-normalize in value space (clamp works on dense row sums)
        A_co = A.coalesce()
        if A_co.layout == torch.sparse_coo:
            n_rows = A.size(0)
            indices = A_co.indices()
            values = A_co.values()
            row = indices[0]
            row_sum = torch.zeros(n_rows, dtype=values.dtype, device=A.device)
            row_sum.index_add_(0, row, values)
            row_sum = row_sum.clamp(min=1e-8)
            inv = (1.0 / row_sum)[row]
            new_vals = values * inv
            return torch.sparse_coo_tensor(
                indices, new_vals, A.size(), device=A.device, dtype=A.dtype
            ).coalesce()
        # Fallback: densify (rare layouts)
        Ad = A.to_dense()
        row_sum = Ad.sum(dim=1, keepdim=True).clamp(min=1e-8)
        return Ad / row_sum

    def forward(self, H_source: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        A_norm = self._row_norm(A)
        return self.W(A_norm @ H_source)


class BipartiteGCNStack(nn.Module):
    """L_gcn layers of alternating bipartite message passing with BatchNorm.

    Odd layers:  target <- source
    Even layers: source <- target
    """

    def __init__(
        self,
        d_source: int,
        d_target_in: int,
        d_hidden: int,
        d_out: int,
        n_layers: int = 3,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.n_layers = n_layers
        self.fwd_layers = nn.ModuleList()
        self.bwd_layers = nn.ModuleList()
        self.fwd_bns = nn.ModuleList()
        self.bwd_bns = nn.ModuleList()

        self.fwd_layers.append(BipartiteGCNLayer(d_source, d_hidden))
        self.fwd_bns.append(nn.BatchNorm1d(d_hidden))

        for i in range(1, n_layers):
            if i % 2 == 1:
                self.bwd_layers.append(BipartiteGCNLayer(d_hidden, d_hidden))
                self.bwd_bns.append(nn.BatchNorm1d(d_hidden))
            else:
                self.fwd_layers.append(BipartiteGCNLayer(d_hidden, d_hidden))
                self.fwd_bns.append(nn.BatchNorm1d(d_hidden))

        self.out_proj = (
            nn.Linear(d_hidden, d_out) if d_hidden != d_out else nn.Identity()
        )
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        H_source: torch.Tensor,
        H_target: torch.Tensor,
        A: torch.Tensor,
    ) -> torch.Tensor:
        A_T = A.t()
        fwd_idx, bwd_idx = 0, 0
        h_src, h_tgt = H_source, H_target

        for i in range(self.n_layers):
            if i % 2 == 0:
                h_tgt = self.fwd_layers[fwd_idx](h_src, A)
                h_tgt = self.fwd_bns[fwd_idx](h_tgt)
                h_tgt = F.relu(h_tgt)
                h_tgt = self.dropout(h_tgt)
                fwd_idx += 1
            else:
                h_src = self.bwd_layers[bwd_idx](h_tgt, A_T)
                h_src = self.bwd_bns[bwd_idx](h_src)
                h_src = F.relu(h_src)
                h_src = self.dropout(h_src)
                bwd_idx += 1

        return self.out_proj(h_tgt)
