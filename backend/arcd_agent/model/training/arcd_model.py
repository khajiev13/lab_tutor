from __future__ import annotations

import torch
import torch.nn as nn

from ..attention import TemporalAttentionModel
from ..decay import (
    BaseDecay,
    DifficultyDecay,
    MasteryDecay,
    RelationalDecay,
    UnifiedDecayMLP,
)
from ..gat import MultiRelationalGAT
from ..heads import MasteryHead, PerformanceHead


class ARCDModel(nn.Module):
    """Full ARCD model: GAT -> Temporal Attention + Decay -> Prediction Heads.

    Architecture (paper Fig. 3):
        1. 5-stage GAT produces h_s, h_qa, h_v, h_r, h_u
        2. Temporal Multi-Head Attention (Eq. 5) produces h_u(t)
        3. 4-stage Decay Cascade (Eq. 6-11) produces δ_{u,s} and δ̄_q
        4. Performance Head (Eq. 13): P(u,q,t) = σ(MLP(e_u ∥ e_q ∥ h_u(t) ∥ δ̄_q))
        5. Mastery Head (Eq. 12): m_{u,s}(t) = σ(MLP(e_u ∥ e_s ∥ δ_{u,s}))

    Optimizations:
        - GAT caching: run_gcn_cached() + forward(gat_cache=...) for 2-3x speedup
        - Decay cascade: learnable forgetting pipeline wired into prediction heads
    """

    def __init__(
        self,
        d_skill_embed: int,
        d: int,
        n_gat_layers: int,
        n_questions: int,
        n_videos: int,
        n_readings: int,
        n_students: int,
        n_skills: int,
        n_heads_gat: int = 4,
        d_type: int = 16,
        n_heads: int = 8,
        d_ff: int = 512,
        n_attn_layers: int = 4,
        dropout: float = 0.1,
        use_gat: bool = True,
        student_emb_drop_p: float = 0.0,
        unk_student_idx: int | None = None,
    ):
        super().__init__()
        self.n_skills = n_skills
        # Reserved slot in the student embedding tables for cold-start /
        # out-of-vocabulary students.  Convention: last row of the table
        # (i.e. n_students - 1).  See arcd_train.py where n_students is set to
        # num_real_students + 1 so the UNK row is genuinely a fresh slot, not
        # piggy-backed on real student 0 (which was the v3 contamination bug).
        self.unk_student_idx = (
            unk_student_idx if unk_student_idx is not None else n_students - 1
        )

        self.gat = MultiRelationalGAT(
            d_skill_embed=d_skill_embed,
            d=d,
            n_layers=n_gat_layers,
            n_questions=n_questions,
            n_videos=n_videos,
            n_readings=n_readings,
            n_students=n_students,
            n_heads=n_heads_gat,
            dropout=dropout,
            use_gat=use_gat,
        )

        self.temporal = TemporalAttentionModel(
            d=d,
            d_type=d_type,
            n_heads=n_heads,
            d_ff=d_ff,
            n_layers=n_attn_layers,
            dropout=dropout,
        )

        self.performance_head = PerformanceHead(d=d, dropout=dropout)
        self.mastery_head = MasteryHead(d=d, dropout=dropout)

        # Decay cascade (paper Eq. 6-11)
        self.base_decay = BaseDecay(n_students, n_skills)
        self.diff_decay = DifficultyDecay(n_skills)
        # RelationalDecay is installed lazily via set_prerequisite_graph() so that
        # model construction does not require A_pre (which is only available after
        # the graph tensors are built).  Until wired, d_rel = d_diff (pass-through).
        self.rel_decay: RelationalDecay | None = None
        self.mast_decay = MasteryDecay()
        self.unified_decay = UnifiedDecayMLP(d=d, dropout=dropout)

        # Per-question difficulty bias (IRT b_q): allows the model to distinguish
        # hard vs easy questions within the same skill, which the GAT alone cannot
        # capture (since all questions mapping to the same skill share embeddings).
        self.question_difficulty = nn.Embedding(n_questions, 1)
        nn.init.zeros_(self.question_difficulty.weight)

        # Per-student ability bias (IRT θ_u): a simple learned scalar per student
        # that acts as a global ability offset, complementing the temporal context.
        self.student_ability = nn.Embedding(n_students, 1)
        nn.init.zeros_(self.student_ability.weight)

        # Student embedding cold-start dropout (applied during training only).
        # With p>0 the model swaps the student id for the reserved UNK slot so
        # the UNK row learns a generic prior — used at inference for unseen
        # students.  v3 zeroed e_u directly which collapsed the mastery head;
        # routing through UNK keeps the embedding distribution intact.
        self.student_emb_drop_p = student_emb_drop_p

        # Cache of the post-cold-start student id tensor — populated by
        # forward() so the decay cascade and ability bias use the same
        # (potentially UNK-swapped) ids as e_u.  Defined here so the attribute
        # exists even when forward() has not yet been called.
        self._effective_student_ids: torch.Tensor | None = None

    def set_prerequisite_graph(self, A_pre: torch.Tensor) -> None:
        """Install (or replace) RelationalDecay from the prerequisite adjacency matrix.

        Must be called BEFORE the optimizer is created so that rel_decay.w_p_logit
        is included in model.parameters() and receives gradient updates.

        Args:
            A_pre: [S, S] prerequisite edge matrix (1 where s' → s, else 0).
                   Will be moved to the same device as the rest of the model.
        """
        device = next(self.parameters()).device
        # Preserve trained w_p_logit across re-installations (e.g. device moves)
        saved_w: torch.Tensor | None = None
        if self.rel_decay is not None:
            saved_w = self.rel_decay.w_p_logit.data.clone()
        self.rel_decay = RelationalDecay(A_pre).to(device)
        if saved_w is not None:
            self.rel_decay.w_p_logit.data.copy_(saved_w)

    def compute_decay(
        self,
        student_ids: torch.Tensor,
        delta_t: torch.Tensor,
        mastery_prior: torch.Tensor,
        review_count: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Run the 4-stage decay cascade (Eq. 6-11).

        Args:
            student_ids:    [B] student indices
            delta_t:        [B, S] seconds since last practice per skill
            mastery_prior:  [B, S] mastery estimates in [0, 1]
            review_count:   [B, S] cumulative practice count per skill
        Returns:
            [B, S] unified decay values in [0, 1]
        """
        d_base = self.base_decay(student_ids, delta_t, review_count)
        d_diff = self.diff_decay(d_base)
        d_rel = self.rel_decay(d_diff) if self.rel_decay is not None else d_diff
        mastery_scaled = 1.0 + 4.0 * mastery_prior.clamp(0.0, 1.0)
        d_mast = self.mast_decay(d_rel, mastery_scaled)
        return self.unified_decay(d_base, d_diff, d_rel, d_mast)

    def run_gcn(
        self,
        H_skill_raw: torch.Tensor,
        A_pre: torch.Tensor,
        A_qs: torch.Tensor,
        A_vs: torch.Tensor,
        A_rs: torch.Tensor,
        A_uq: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        """Run GAT stages with gradient tracking (for periodic refresh)."""
        return self.gat(H_skill_raw, A_pre, A_qs, A_vs, A_rs, A_uq)

    @torch.no_grad()
    def run_gcn_cached(
        self,
        H_skill_raw: torch.Tensor,
        A_pre: torch.Tensor,
        A_qs: torch.Tensor,
        A_vs: torch.Tensor,
        A_rs: torch.Tensor,
        A_uq: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        """Run GAT stages and detach outputs for caching."""
        out = self.gat(H_skill_raw, A_pre, A_qs, A_vs, A_rs, A_uq)
        return {k: v.detach() for k, v in out.items()}

    def forward(
        self,
        H_skill_raw: torch.Tensor,
        A_pre: torch.Tensor,
        A_qs: torch.Tensor,
        A_vs: torch.Tensor,
        A_rs: torch.Tensor,
        A_uq: torch.Tensor,
        event_types: torch.Tensor,
        entity_indices: torch.Tensor,
        outcomes: torch.Tensor,
        timestamps: torch.Tensor,
        decay_values: torch.Tensor,
        pad_mask: torch.Tensor,
        target_type: torch.Tensor,
        target_idx: torch.Tensor,
        student_ids: torch.Tensor | None = None,
        delta_t_skills: torch.Tensor | None = None,
        review_count: torch.Tensor | None = None,
        mastery_prior: torch.Tensor | None = None,
        gat_cache: dict[str, torch.Tensor] | None = None,
    ) -> dict[str, torch.Tensor]:
        # GAT with optional caching (2-3x speedup when cached)
        if gat_cache is not None:
            gat_out = gat_cache
        else:
            gat_out = self.gat(H_skill_raw, A_pre, A_qs, A_vs, A_rs, A_uq)

        h_s = gat_out["h_s"]
        h_qa = gat_out["h_qa"]
        h_v = gat_out["h_v"]
        h_r = gat_out["h_r"]
        h_u = gat_out["h_u"]

        h_u_t = self.temporal(
            event_types,
            entity_indices,
            outcomes,
            timestamps,
            decay_values,
            pad_mask,
            h_qa,
            h_v,
            h_r,
        )

        # e_u: static student embedding from GCN (paper Eq. 12-13).
        #
        # Cold-start handling: instead of zeroing e_u (which destroys signal
        # and biases the network toward predicting zero mastery), we *swap* the
        # student id for the reserved UNK slot during training with probability
        # `student_emb_drop_p`.  The UNK row in h_u thus learns a generic
        # cold-start prior, which is exactly what gets used at inference time
        # for unseen students (model_registry routes OOV students to UNK).
        if student_ids is not None:
            sid = student_ids.clamp(max=h_u.size(0) - 1)
            if self.training and self.student_emb_drop_p > 0.0:
                drop = (
                    torch.rand(sid.size(0), device=sid.device) < self.student_emb_drop_p
                )
                sid = torch.where(
                    drop,
                    torch.full_like(sid, self.unk_student_idx),
                    sid,
                )
            self._effective_student_ids = sid  # cached for ability bias below
            e_u = h_u[sid]
        else:
            self._effective_student_ids = None
            e_u = h_u_t

        B = e_u.size(0)
        S = h_s.size(0)

        # Decay cascade (Eq. 6-11) — compute δ_{u,s} and δ̄_q
        if student_ids is not None and delta_t_skills is not None:
            m_prior = (
                mastery_prior
                if mastery_prior is not None
                else torch.full((B, S), 0.5, device=e_u.device)
            )
            # Use the effective (post-cold-start-dropout) student id so the
            # base-decay table sees the UNK row when e_u was UNK-swapped.
            decay_sid = (
                self._effective_student_ids
                if self._effective_student_ids is not None
                else student_ids
            )
            decay_us = self.compute_decay(
                decay_sid, delta_t_skills, m_prior, review_count
            )
            qs_weights = A_qs[target_idx.clamp(max=A_qs.size(0) - 1)]
            qs_norm = qs_weights / qs_weights.sum(-1, keepdim=True).clamp(min=1e-8)
            decay_bar_q = (qs_norm * decay_us).sum(-1)
        else:
            decay_us = torch.zeros(B, S, device=e_u.device)
            decay_bar_q = torch.zeros(B, device=e_u.device)

        # Target embedding lookup from entity tables
        max_entities = max(h_qa.size(0), h_v.size(0), h_r.size(0))

        def _pad(h: torch.Tensor) -> torch.Tensor:
            if h.size(0) < max_entities:
                return torch.cat(
                    [
                        h,
                        torch.zeros(
                            max_entities - h.size(0), h.size(1), device=h.device
                        ),
                    ]
                )
            return h

        entity_table = torch.stack([_pad(h_qa), _pad(h_v), _pad(h_r)], dim=0)
        target_emb = entity_table[target_type, target_idx]

        # Performance Head logit (Eq. 13 without final σ — training uses logits)
        perf_input = torch.cat(
            [e_u, target_emb, h_u_t, decay_bar_q.unsqueeze(-1)], dim=-1
        )
        response_logit = self.performance_head.mlp(perf_input).squeeze(-1)

        # Add per-question difficulty bias (IRT b_q).  Zero-initialised so
        # training starts at unbiased predictions and the signal guides each
        # question toward its true difficulty.
        q_diff_bias = self.question_difficulty(
            target_idx.clamp(max=self.question_difficulty.num_embeddings - 1)
        ).squeeze(-1)
        # Add per-student ability bias (IRT θ_u).  Also zero-initialised.
        # We use the SAME effective-student-id tensor as e_u so cold-start
        # dropout consistently routes both the embedding and the bias through
        # the UNK slot — preventing the train/inference distribution skew that
        # plagued v3 (where cold-start zeroed e_u but kept the real student's
        # ability bias active).
        if self._effective_student_ids is not None:
            ability_sid = self._effective_student_ids.clamp(
                max=self.student_ability.num_embeddings - 1
            )
            s_ability_bias = self.student_ability(ability_sid).squeeze(-1)
        else:
            s_ability_bias = torch.zeros(
                response_logit.size(0), device=response_logit.device
            )
        response_logit = response_logit + q_diff_bias + s_ability_bias

        # Mastery Head (Eq. 12)
        mastery = self.mastery_head(e_u, h_s, decay_us)

        return {"response_logit": response_logit, "mastery": mastery}
