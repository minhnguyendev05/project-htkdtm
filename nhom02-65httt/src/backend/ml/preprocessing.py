"""Backward-compatible shim; canonical implementation lives in `app.ml.preprocessing`."""

from app.ml.preprocessing import build_sales_features, clean_price_history, compute_pmin

__all__ = ["build_sales_features", "clean_price_history", "compute_pmin"]
