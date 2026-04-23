from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class FocalLoss(nn.Module):
    """Binary focal loss for imbalanced classification with optional label smoothing.

    L = -alpha_t * (1 - p_t)^gamma * log(p_t)

    alpha:           weight for the *positive* class.
                     Set to 1 - pos_rate for imbalanced data.
                     With ~79% correct responses, alpha≈0.25 down-weights
                     the dominant positive class and focuses on hard negatives.
    label_smoothing: replaces hard {0,1} targets with {ε/2, 1-ε/2}.
                     Prevents overconfident predictions and is a strong
                     regulariser against memorisation.
    """

    def __init__(
        self,
        gamma: float = 2.0,
        alpha: float = 0.25,
        label_smoothing: float = 0.1,
        reduction: str = "mean",
    ):
        super().__init__()
        self.gamma = gamma
        self.alpha = alpha
        self.label_smoothing = label_smoothing
        self.reduction = reduction

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # Apply label smoothing: 0 → ε/2,  1 → 1 − ε/2
        if self.label_smoothing > 0:
            targets = (
                targets * (1.0 - self.label_smoothing) + 0.5 * self.label_smoothing
            )

        p = torch.sigmoid(logits)
        ce_loss = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")

        p_t = p * targets + (1 - p) * (1 - targets)
        alpha_t = self.alpha * targets + (1 - self.alpha) * (1 - targets)
        focal_weight = alpha_t * (1 - p_t) ** self.gamma

        loss = focal_weight * ce_loss

        if self.reduction == "mean":
            return loss.mean()
        elif self.reduction == "sum":
            return loss.sum()
        return loss


class MasteryLoss(nn.Module):
    """Masked MSE loss between predicted and IRT mastery levels.

    A per-skill mask is REQUIRED in practice: synthgen only emits ground-truth
    mastery for skills the student has actually interacted with (~5% of all
    skills per student in roma_synth_v3_2048).  Computing MSE over the full
    [B, n_skills] matrix without a mask was the root cause of the "mastery
    collapses to zero" bug — the model just learned to output near-zero
    everywhere because ~95% of targets were hard zeros.

    Args:
        pred_mastery: [B, n_skills] predictions in [0, 1]
        true_mastery: [B, n_skills] ground-truth mastery in [0, 1]
        mask:         [B, n_skills] 1.0 where target is observed, 0.0 elsewhere.
                      If None we fall back to unmasked behavior (NOT recommended
                      for sparse targets but kept for backward compat).
        seq_weight:   optional [B] per-sample scalar in [0, 1].
    """

    def __init__(self, reduction: str = "mean"):
        super().__init__()
        self.reduction = reduction

    def forward(
        self,
        pred_mastery: torch.Tensor,
        true_mastery: torch.Tensor,
        mask: torch.Tensor | None = None,
        seq_weight: torch.Tensor | None = None,
    ) -> torch.Tensor:
        sq_err = (pred_mastery - true_mastery) ** 2  # (B, n_skills)

        if mask is not None:
            mask = mask.to(sq_err.dtype)
            denom = mask.sum(dim=-1).clamp(min=1.0)  # (B,) avoid div-by-zero
            per_sample = (sq_err * mask).sum(dim=-1) / denom  # (B,)
        else:
            per_sample = sq_err.mean(dim=-1)  # (B,) — legacy unmasked path

        if seq_weight is not None:
            per_sample = per_sample * seq_weight

        if self.reduction == "mean":
            return per_sample.mean()
        elif self.reduction == "sum":
            return per_sample.sum()
        return per_sample


class ARCDLoss(nn.Module):
    """Combined loss: L_focal + mastery_weight * L_mastery_weighted.

    mastery_weight default raised from 0.05 → 0.5 because the masked
    MasteryLoss now emits a meaningful gradient signal (instead of being
    overwhelmingly dominated by zero targets).  0.5 keeps response prediction
    as the primary objective while ensuring the mastery head actually trains.
    """

    def __init__(
        self,
        gamma: float = 2.0,
        alpha: float = 0.25,
        label_smoothing: float = 0.1,
        mastery_weight: float = 0.5,
    ):
        super().__init__()
        self.focal = FocalLoss(
            gamma=gamma, alpha=alpha, label_smoothing=label_smoothing
        )
        self.mastery = MasteryLoss()
        self.mastery_weight = mastery_weight

    def forward(
        self,
        response_logits: torch.Tensor,
        response_targets: torch.Tensor,
        pred_mastery: torch.Tensor,
        true_mastery: torch.Tensor,
        mastery_mask: torch.Tensor | None = None,
        seq_weight: torch.Tensor | None = None,
    ) -> dict:
        l_focal = self.focal(response_logits, response_targets)
        l_mastery = self.mastery(pred_mastery, true_mastery, mastery_mask, seq_weight)
        total = l_focal + self.mastery_weight * l_mastery
        return {"total": total, "focal": l_focal, "mastery": l_mastery}
