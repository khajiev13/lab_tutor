from __future__ import annotations

import torch
import torch.nn as nn
from torch.utils.data import DataLoader


class TemperatureScaler(nn.Module):
    """Post-hoc temperature scaling for calibrating model logits.

    Learns a single parameter T that divides logits before sigmoid:
        P_calibrated = sigmoid(logit / T)

    Optimized on the validation set using NLL loss.
    """

    def __init__(self):
        super().__init__()
        self.temperature = nn.Parameter(torch.ones(1))

    def forward(self, logits: torch.Tensor) -> torch.Tensor:
        return logits / self.temperature.clamp(min=0.01)

    @torch.no_grad()
    def calibrated_probs(self, logits: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.forward(logits))

    def fit(
        self,
        model: nn.Module,
        val_loader: DataLoader,
        graph_data: dict[str, torch.Tensor],
        device: torch.device,
        max_iter: int = 200,
        lr: float = 0.01,
    ) -> float:
        """Optimize temperature on validation data.

        Returns the learned temperature value.
        """
        model.eval()
        all_logits, all_targets = [], []

        with torch.no_grad():
            for batch in val_loader:
                out = model(
                    graph_data["H_skill_raw"],
                    graph_data["A_pre"],
                    graph_data["A_qs"],
                    graph_data["A_vs"],
                    graph_data["A_rs"],
                    graph_data["A_uq"],
                    batch["event_types"].to(device),
                    batch["entity_indices"].to(device),
                    batch["outcomes"].to(device),
                    batch["timestamps"].to(device),
                    batch["decay_values"].to(device),
                    batch["pad_mask"].to(device),
                    batch["target_type"].to(device),
                    batch["target_idx"].to(device),
                )
                all_logits.append(out["response_logit"].cpu())
                all_targets.append(batch["response_target"])

        logits = torch.cat(all_logits).detach()
        targets = torch.cat(all_targets).detach()

        self.temperature.data.fill_(1.0)
        optimizer = torch.optim.LBFGS([self.temperature], lr=lr, max_iter=max_iter)
        criterion = nn.BCEWithLogitsLoss()

        def closure():
            optimizer.zero_grad()
            loss = criterion(self.forward(logits), targets)
            loss.backward()
            return loss

        optimizer.step(closure)

        return self.temperature.item()
