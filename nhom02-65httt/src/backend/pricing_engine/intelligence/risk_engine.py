"""Pricing Risk Engine (WORK_SPEC §9).

RiskScore = Σ w_i * R_i, với R_i là điểm 0-100 của từng nhóm rủi ro đang
kích hoạt.
"""

from __future__ import annotations

from typing import Any

from ..config import (
    HIGH_PRICE_CHANGE_WARNING,
    RISK_SEVERITY_SCORE,
    RISK_WEIGHTS,
    risk_level_for,
)
from ..core.feature_engineering import margin_of, price_change_ratio
from ..schemas.input_schema import MarketInput, PricingContextInput, ProductInput
from ..schemas.output_schema import RiskReport


def _factor(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def assess_risk(
    *,
    price: float,
    product: ProductInput,
    market: MarketInput,
    context: PricingContextInput,
    forecast: dict[str, Any] | None = None,
) -> RiskReport:
    """Đánh giá rủi ro của một mức giá đề xuất."""
    factors: list[dict[str, str]] = []
    margin = margin_of(price, product.cost_price, context.channel_fee_rate)
    change = abs(price_change_ratio(price, product.current_price))

    if margin < context.min_margin - 1e-9:
        factors.append(
            _factor(
                "MARGIN_BELOW_MIN",
                "HIGH",
                f"Biên lợi nhuận {margin:.1%} thấp hơn mức tối thiểu "
                f"{context.min_margin:.0%}.",
            )
        )

    if market.confidence_score < 0.8:
        severity = "HIGH" if market.confidence_score < 0.5 else "MEDIUM"
        factors.append(
            _factor(
                "LOW_DATA_CONFIDENCE",
                severity,
                f"Độ tin cậy dữ liệu thị trường chỉ đạt "
                f"{market.confidence_score:.0%}.",
            )
        )

    if change > context.max_price_change_percent + 1e-9:
        factors.append(
            _factor(
                "HIGH_PRICE_CHANGE",
                "HIGH",
                f"Mức thay đổi giá {change:.1%} vượt giới hạn "
                f"{context.max_price_change_percent:.0%}.",
            )
        )
    elif change > HIGH_PRICE_CHANGE_WARNING:
        factors.append(
            _factor(
                "HIGH_PRICE_CHANGE",
                "MEDIUM",
                f"Mức thay đổi giá {change:.1%} ở mức đáng lưu ý.",
            )
        )

    if forecast is not None:
        status = str(forecast.get("status", "OK")).upper()
        if status != "OK":
            factors.append(
                _factor(
                    "FORECAST_UNCERTAINTY",
                    "MEDIUM",
                    "Không đủ dữ liệu để dự báo nhu cầu đáng tin cậy.",
                )
            )
        else:
            mae = float(forecast.get("mae", 0.0) or 0.0)
            demand = float(forecast.get("demand", 0.0) or 0.0)
            if demand > 0 and mae / demand > 0.25:
                factors.append(
                    _factor(
                        "FORECAST_UNCERTAINTY",
                        "MEDIUM",
                        f"Sai số dự báo MAE {mae:.1f} lớn so với nhu cầu "
                        f"{demand:.1f}.",
                    )
                )

    competitor = market.competitor_price
    if competitor is not None and competitor > 0:
        deviation = abs(competitor - product.current_price) / product.current_price
        if deviation > 0.4:
            factors.append(
                _factor(
                    "MARKET_ANOMALY",
                    "MEDIUM",
                    f"Giá đối thủ lệch {deviation:.0%} so với giá hiện tại — "
                    "cần kiểm tra tính bất thường.",
                )
            )

    if product.inventory_days >= 90.0:
        factors.append(
            _factor(
                "INVENTORY_HIGH",
                "LOW",
                f"Tuổi tồn kho {product.inventory_days:.0f} ngày ở mức cao.",
            )
        )

    total = 0.0
    for factor in factors:
        weight = RISK_WEIGHTS.get(factor["code"], 0.0)
        total += weight * RISK_SEVERITY_SCORE.get(factor["severity"], 0.0)
    total = round(min(100.0, total), 2)
    level = risk_level_for(total)

    return RiskReport(
        score=total,
        level=level,
        factors=factors,
        requires_review=level in {"HIGH", "CRITICAL"},
        execution_allowed=level != "CRITICAL",
    )
