from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    log_loss,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)


class MetricsSuite:
    """Computes 16 evaluation metrics for binary classification.

    Metrics:
      Discrimination:  AUC-ROC, PR-AUC
      Classification:  Accuracy, Balanced Acc, F1, Precision, Recall,
                       Specificity, MCC, Cohen's Kappa
      Probabilistic:   RMSE, Log Loss, Brier Score
      Calibration:     ECE, Calibration Slope, Calibration Intercept
    """

    def __init__(self, n_bins_ece: int = 10):
        self.n_bins_ece = n_bins_ece

    @staticmethod
    def _specificity(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        tn, fp = cm[0, 0], cm[0, 1]
        return tn / max(tn + fp, 1)

    def _ece(self, y_true: np.ndarray, y_prob: np.ndarray) -> float:
        bin_edges = np.linspace(0.0, 1.0, self.n_bins_ece + 1)
        ece = 0.0
        for lo, hi in zip(bin_edges[:-1], bin_edges[1:], strict=False):
            mask = (y_prob >= lo) & (y_prob < hi)
            if mask.sum() == 0:
                continue
            frac = mask.mean()
            avg_conf = y_prob[mask].mean()
            avg_acc = y_true[mask].mean()
            ece += frac * abs(avg_conf - avg_acc)
        return ece

    @staticmethod
    def _calibration_logistic(
        y_true: np.ndarray, y_prob: np.ndarray
    ) -> tuple[float, float]:
        eps = 1e-7
        logit_p = np.log(
            np.clip(y_prob, eps, 1 - eps) / np.clip(1 - y_prob, eps, 1 - eps)
        )
        lr = LogisticRegression(solver="lbfgs", max_iter=1000)
        lr.fit(logit_p.reshape(-1, 1), y_true)
        return float(lr.coef_[0, 0]), float(lr.intercept_[0])

    def compute(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
        threshold: float = 0.5,
    ) -> dict[str, float]:
        y_pred = (y_prob >= threshold).astype(int)
        calib_slope, calib_intercept = self._calibration_logistic(y_true, y_prob)

        return {
            "AUC-ROC": roc_auc_score(y_true, y_prob),
            "PR-AUC": average_precision_score(y_true, y_prob),
            "Accuracy": accuracy_score(y_true, y_pred),
            "Balanced Acc": balanced_accuracy_score(y_true, y_pred),
            "F1": f1_score(y_true, y_pred, zero_division=0),
            "Precision": precision_score(y_true, y_pred, zero_division=0),
            "Recall": recall_score(y_true, y_pred, zero_division=0),
            "Specificity": self._specificity(y_true, y_pred),
            "RMSE": float(np.sqrt(np.mean((y_prob - y_true) ** 2))),
            "Log Loss": log_loss(y_true, np.clip(y_prob, 1e-7, 1 - 1e-7)),
            "Brier Score": brier_score_loss(y_true, y_prob),
            "ECE": self._ece(y_true, y_prob),
            "MCC": matthews_corrcoef(y_true, y_pred),
            "Cohen Kappa": cohen_kappa_score(y_true, y_pred),
            "Calib Slope": calib_slope,
            "Calib Intercept": calib_intercept,
        }

    def report(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
        threshold: float = 0.5,
        title: str = "MetricsSuite",
    ) -> dict[str, float]:
        metrics = self.compute(y_true, y_prob, threshold)

        print(f"\n{'=' * 60}")
        print(f"  {title}  (n={len(y_true)})")
        print(f"{'=' * 60}")

        groups = {
            "Discrimination": ["AUC-ROC", "PR-AUC"],
            "Classification": [
                "Accuracy",
                "Balanced Acc",
                "F1",
                "Precision",
                "Recall",
                "Specificity",
                "MCC",
                "Cohen Kappa",
            ],
            "Probabilistic": ["RMSE", "Log Loss", "Brier Score"],
            "Calibration": ["ECE", "Calib Slope", "Calib Intercept"],
        }

        for group_name, keys in groups.items():
            print(f"\n  {group_name}:")
            for k in keys:
                print(f"    {k:<20s}  {metrics[k]:>10.4f}")

        print(f"\n{'─' * 60}")
        return metrics
