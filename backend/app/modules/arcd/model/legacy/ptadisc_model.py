"""
PTADisc legacy model architecture.

This is the exact ARCDModel variant used to train the PTADisc checkpoint
(data/checkpoints/ptadisc.pt).  It differs from the current canonical
src.model.training.ARCDModel in that it:
  - Uses a DomainGCN stage that accepts explicit domain embeddings (H_domain)
  - Uses a simplified TemporalModel (no event-type embeddings)
  - Combines response and mastery heads as simple sequential MLPs
  - Supports Platt scaling (platt_a, platt_b read from checkpoint)

Do NOT modify this file without also re-training the PTADisc checkpoint;
any architectural change will break checkpoint loading.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

# ── Building blocks ──────────────────────────────────────────────────


class BasicGCNLayer(nn.Module):
    def __init__(self, in_dim: int, out_dim: int, bias: bool = True):
        super().__init__()
        self.W = nn.Linear(in_dim, out_dim, bias=bias)
        nn.init.xavier_uniform_(self.W.weight)

    @staticmethod
    def _norm_adj(A: torch.Tensor) -> torch.Tensor:
        N = A.size(0)
        A_t = A + torch.eye(N, device=A.device)
        D = A_t.sum(dim=1)
        D_inv = torch.where(D > 0, D.pow(-0.5), torch.zeros_like(D))
        return torch.diag(D_inv) @ A_t @ torch.diag(D_inv)

    def forward(self, H: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        return F.relu(self._norm_adj(A) @ self.W(H))


class AttentionGCNLayer(nn.Module):
    def __init__(
        self,
        in_dim: int,
        out_dim: int,
        n_heads: int = 4,
        neg_slope: float = 0.2,
        dropout: float = 0.1,
    ):
        super().__init__()
        assert out_dim % n_heads == 0
        self.n_heads = n_heads
        self.d_k = out_dim // n_heads
        self.out_dim = out_dim
        self.W = nn.Linear(in_dim, out_dim, bias=False)
        self.a_l = nn.Parameter(torch.empty(n_heads, self.d_k))
        self.a_r = nn.Parameter(torch.empty(n_heads, self.d_k))
        nn.init.xavier_uniform_(self.W.weight)
        nn.init.xavier_uniform_(self.a_l.unsqueeze(0))
        nn.init.xavier_uniform_(self.a_r.unsqueeze(0))
        self.lrelu = nn.LeakyReLU(neg_slope)
        self.drop = nn.Dropout(dropout)

    def forward(self, H: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        N = H.size(0)
        mask = (A + torch.eye(N, device=A.device)) > 0
        Wh = self.W(H).view(N, self.n_heads, self.d_k)
        sl = (Wh * self.a_l).sum(-1)
        sr = (Wh * self.a_r).sum(-1)
        e = self.lrelu(sl.unsqueeze(2) + sr.permute(1, 0).unsqueeze(0))
        e = e.masked_fill(
            ~mask.unsqueeze(1).expand(-1, self.n_heads, -1), float("-inf")
        )
        alpha = self.drop(F.softmax(e, dim=2).nan_to_num(0.0))
        return F.elu(
            torch.bmm(alpha.permute(1, 0, 2), Wh.permute(1, 0, 2))
            .permute(1, 0, 2)
            .reshape(N, self.out_dim)
        )


class BipartiteGCNLayer(nn.Module):
    def __init__(self, in_dim: int, out_dim: int):
        super().__init__()
        self.W = nn.Linear(in_dim, out_dim, bias=True)
        nn.init.xavier_uniform_(self.W.weight)

    def forward(self, H_src: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        WH = self.W(H_src)
        if A.is_sparse:
            deg = torch.sparse.sum(A, dim=1).to_dense().clamp(min=1).unsqueeze(1)
            return F.relu(torch.sparse.mm(A, WH) / deg)
        deg = A.sum(dim=1, keepdim=True).clamp(min=1)
        return F.relu((A / deg) @ WH)


class SparseStudentGCN(nn.Module):
    def __init__(self, d: int, n_students: int, dropout: float = 0.1):
        super().__init__()
        self.emb = nn.Embedding(n_students, d)
        nn.init.normal_(self.emb.weight, std=0.02)
        self.fwd = BipartiteGCNLayer(d, d)
        self.ln = nn.LayerNorm(d)
        self.drop = nn.Dropout(dropout)

    def forward(self, H_q: torch.Tensor, A_uq: torch.Tensor) -> torch.Tensor:
        return self.ln(self.emb.weight + self.drop(self.fwd(H_q, A_uq)))


class BipartiteGCNStack(nn.Module):
    def __init__(self, d: int, n_targets: int, n_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.target_emb = nn.Parameter(torch.randn(n_targets, d) * 0.02)
        self.fwd_layers = nn.ModuleList(
            [BipartiteGCNLayer(d, d) for _ in range(n_layers)]
        )
        self.bwd_layers = nn.ModuleList(
            [BipartiteGCNLayer(d, d) for _ in range(n_layers)]
        )
        self.bn = nn.ModuleList([nn.BatchNorm1d(d) for _ in range(n_layers)])
        self.drop = nn.Dropout(dropout)

    def forward(self, H_src: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        H_tgt = self.target_emb
        for fwd, bwd, bn in zip(
            self.fwd_layers, self.bwd_layers, self.bn, strict=False
        ):
            H_tgt = bn(self.drop(fwd(H_src, A)) + H_tgt)
            H_src = bwd(H_tgt, A.T)
        return H_tgt


class SkillGCN(nn.Module):
    def __init__(self, d_in: int, d: int, dropout: float = 0.1):
        super().__init__()
        self.basic = BasicGCNLayer(d_in, d)
        self.attn = AttentionGCNLayer(d, d, n_heads=4, dropout=dropout)
        self.ln = nn.LayerNorm(d)
        self.proj = nn.Linear(d_in, d) if d_in != d else nn.Identity()

    def forward(self, H: torch.Tensor, A: torch.Tensor) -> torch.Tensor:
        return self.ln(self.attn(self.basic(H, A), A) + self.proj(H))


class DomainGCN(nn.Module):
    def __init__(self, d_dom: int, d: int, n_skills: int, dropout: float = 0.1):
        super().__init__()
        self.basic = BasicGCNLayer(d_dom, d)
        self.attn = AttentionGCNLayer(d, d, n_heads=4, dropout=dropout)
        self.ln = nn.LayerNorm(d)
        self.proj = nn.Linear(d_dom, d) if d_dom != d else nn.Identity()
        self.d2s = BipartiteGCNLayer(d, d)

    def forward(
        self, H_dom: torch.Tensor, A_dom: torch.Tensor, A_ds: torch.Tensor
    ) -> torch.Tensor:
        h = self.attn(self.basic(H_dom, A_dom), A_dom)
        return self.d2s(self.ln(h + self.proj(H_dom)), A_ds)


class MultiRelationalGCN(nn.Module):
    def __init__(
        self,
        d_skill_embed: int,
        d_domain_embed: int,
        d: int,
        n_skills: int,
        n_questions: int,
        n_students: int,
        n_layers: int = 2,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.domain_gcn = DomainGCN(d_domain_embed, d, n_skills, dropout=dropout)
        self.skill_gcn = SkillGCN(d_skill_embed, d, dropout=dropout)
        self.merge_ln = nn.LayerNorm(d)
        self.question_gcn = BipartiteGCNStack(
            d, n_questions, n_layers=n_layers, dropout=dropout
        )
        self.student_gcn = SparseStudentGCN(d, n_students, dropout=dropout)

    def forward(
        self,
        H_s: torch.Tensor,
        H_d: torch.Tensor,
        A_dom: torch.Tensor,
        A_ds: torch.Tensor,
        A_pre: torch.Tensor,
        A_qs: torch.Tensor,
        A_uq: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        h_d2s = self.domain_gcn(H_d, A_dom, A_ds)
        h_s = self.merge_ln(self.skill_gcn(H_s, A_pre) + h_d2s)
        h_q = self.question_gcn(h_s, A_qs)
        h_u = self.student_gcn(h_q, A_uq)
        return {"h_s": h_s, "h_q": h_q, "h_u": h_u}


# ── Temporal model ────────────────────────────────────────────────────


class InteractionEncoder(nn.Module):
    def __init__(self, d: int):
        super().__init__()
        self.W_o = nn.Parameter(torch.ones(1))
        self.W_dt = nn.Parameter(torch.ones(1))
        self.W_proj = nn.Linear(d + 2, d)
        nn.init.xavier_uniform_(self.W_proj.weight)
        self.ln = nn.LayerNorm(d)

    def forward(
        self,
        q_idx: torch.Tensor,
        outcomes: torch.Tensor,
        timestamps: torch.Tensor,
        h_q: torch.Tensor,
    ) -> torch.Tensor:
        q_emb = h_q[q_idx.clamp(0, h_q.size(0) - 1)]
        o_feat = (outcomes.unsqueeze(-1) * self.W_o).clamp(-5, 5)
        t_feat = (torch.log1p(timestamps.abs()).unsqueeze(-1) * self.W_dt).clamp(-5, 5)
        return self.ln(self.W_proj(torch.cat([q_emb, o_feat, t_feat], dim=-1)))


class TemporalMHA(nn.Module):
    def __init__(self, d: int, n_heads: int, dropout: float = 0.1):
        super().__init__()
        self.n_heads = n_heads
        self.d_k = d // n_heads
        self.q = nn.Linear(d, d)
        self.k = nn.Linear(d, d)
        self.v = nn.Linear(d, d)
        self.out = nn.Linear(d, d)
        self.drop = nn.Dropout(dropout)
        self.lam = nn.Parameter(torch.tensor(0.01))

    def forward(
        self,
        x: torch.Tensor,
        timestamps: torch.Tensor,
        decay_values: torch.Tensor,
        pad_mask: torch.Tensor | None,
    ) -> torch.Tensor:
        B, L, D = x.shape
        H = self.n_heads
        Q = self.q(x).view(B, L, H, self.d_k).transpose(1, 2)
        K = self.k(x).view(B, L, H, self.d_k).transpose(1, 2)
        V = self.v(x).view(B, L, H, self.d_k).transpose(1, 2)
        scores = (Q @ K.transpose(-2, -1)) / math.sqrt(self.d_k)
        t_diff = (timestamps.unsqueeze(2) - timestamps.unsqueeze(1)).abs()
        scores = scores - self.lam.abs() * torch.log1p(
            t_diff / max(t_diff.max().item(), 1)
        ).unsqueeze(1)
        causal = torch.triu(
            torch.ones(L, L, dtype=torch.bool, device=x.device), diagonal=1
        )
        scores = scores.masked_fill(causal.unsqueeze(0).unsqueeze(0), float("-inf"))
        if pad_mask is not None:
            scores = scores.masked_fill(
                ~pad_mask.unsqueeze(1).unsqueeze(2), float("-inf")
            )
        out = F.softmax(scores, dim=-1).nan_to_num(0.0) @ V
        return self.out(out.transpose(1, 2).reshape(B, L, D))


class TBlock(nn.Module):
    def __init__(self, d: int, n_heads: int, d_ff: int, dropout: float = 0.1):
        super().__init__()
        self.attn = TemporalMHA(d, n_heads, dropout)
        self.ff = nn.Sequential(
            nn.Linear(d, d_ff), nn.GELU(), nn.Dropout(dropout), nn.Linear(d_ff, d)
        )
        self.ln1 = nn.LayerNorm(d)
        self.ln2 = nn.LayerNorm(d)
        self.drop = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        timestamps: torch.Tensor,
        dv: torch.Tensor,
        pm: torch.Tensor | None,
    ) -> torch.Tensor:
        x = x + self.drop(self.attn(self.ln1(x), timestamps, dv, pm))
        return x + self.drop(self.ff(self.ln2(x)))


class TemporalModel(nn.Module):
    def __init__(
        self, d: int, n_heads: int, d_ff: int, n_layers: int, dropout: float = 0.1
    ):
        super().__init__()
        self.enc = InteractionEncoder(d)
        self.blocks = nn.ModuleList(
            [TBlock(d, n_heads, d_ff, dropout) for _ in range(n_layers)]
        )
        self.ln_out = nn.LayerNorm(d)

    def forward(
        self,
        q_idx: torch.Tensor,
        outcomes: torch.Tensor,
        timestamps: torch.Tensor,
        dv: torch.Tensor,
        pm: torch.Tensor,
        h_q: torch.Tensor,
    ) -> torch.Tensor:
        x = self.enc(q_idx, outcomes, timestamps, h_q)
        for b in self.blocks:
            x = b(x, timestamps, dv, pm)
        x = self.ln_out(x)
        lengths = pm.sum(dim=1).clamp(min=1) - 1
        return x[torch.arange(x.size(0), device=x.device), lengths]


# ── Full PTADisc ARCD Model ───────────────────────────────────────────


class ARCDModelPTADisc(nn.Module):
    """PTADisc-specific ARCD model.

    Checkpoint key: data/checkpoints/ptadisc.pt
    Hyperparams are stored in checkpoint["model_hparams"].
    """

    def __init__(
        self,
        d_skill_embed: int,
        d_domain_embed: int,
        d: int,
        n_skills: int,
        n_questions: int,
        n_students: int,
        n_gcn_layers: int = 3,
        n_heads: int = 4,
        d_ff: int = 256,
        n_attn_layers: int = 2,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.d = d
        self.n_skills = n_skills
        self.gcn = MultiRelationalGCN(
            d_skill_embed,
            d_domain_embed,
            d,
            n_skills,
            n_questions,
            n_students,
            n_layers=n_gcn_layers,
            dropout=dropout,
        )
        self.temporal = TemporalModel(d, n_heads, d_ff, n_attn_layers, dropout)
        self.response_head = nn.Sequential(
            nn.Linear(d * 3, d * 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d * 2, d),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d, 1),
        )
        self.mastery_head = nn.Sequential(
            nn.Linear(d, d),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d, n_skills),
            nn.Sigmoid(),
        )

    def run_gcn(self, gd: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        out = self.gcn(
            gd["H_skill"],
            gd["H_domain"],
            gd["A_domain"],
            gd["A_ds"],
            gd["A_skill"],
            gd["A_qs"],
            gd["A_uq"],
        )
        return {"h_q": out["h_q"], "h_s": out["h_s"]}

    def forward(
        self,
        gcn_out: dict[str, torch.Tensor],
        q_idx: torch.Tensor,
        outcomes: torch.Tensor,
        timestamps: torch.Tensor,
        dv: torch.Tensor,
        pm: torch.Tensor,
        tq_idx: torch.Tensor,
        A_qs: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        h_q, h_s = gcn_out["h_q"], gcn_out["h_s"]
        h_u = self.temporal(q_idx, outcomes, timestamps, dv, pm, h_q)
        tq = h_q[tq_idx.clamp(0, h_q.size(0) - 1)]
        sw = A_qs[tq_idx.clamp(0, A_qs.size(0) - 1)]
        sw = sw / sw.sum(-1, keepdim=True).clamp(min=1e-8)
        ts = sw @ h_s
        logit = self.response_head(torch.cat([h_u, tq, ts], dim=-1)).squeeze(-1)
        mastery = self.mastery_head(h_u)
        return {"response_logit": logit, "mastery": mastery}
