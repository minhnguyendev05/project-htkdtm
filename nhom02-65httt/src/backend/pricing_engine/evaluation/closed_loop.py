"""Closed-loop evaluation comparing predicted demand vs realized sales."""

from __future__ import annotations


def evaluate(predicted: float, actual: float) -> dict[str, float]:
    """Compute absolute and percentage error for a single prediction."""
    abs_err = round(abs(predicted - actual), 4)
    pct_err = round(abs_err / actual, 4) if actual > 0 else 0.0
    return {"error": abs_err, "percentage_error": pct_err}


def summarize_closed_loop(items: list[dict[str, float]]) -> dict[str, float | int]:
    """Aggregate MAE and accuracy within 20% tolerance across evaluated recommendations."""
    if not items:
        return {"evaluated_count": 0, "mae": 0.0, "within_tolerance_count": 0}
    total_abs = sum(item["error"] for item in items)
    within_tol = sum(1 for item in items if item["percentage_error"] <= 0.20)
    return {
        "evaluated_count": len(items),
        "mae": round(total_abs / len(items), 4),
        "within_tolerance_count": within_tol,
    }
