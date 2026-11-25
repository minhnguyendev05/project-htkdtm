"""Dự báo nhu cầu baseline (WORK_SPEC §6, §20 TC07).

Baseline trung bình trượt trước, chỉ dùng mô hình phức tạp khi dữ liệu đủ.
Khi lịch sử không đủ, trả ``INSUFFICIENT_DATA`` thay vì tạo số liệu giả.
"""

from __future__ import annotations

from typing import Sequence

from ..config import DEFAULT_FORECAST_HORIZON, MIN_FORECAST_OBSERVATIONS


def _trend(values: Sequence[float]) -> str:
    if len(values) < 2:
        return "STABLE"
    half = len(values) // 2
    first = sum(values[:half]) / max(1, half)
    second = sum(values[half:]) / max(1, len(values) - half)
    if first <= 0:
        return "INCREASING" if second > 0 else "STABLE"
    change = (second - first) / first
    if change > 0.05:
        return "INCREASING"
    if change < -0.05:
        return "DECREASING"
    return "STABLE"


def _evaluate(values: Sequence[float], window: int) -> dict[str, float] | None:
    """Đánh giá walk-forward một bước trên chính lịch sử (MAE, RMSE)."""
    if len(values) <= window:
        return None
    errors: list[float] = []
    for index in range(window, len(values)):
        predicted = sum(values[index - window : index]) / window
        errors.append(values[index] - predicted)
    if not errors:
        return None
    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = (sum(error**2 for error in errors) / len(errors)) ** 0.5
    return {"mae": round(mae, 4), "rmse": round(rmse, 4)}


def moving_average_forecast(
    history: Sequence[float],
    horizon: int = DEFAULT_FORECAST_HORIZON,
    window: int = 3,
) -> list[float]:
    """Dự báo ``horizon`` kỳ bằng trung bình trượt, cập nhật dần."""
    if not history:
        return []
    series = [float(value) for value in history]
    effective_window = max(1, min(window, len(series)))
    daily: list[float] = []
    for _ in range(max(0, horizon)):
        next_value = sum(series[-effective_window:]) / effective_window
        daily.append(round(next_value, 2))
        series.append(next_value)
    return daily


def forecast_demand(
    history: Sequence[float],
    horizon: int = DEFAULT_FORECAST_HORIZON,
    window: int = 3,
) -> dict[str, object]:
    """Trả về kết quả dự báo kèm đánh giá và trạng thái dữ liệu."""
    values = [float(value) for value in history]

    if len(values) < MIN_FORECAST_OBSERVATIONS:
        return {
            "status": "INSUFFICIENT_DATA",
            "model": "MOVING_AVERAGE",
            "model_name": "MOVING_AVERAGE",
            "forecast_horizon": horizon,
            "predicted_demand": None,
            "demand": None,
            "daily_forecast": [],
            "trend": "UNKNOWN",
            "evaluation": None,
            "observations": len(values),
        }

    daily = moving_average_forecast(values, horizon=horizon, window=window)
    predicted = round(sum(daily), 2) if daily else None
    # Nhu cầu/ngày dùng cho chấm điểm doanh thu; None khi không dự báo được.
    daily_demand = round(predicted / horizon, 2) if predicted and horizon else None

    return {
        "status": "OK",
        "model": "MOVING_AVERAGE",
        "model_name": "MOVING_AVERAGE",
        "forecast_horizon": horizon,
        "predicted_demand": predicted,
        "demand": daily_demand,
        "daily_forecast": daily,
        "trend": _trend(values),
        "evaluation": _evaluate(values, max(1, min(window, len(values)))),
        "observations": len(values),
    }
