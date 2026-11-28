"""Backward-compatible shim; canonical implementation lives in `app.ml.demand_baseline`."""

from app.ml.demand_baseline import DemandBaseline, forecast_demand_ml

__all__ = ["DemandBaseline", "forecast_demand_ml"]
