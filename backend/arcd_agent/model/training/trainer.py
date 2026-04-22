"""ARCDTrainer: training harness for ARCDModel."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

if TYPE_CHECKING:
    from .arcd_model import ARCDModel
    from .losses import ARCDLoss

logger = logging.getLogger(__name__)


class ARCDTrainer:
    """Training harness for ARCDModel.

    Parameters
    ----------
    model : ARCDModel
    criterion : ARCDLoss
    graph_data : dict[str, torch.Tensor]
        Pre-built graph tensors (already on device).
    lr, weight_decay : float
        AdamW hyper-parameters.
    grad_clip : float
        Max gradient norm; 0 disables clipping.
    patience : int
        Early-stopping patience (epochs without val-AUC improvement).
    t0 : int
        CosineAnnealingLR T_max (used after warmup).
    warmup_epochs : int
        Linear LR warmup length.
    rdrop_alpha : float
        R-Drop KL weight; 0 disables R-Drop.
    device : torch.device
    use_amp : bool
        CUDA → fp16 GradScaler.
    use_bf16 : bool
        MPS → bf16 autocast (no scaler needed; ~30-50% speedup on Apple Silicon).
    gcn_refresh_every : int
        Refresh GAT cache every N epochs; 0 = never refresh.
    """

    def __init__(
        self,
        model: ARCDModel,
        criterion: ARCDLoss,
        graph_data: dict[str, torch.Tensor],
        lr: float = 1e-3,
        weight_decay: float = 1e-4,
        grad_clip: float = 1.0,
        patience: int = 15,
        t0: int = 10,
        warmup_epochs: int = 5,
        rdrop_alpha: float = 0.3,
        device: torch.device | None = None,
        use_amp: bool = False,
        use_bf16: bool = False,
        gcn_refresh_every: int = 5,
    ) -> None:
        self.model = model
        self.criterion = criterion
        self.graph_data = graph_data
        self.device = device or torch.device("cpu")
        self.grad_clip = grad_clip
        self.patience = patience
        self.rdrop_alpha = rdrop_alpha
        self.gcn_refresh_every = gcn_refresh_every
        self.use_amp = use_amp
        self.use_bf16 = use_bf16
        self.warmup_epochs = warmup_epochs
        self.t0 = t0

        self.optimizer = torch.optim.AdamW(
            model.parameters(), lr=lr, weight_decay=weight_decay
        )

        # GradScaler only for CUDA fp16; MPS bf16 uses autocast without scaling.
        self._scaler: torch.amp.GradScaler | None = (
            torch.amp.GradScaler("cuda")
            if use_amp and self.device.type == "cuda"
            else None
        )

        self.best_val_auc: float = 0.0
        self._best_state: dict | None = None

    # ── Graph helpers ──────────────────────────────────────────────────────────

    def _build_gcn_args(self) -> tuple:
        """Return (H_skill_raw, A_pre, A_qs, A_vs, A_rs, A_uq)."""
        gd = self.graph_data
        return (
            gd["H_skill_raw"],
            gd["A_pre"],
            gd["A_qs"],
            gd["A_vs"],
            gd["A_rs"],
            gd["A_uq"],
        )

    def _to_device(self, batch: dict) -> dict:
        """Return batch with all tensors moved to self.device."""
        return {
            k: v.to(self.device) if isinstance(v, torch.Tensor) else v
            for k, v in batch.items()
        }

    # ── Forward ───────────────────────────────────────────────────────────────

    def _forward(
        self,
        batch: dict[str, torch.Tensor],
        gcn_cache: dict[str, torch.Tensor] | None = None,
    ) -> dict[str, torch.Tensor]:
        """Forward pass; moves batch to device internally."""
        b = self._to_device(batch)
        gd = self.graph_data
        return self.model(
            gd["H_skill_raw"],
            gd["A_pre"],
            gd["A_qs"],
            gd["A_vs"],
            gd["A_rs"],
            gd["A_uq"],
            b["event_types"],
            b["entity_indices"],
            b["outcomes"],
            b["timestamps"],
            b["decay_values"],
            b["pad_mask"],
            b["target_type"],
            b["target_idx"],
            student_ids=b.get("student_ids"),
            delta_t_skills=b.get("delta_t_skills"),
            gat_cache=gcn_cache,
        )

    def _compute_loss(
        self,
        batch: dict[str, torch.Tensor],
        out: dict[str, torch.Tensor],
        out2: dict[str, torch.Tensor] | None = None,
    ) -> torch.Tensor:
        """ARCDLoss + optional R-Drop KL consistency."""
        b = self._to_device(batch)
        loss_dict = self.criterion(
            out["response_logit"],
            b["response_target"],
            out["mastery"],
            b["mastery_target"],
            mastery_mask=b.get("mastery_mask"),
        )
        total: torch.Tensor = loss_dict["total"]

        if out2 is not None and self.rdrop_alpha > 0.0:
            eps = 1e-8
            p1 = torch.sigmoid(out["response_logit"])
            p2 = torch.sigmoid(out2["response_logit"])
            kl1 = F.kl_div((p1 + eps).log(), p2.detach(), reduction="batchmean")
            kl2 = F.kl_div((p2 + eps).log(), p1.detach(), reduction="batchmean")
            total = total + self.rdrop_alpha * (kl1 + kl2) * 0.5

        return total

    # ── Validation ────────────────────────────────────────────────────────────

    @torch.no_grad()
    def _validate(
        self,
        loader: DataLoader,
        gcn_cache: dict[str, torch.Tensor],
    ) -> tuple[float, float, float, float]:
        """Return (mean_val_loss, val_auc, mean_focal_loss, mean_mastery_loss)."""
        from sklearn.metrics import roc_auc_score

        self.model.eval()
        total_loss, total_focal, total_mastery, n_batches = 0.0, 0.0, 0.0, 0
        all_logits: list[torch.Tensor] = []
        all_targets: list[torch.Tensor] = []

        for batch in loader:
            b = self._to_device(batch)
            out = self._forward(b, gcn_cache=gcn_cache)
            # Compute component losses separately for diagnostics
            loss_dict = self.criterion(
                out["response_logit"],
                b["response_target"],
                out["mastery"],
                b["mastery_target"],
                mastery_mask=b.get("mastery_mask"),
            )
            total_loss += loss_dict["total"].item()
            total_focal += loss_dict["focal"].item()
            total_mastery += loss_dict["mastery"].item()
            n_batches += 1
            all_logits.append(out["response_logit"].cpu())
            all_targets.append(b["response_target"].cpu())

        probs = torch.sigmoid(torch.cat(all_logits)).numpy()
        targets = torch.cat(all_targets).numpy()
        try:
            auc = float(roc_auc_score(targets, probs))
        except Exception:
            auc = 0.0

        denom = max(n_batches, 1)
        return (
            total_loss / denom,
            auc,
            total_focal / denom,
            total_mastery / denom,
        )

    # ── Training loop ─────────────────────────────────────────────────────────

    def fit(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        n_epochs: int,
        verbose: bool = False,
    ) -> dict[str, list[float]]:
        """Train model; returns history with train_loss, val_loss, val_auc lists."""
        history: dict[str, list[float]] = {
            "train_loss": [],
            "val_loss": [],
            "val_auc": [],
            "val_focal": [],
            "val_mastery": [],
        }

        # LR schedule: linear warmup → cosine annealing
        def _warmup_lambda(epoch: int) -> float:
            if self.warmup_epochs <= 0:
                return 1.0
            return min(1.0, float(epoch + 1) / float(self.warmup_epochs))

        warmup_sched = torch.optim.lr_scheduler.LambdaLR(self.optimizer, _warmup_lambda)
        cosine_sched = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=max(n_epochs - self.warmup_epochs, 1)
        )

        # AMP context: CUDA uses GradScaler (handled in step), MPS uses bf16 autocast.
        if self.use_bf16 and self.device.type == "mps":
            amp_ctx: contextlib.AbstractContextManager = torch.autocast(
                device_type="mps", dtype=torch.bfloat16
            )
        else:
            amp_ctx = contextlib.nullcontext()

        # Initial GAT cache (detached, no grad)
        gcn_cache = self.model.run_gcn_cached(*self._build_gcn_args())
        no_improve = 0

        for epoch in range(n_epochs):
            # Refresh GAT cache periodically to incorporate updated skill embeddings
            if (
                epoch > 0
                and self.gcn_refresh_every > 0
                and epoch % self.gcn_refresh_every == 0
            ):
                gcn_cache = self.model.run_gcn_cached(*self._build_gcn_args())

            self.model.train()
            epoch_loss, n_batches = 0.0, 0

            for batch in train_loader:
                b = self._to_device(batch)
                self.optimizer.zero_grad()

                with amp_ctx:
                    out = self._forward(b, gcn_cache=gcn_cache)
                    out2 = (
                        self._forward(b, gcn_cache=gcn_cache)
                        if self.rdrop_alpha > 0.0
                        else None
                    )
                    loss = self._compute_loss(b, out, out2)

                if self._scaler is not None:
                    self._scaler.scale(loss).backward()
                    self._scaler.unscale_(self.optimizer)
                    if self.grad_clip > 0:
                        nn.utils.clip_grad_norm_(
                            self.model.parameters(), self.grad_clip
                        )
                    self._scaler.step(self.optimizer)
                    self._scaler.update()
                else:
                    loss.backward()
                    if self.grad_clip > 0:
                        nn.utils.clip_grad_norm_(
                            self.model.parameters(), self.grad_clip
                        )
                    self.optimizer.step()

                epoch_loss += loss.item()
                n_batches += 1

            # Step LR scheduler
            if epoch < self.warmup_epochs:
                warmup_sched.step()
            else:
                cosine_sched.step()

            avg_train_loss = epoch_loss / max(n_batches, 1)
            val_loss, val_auc, val_focal, val_mastery = self._validate(
                val_loader, gcn_cache
            )

            history["train_loss"].append(avg_train_loss)
            history["val_loss"].append(val_loss)
            history["val_auc"].append(val_auc)
            history["val_focal"].append(val_focal)
            history["val_mastery"].append(val_mastery)

            if verbose:
                logger.info(
                    "Epoch %3d/%d  train=%.4f  val=%.4f  (focal=%.4f  mastery=%.4f)  auc=%.4f  lr=%.2e",
                    epoch + 1,
                    n_epochs,
                    avg_train_loss,
                    val_loss,
                    val_focal,
                    val_mastery,
                    val_auc,
                    self.optimizer.param_groups[0]["lr"],
                )

            if val_auc > self.best_val_auc:
                self.best_val_auc = val_auc
                self._best_state = {
                    k: v.cpu().clone() for k, v in self.model.state_dict().items()
                }
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= self.patience:
                    logger.info(
                        "Early stopping at epoch %d (patience=%d, best_auc=%.4f)",
                        epoch + 1,
                        self.patience,
                        self.best_val_auc,
                    )
                    break

        # Restore best weights
        if self._best_state is not None:
            self.model.load_state_dict(
                {k: v.to(self.device) for k, v in self._best_state.items()}
            )

        return history
