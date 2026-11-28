"""Backward-compatible shim; canonical implementation lives in `app.ml.model_runs`."""

from app.ml.model_runs import (
    evaluate_model,
    run_model_comparison,
    train_and_log_from_sales_records,
)

__all__ = ["evaluate_model", "run_model_comparison", "train_and_log_from_sales_records"]
