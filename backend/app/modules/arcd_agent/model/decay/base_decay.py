from __future__ import annotations

import torch
import torch.nn as nn


class BaseDecay(nn.Module):
    """Exponential forgetting with stability strengthening and proficiency modulation.

    λ_eff = λ_{u,s} / ((1 + α · ln(1 + n_{u,s})) · (1 + γ · p_u))
    δ^base_{u,s}(Δt) = exp(-λ_eff · Δt_days)

    Two complementary mechanisms slow forgetting:
      • Repeated study (n): each review flattens the curve (spacing effect)
      • Student proficiency (p): consistently high-performing students
        retain knowledge longer (proficiency modulation)
    """

    SECONDS_PER_DAY = 86400.0

    def __init__(self, n_students: int, n_skills: int):
        super().__init__()
        self.lambda_raw = nn.Embedding(n_students, n_skills)
        nn.init.uniform_(self.lambda_raw.weight, 0.01, 0.03)
        self.alpha_logit = nn.Parameter(torch.tensor(0.0))
        self.gamma_logit = nn.Parameter(torch.tensor(0.0))

    def forward(
        self,
        student_ids: torch.Tensor,
        delta_t: torch.Tensor,
        review_count: torch.Tensor | None = None,
        proficiency: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """
        Args:
            student_ids:  [B] long tensor — student indices
            delta_t:      [B, S] float tensor — seconds since last interaction
            review_count: [B, S] float tensor — cumulative practice count per skill
                          (optional; defaults to 0 = no strengthening)
            proficiency:  [B] float tensor — overall student proficiency in [0, 1]
                          (optional; defaults to no proficiency modulation)
        Returns:
            [B, S] base retention probability
        """
        lambda_us = self.lambda_raw(student_ids).clamp(0.005, 0.05)
        alpha = self.alpha_logit.sigmoid() * 1.9 + 0.1  # ∈ [0.1, 2.0]
        gamma = self.gamma_logit.sigmoid() * 2.9 + 0.1  # ∈ [0.1, 3.0]

        stability = torch.ones_like(lambda_us)

        if review_count is not None:
            stability = stability * (1.0 + alpha * torch.log1p(review_count.float()))

        if proficiency is not None:
            p = proficiency.clamp(0.0, 1.0).unsqueeze(-1)  # [B, 1]
            stability = stability * (1.0 + gamma * p)

        lambda_eff = lambda_us / stability
        delta_t_days = delta_t / self.SECONDS_PER_DAY
        return torch.exp(-lambda_eff * delta_t_days)
