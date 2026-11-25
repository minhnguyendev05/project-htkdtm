"""Dự báo nhu cầu baseline (WORK_SPEC §6)."""

from .demand_forecaster import forecast_demand, moving_average_forecast

__all__ = ["forecast_demand", "moving_average_forecast"]
