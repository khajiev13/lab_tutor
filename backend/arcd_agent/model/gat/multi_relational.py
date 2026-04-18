from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from .attention_gcn import AttentionGCNLayer
from .basic_gcn import BasicGCNLayer


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


class HomoGCNStack(nn.Module):
    """L_gat graph attention layers with BatchNorm and residual.

    When use_gat=True (default), uses multi-head GAT layers (paper Eq. 1-2).
    """

    def __init__(
        self,
        d_in: int,
        d_hidden: int,
        d_out: int,
        n_layers: int = 3,
        n_heads: int = 4,
        dropout: float = 0.1,
        use_gat: bool = True,
    ):
        super().__init__()
        dims = [d_in] + [d_hidden] * (n_layers - 1) + [d_out]
        self.layers = nn.ModuleList()
        self.bns = nn.ModuleList()
        self.use_gat = use_gat
        for i in range(n_layers):
            if use_gat:
                self.layers.append(
                    AttentionGCNLayer(
                        dims[i], dims[i + 1], n_heads=n_heads, dropout=dropout
                    )
                )
            else:
                self.layers.append(BasicGCNLayer(dims[i], dims[i + 1]))
            self.bns.append(nn.BatchNorm1d(dims[i + 1]))
        self.dropout = nn.Dropout(dropout)
        self.proj = nn.Linear(d_in, d_out, bias=False) if d_in != d_out else None

    def forward(self, H: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        residual = self.proj(H) if self.proj else H
        x = H
        for i, (layer, bn) in enumerate(zip(self.layers, self.bns, strict=False)):
            x = layer(x, A)
            x = bn(x)
            if i < len(self.layers) - 1:
                if not self.use_gat:
                    x = F.relu(x)
                x = self.dropout(x)
        return F.elu(x + residual) if self.use_gat else F.relu(x + residual)


class SkillGATStage(nn.Module):
    """Stage 1: Skill GAT over prerequisite graph (paper Eq. 1-2)."""

    def __init__(
        self, d_embed, d_hidden, d_out, n_layers=3, n_heads=4, dropout=0.1, use_gat=True
    ):
        super().__init__()
        self.gat = HomoGCNStack(
            d_embed, d_hidden, d_out, n_layers, n_heads, dropout, use_gat
        )

    def forward(self, H_raw, A_pre):
        return self.gat(H_raw, A_pre)


class QuestionGATStage(nn.Module):
    """Stage 2: Question-Skill bipartite GCN (edges A_qs)."""

    def __init__(self, n_questions, d, n_layers=3, dropout=0.1):
        super().__init__()
        self.q_embed = nn.Embedding(n_questions, d)
        nn.init.xavier_uniform_(self.q_embed.weight)
        self.embed_drop = nn.Dropout(dropout)
        self.gcn = BipartiteGCNStack(d, d, d, d, n_layers, dropout)

    def forward(self, h_s, A_qs):
        return self.gcn(h_s, self.embed_drop(self.q_embed.weight), A_qs)


class VideoGATStage(nn.Module):
    """Stage 3: Video-Skill bipartite GCN (edges A_vs)."""

    def __init__(self, n_videos, d, n_layers=3, dropout=0.1):
        super().__init__()
        self.n_videos = n_videos
        self.v_embed = nn.Embedding(n_videos, d)
        nn.init.xavier_uniform_(self.v_embed.weight)
        self.embed_drop = nn.Dropout(dropout)
        self.gcn = (
            BipartiteGCNStack(d, d, d, d, n_layers, dropout) if n_videos > 1 else None
        )

    def forward(self, h_s, A_vs):
        h = self.embed_drop(self.v_embed.weight)
        if self.gcn is not None:
            return self.gcn(h_s, h, A_vs)
        return h


class ReadingGATStage(nn.Module):
    """Stage 4: Reading-Skill bipartite GCN (edges A_rs)."""

    def __init__(self, n_readings, d, n_layers=3, dropout=0.1):
        super().__init__()
        self.n_readings = n_readings
        self.r_embed = nn.Embedding(n_readings, d)
        nn.init.xavier_uniform_(self.r_embed.weight)
        self.embed_drop = nn.Dropout(dropout)
        self.gcn = (
            BipartiteGCNStack(d, d, d, d, n_layers, dropout) if n_readings > 1 else None
        )

    def forward(self, h_s, A_rs):
        h = self.embed_drop(self.r_embed.weight)
        if self.gcn is not None:
            return self.gcn(h_s, h, A_rs)
        return h


class StudentGATStage(nn.Module):
    """Stage 5: Student-Question bipartite GCN (edges A_uq)."""

    def __init__(self, n_students, d, n_layers=3, dropout=0.1):
        super().__init__()
        self.u_embed = nn.Embedding(n_students, d)
        nn.init.xavier_uniform_(self.u_embed.weight)
        self.embed_drop = nn.Dropout(dropout)
        self.gcn = BipartiteGCNStack(d, d, d, d, n_layers, dropout)

    def forward(self, h_qa, A_uq):
        return self.gcn(h_qa, self.embed_drop(self.u_embed.weight), A_uq)


class MultiRelationalGAT(nn.Module):
    """5-stage multi-relational GAT over the knowledge graph (paper Fig. 3).

    Stage 1 (Skill GAT):    h_s  — prerequisite-aware skill vectors
    Stage 2 (Question GCN): h_qa — skill-aware question vectors  (entity_table[0])
    Stage 3 (Video GCN):    h_v  — skill-aware video vectors     (entity_table[1])
    Stage 4 (Reading GCN):  h_r  — skill-aware reading vectors   (entity_table[2])
    Stage 5 (Student GCN):  h_u  — student vectors with question context
    """

    def __init__(
        self,
        d_skill_embed: int,
        d: int,
        n_layers: int,
        n_questions: int,
        n_videos: int,
        n_readings: int,
        n_students: int,
        n_heads: int = 4,
        dropout: float = 0.1,
        use_gat: bool = True,
    ):
        super().__init__()
        self.stage1_skill = SkillGATStage(
            d_skill_embed, d, d, n_layers, n_heads, dropout, use_gat
        )
        self.stage2_question = QuestionGATStage(n_questions, d, n_layers, dropout)
        self.stage3_video = VideoGATStage(n_videos, d, n_layers, dropout)
        self.stage4_reading = ReadingGATStage(n_readings, d, n_layers, dropout)
        self.stage5_student = StudentGATStage(n_students, d, n_layers, dropout)

    def forward(self, H_skill_raw, A_pre, A_qs, A_vs, A_rs, A_uq):
        h_s = self.stage1_skill(H_skill_raw, A_pre)
        h_qa = self.stage2_question(h_s, A_qs)
        h_v = self.stage3_video(h_s, A_vs)
        h_r = self.stage4_reading(h_s, A_rs)
        h_u = self.stage5_student(h_qa, A_uq)
        return {"h_s": h_s, "h_qa": h_qa, "h_v": h_v, "h_r": h_r, "h_u": h_u}


# ---------------------------------------------------------------------------
# Back-compat aliases (old checkpoint state_dict used "GCN" stage names)
# ---------------------------------------------------------------------------
SkillGCNStage = SkillGATStage
QuestionGCNStage = QuestionGATStage
VideoGCNStage = VideoGATStage
ReadingGCNStage = ReadingGATStage
StudentGCNStage = StudentGATStage
MultiRelationalGCN = MultiRelationalGAT
