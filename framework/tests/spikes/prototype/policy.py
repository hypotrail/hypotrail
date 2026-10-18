"""Pure threshold policy used by the workbench slider (prototype only).

The real ``policy.evaluate`` (WP2.4) also handles capacity rules and ties
at the cut. This one only needs to be pure so the slider can call it.
"""
from __future__ import annotations


def evaluate(y: list[int], score: list[float], threshold: float) -> dict[str, float | int]:
    selected = [s >= threshold for s in score]
    tp = sum(1 for sel, label in zip(selected, y) if sel and label == 1)
    n_selected = sum(selected)
    n_positive = sum(1 for label in y if label == 1)
    return {
        "threshold": threshold,
        "selected": n_selected,
        "true_positives": tp,
        "precision": tp / n_selected if n_selected else 0.0,
        "recall": tp / n_positive if n_positive else 0.0,
    }
