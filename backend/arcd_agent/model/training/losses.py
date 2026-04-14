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
            targets = targets * (1.0 - self.label_smoothing) + 0.5 * self.label_smoothing

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
    """MSE loss between predicted and IRT mastery levels.

    sequence_weight: optional per-sample scalar in [0,1] that
    up-weights samples taken later in the student's sequence.
    Later snapshots have more history and are closer to the
    final IRT target, so they should carry more gradient signal.
    """

    def __init__(self, reduction: str = "mean"):
        super().__init__()
        self.reduction = reduction

    def forward(
        self,
        pred_mastery: torch.Tensor,
        true_mastery: torch.Tensor,
        seq_weight: torch.Tensor | None = None,
    ) -> torch.Tensor:
        mse = F.mse_loss(pred_mastery, true_mastery, reduction="none")  # (B, n_skills)
        mse = mse.mean(dim=-1)  # (B,) — mean over skills

        if seq_weight is not None:
            # seq_weight shape: (B,), values in [0, 1]
            mse = mse * seq_weight

        if self.reduction == "mean":
            return mse.mean()
        elif self.reduction == "sum":
            return mse.sum()
        return mse


class ARCDLoss(nn.Module):
    """Combined loss: L_focal + mastery_weight * L_mastery_weighted."""

    def __init__(
        self,
        gamma: float = 2.0,
        alpha: float = 0.25,
        label_smoothing: float = 0.1,
        mastery_weight: float = 0.05,
    ):
        super().__init__()
        self.focal = FocalLoss(gamma=gamma, alpha=alpha, label_smoothing=label_smoothing)
        self.mastery = MasteryLoss()
        self.mastery_weight = mastery_weight

    def forward(
        self,
        response_logits: torch.Tensor,
        response_targets: torch.Tensor,
        pred_mastery: torch.Tensor,
        true_mastery: torch.Tensor,
        seq_weight: torch.Tensor | None = None,
    ) -> dict:
        l_focal = self.focal(response_logits, response_targets)
        l_mastery = self.mastery(pred_mastery, true_mastery, seq_weight)
        total = l_focal + self.mastery_weight * l_mastery
        return {"total": total, "focal": l_focal, "mastery": l_mastery}
