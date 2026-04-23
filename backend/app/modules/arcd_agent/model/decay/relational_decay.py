from __future__ import annotations

import torch
import torch.nn as nn


class RelationalDecay(nn.Module):
    """Forgetting cascades through the prerequisite graph.

    δ^rel_{u,s} = δ^diff_{u,s} · ∏_{s' ∈ parents(s)} (w_p + (1 - w_p) · δ_{s'})

    Computed in topological order so parents are always resolved before children.
    """

    def __init__(self, adj_matrix: torch.Tensor):
        super().__init__()
        self.register_buffer("adj", (adj_matrix > 0).float())
        self.register_buffer("topo_order", self._topological_sort(adj_matrix))
        self.w_p_logit = nn.Parameter(torch.tensor(0.0))

    @staticmethod
    def _topological_sort(adj: torch.Tensor) -> torch.Tensor:
        """Kahn's algorithm for topological sorting."""
        S = adj.size(0)
        in_deg = (adj > 0).float().sum(dim=0).long()
        queue = (in_deg == 0).nonzero(as_tuple=True)[0].tolist()
        order: list[int] = []
        remaining = in_deg.clone()
        while queue:
            node = queue.pop(0)
            order.append(node)
            for j in range(S):
                if adj[node, j] > 0:
                    remaining[j] -= 1
                    if remaining[j] == 0:
                        queue.append(j)
        if len(order) != S:
            for i in range(S):
                if i not in order:
                    order.append(i)
        return torch.tensor(order, dtype=torch.long)

    def forward(self, delta_diff: torch.Tensor) -> torch.Tensor:
        """
        Args:
            delta_diff: [B, S] difficulty-adjusted retention
        Returns:
            [B, S] relationally-adjusted retention
        """
        B, S = delta_diff.shape
        w_p = torch.sigmoid(self.w_p_logit)
        delta_rel = delta_diff.clone()

        for s in self.topo_order.tolist():
            parent_mask = self.adj[:, s]
            if parent_mask.sum() == 0:
                continue
            parent_idx = parent_mask.nonzero(as_tuple=True)[0]
            parent_decays = delta_rel[:, parent_idx]
            factors = w_p + (1 - w_p) * parent_decays
            delta_rel[:, s] = delta_diff[:, s] * factors.prod(dim=1)

        return delta_rel
