"""ERP & price-history preprocessing, Pmin floor formula, and ML feature builder."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

FEATURE_COLUMNS: list[str] = [
    "day_idx",
    "unit_price",
    "price_ratio_vs_mean",
    "rolling_3d_qty",
    "day_of_week",
]


def clean_price_history(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter out price-history records with missing or non-positive prices."""
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        price = row.get("price")
        if price is None or price <= 0:
            continue
        cleaned.append(
            {
                "sku": row.get("sku"),
                "date": row.get("date"),
                "price": float(price),
            }
        )
    return cleaned


def compute_pmin(cost: float, fee_rate: float = 0.05, margin: float = 0.1) -> float:
    """Compute minimum safe floor price: Pmin = cost / (1 - fee_rate - margin)."""
    if cost < 0:
        raise ValueError("cost khong duoc am.")
    denominator = 1.0 - fee_rate - margin
    if denominator <= 0:
        raise ValueError("fee_rate + margin phai nho hon 1.")
    return round(cost / denominator, 2)


def build_sales_features(records: Sequence[Any]) -> tuple[np.ndarray, np.ndarray]:
    """Build (X, y) feature matrix from chronological SalesRecord-like objects.

    Each record must expose ``unit_price``, ``quantity``, and ``order_date``.
    """
    if not records:
        return np.empty((0, len(FEATURE_COLUMNS)), dtype=float), np.empty((0,), dtype=float)

    prices = [float(r.unit_price) for r in records]
    quantities = [float(max(0, r.quantity)) for r in records]
    mean_price = sum(prices) / len(prices) if prices else 1.0
    if mean_price <= 0:
        mean_price = 1.0

    rows: list[list[float]] = []
    for idx, rec in enumerate(records):
        window_start = max(0, idx - 3)
        prev_slice = quantities[window_start:idx]
        rolling_3d = sum(prev_slice) / len(prev_slice) if prev_slice else quantities[idx]
        dow = float(rec.order_date.weekday()) if hasattr(rec.order_date, "weekday") else 0.0
        unit_price = prices[idx]
        rows.append(
            [
                float(idx),
                unit_price,
                unit_price / mean_price,
                rolling_3d,
                dow,
            ]
        )

    return np.asarray(rows, dtype=float), np.asarray(quantities, dtype=float)
