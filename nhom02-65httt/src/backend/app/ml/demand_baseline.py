"""Demand forecasting models (LinearRegression baseline + ML-assisted predictor)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from sklearn.linear_model import LinearRegression

from app.ml.preprocessing import build_sales_features


class DemandBaseline:
    """Linear regression baseline for daily demand forecasting."""

    def __init__(self) -> None:
        self.model = LinearRegression()

    def fit(self, X: np.ndarray, y: np.ndarray) -> DemandBaseline:
        """Fit linear regression on feature matrix X and target demand y."""
        self.model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict demand for input feature matrix X."""
        return self.model.predict(X)


def forecast_demand_ml(
    records: Sequence[Any],
    *,
    target_price: float,
    min_samples: int = 4,
) -> tuple[float, float, str] | None:
    """Forecast next-day demand and growth rate from chronological SalesRecord rows.

    Returns ``(predicted_demand, growth_rate, model_name)`` or ``None`` if history
    has fewer than ``min_samples`` rows.
    """
    if len(records) < min_samples:
        return None

    X, y = build_sales_features(records)
    if len(y) < min_samples:
        return None

    mean_price = float(np.mean(X[:, 1])) if np.mean(X[:, 1]) > 0 else max(target_price, 1.0)
    rolling_3d = float(np.mean(y[-3:]))
    last_date = getattr(records[-1], "order_date", None)
    next_dow = float((last_date.weekday() + 1) % 7) if hasattr(last_date, "weekday") else 0.0
    next_x = np.array(
        [
            [
                float(len(records)),
                float(target_price),
                float(target_price) / mean_price,
                rolling_3d,
                next_dow,
            ]
        ],
        dtype=float,
    )

    if len(records) >= 12:
        from xgboost import XGBRegressor

        xgb = XGBRegressor(
            n_estimators=50,
            max_depth=3,
            learning_rate=0.1,
            objective="reg:squarederror",
            random_state=42,
        )
        xgb.fit(X, y)
        pred = max(0.0, float(xgb.predict(next_x)[0]))
        model_name = "XGBoost"
    else:
        baseline = DemandBaseline().fit(X, y)
        pred = max(0.0, float(baseline.predict(next_x)[0]))
        model_name = "LinearRegression"

    recent_avg = float(np.mean(y[-min(7, len(y)) :]))
    growth = 0.0
    if recent_avg > 0:
        growth = max(-0.5, min(1.0, (pred - recent_avg) / recent_avg))

    return round(pred, 2), round(growth, 4), model_name
