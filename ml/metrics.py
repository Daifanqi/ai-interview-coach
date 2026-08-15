"""Metric computation shared by train.py, baselines.py, learning_curve.py.

Pure functions over (y_true, y_pred) int-label arrays — no torch/transformers
dependency, so this is fully covered by ml/self_test.py without touching the
model training path.
"""
from __future__ import annotations

from sklearn.metrics import cohen_kappa_score, confusion_matrix, f1_score

NUM_BANDS = 5
BAND_LABELS = ["0-2", "3-4", "5-6", "7-8", "9-10"]


def within_k_accuracy(y_true: list[int], y_pred: list[int], k: int = 1) -> float:
    if not y_true:
        return float("nan")
    hits = sum(1 for t, p in zip(y_true, y_pred) if abs(t - p) <= k)
    return hits / len(y_true)


def compute_metrics(y_true: list[int], y_pred: list[int]) -> dict:
    """macro-F1, quadratic-weighted kappa, +/-1-band accuracy, and the 5x5 confusion matrix.

    Labels are fixed to range(NUM_BANDS) (not inferred from the data) so a
    fold/eval split that happens not to contain every band still produces a
    full 5x5 confusion matrix and comparable metrics across folds.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"length mismatch: y_true={len(y_true)} y_pred={len(y_pred)}")
    if not y_true:
        raise ValueError("compute_metrics: empty input")

    labels = list(range(NUM_BANDS))
    macro_f1 = f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    qwk = cohen_kappa_score(y_true, y_pred, labels=labels, weights="quadratic")
    within1 = within_k_accuracy(y_true, y_pred, k=1)
    exact = within_k_accuracy(y_true, y_pred, k=0)
    cm = confusion_matrix(y_true, y_pred, labels=labels).tolist()

    return {
        "n": len(y_true),
        "exact_accuracy": exact,
        "macro_f1": macro_f1,
        "qwk": qwk,
        "within1_accuracy": within1,
        "confusion_matrix": cm,
        "confusion_matrix_labels": BAND_LABELS,
    }


def format_metrics(metrics: dict, title: str = "") -> str:
    lines = []
    if title:
        lines.append(title)
    lines.append(
        f"  n={metrics['n']}  exact_acc={metrics['exact_accuracy']:.3f}  "
        f"macro_f1={metrics['macro_f1']:.3f}  qwk={metrics['qwk']:.3f}  "
        f"within1_acc={metrics['within1_accuracy']:.3f}"
    )
    header = "        " + " ".join(f"{b:>6}" for b in metrics["confusion_matrix_labels"])
    lines.append("  confusion matrix (rows=true, cols=pred):")
    lines.append("  " + header)
    for label, row in zip(metrics["confusion_matrix_labels"], metrics["confusion_matrix"]):
        lines.append(f"  {label:>6}  " + " ".join(f"{v:>6}" for v in row))
    return "\n".join(lines)
