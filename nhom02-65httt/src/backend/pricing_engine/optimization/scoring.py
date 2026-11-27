"""Hàm mục tiêu đa mục tiêu (WORK_SPEC §5.3).

Score(p) = w1*Profit + w2*Revenue + w3*Competitive + w4*Inventory - w5*Risk

Mỗi thành phần được chuẩn hóa min-max trên chính tập ứng viên để nằm trong
0..1 — đúng yêu cầu "chuẩn hóa về thang điểm 0–1" mà không cần một mốc tham
chiếu tùy ý.
"""

from __future__ import annotations

from ..config import CLEARANCE_INVENTORY_DAYS, weights_for
from ..core.feature_engineering import price_change_ratio, unit_profit
from ..schemas.input_schema import MarketInput, PricingContextInput, ProductInput
from ..schemas.output_schema import CandidatePrice, ObjectiveBreakdown


def _min_max(values: list[float]) -> list[float]:
    """Chuẩn hóa min-max; nếu mọi giá trị bằng nhau thì trả 0.5 trung tính."""
    if not values:
        return []
    low = min(values)
    high = max(values)
    if high - low <= 1e-9:
        return [0.5] * len(values)
    span = high - low
    return [(value - low) / span for value in values]


def _expected_demand(
    price: float,
    current_price: float,
    base_demand: float,
    elasticity: float | None,
) -> float:
    """Nhu cầu dự kiến tại một mức giá.

    Mặc định dùng ``base_demand`` từ dự báo (giá không đổi nhu cầu) — đây là
    baseline trung thực vì module Price Elasticity thuộc P1 (WORK_SPEC §7).
    Chỉ khi truyền ``elasticity`` mới hiệu chỉnh theo độ co giãn.
    """
    if elasticity is None or current_price <= 0 or price <= 0:
        return base_demand
    ratio = price / current_price
    try:
        return base_demand * max(0.0, ratio**elasticity)
    except (OverflowError, ValueError):
        return base_demand


def score_candidates(
    prices: list[float],
    *,
    product: ProductInput,
    market: MarketInput,
    context: PricingContextInput,
    strategy: str,
    expected_daily_demand: float | None = None,
    elasticity: float | None = None,
) -> list[CandidatePrice]:
    """Chấm điểm và sắp xếp các ứng viên theo điểm giảm dần.

    ``expected_daily_demand`` lấy từ Demand Forecasting; khi thiếu dữ liệu,
    dùng 1.0 để thành phần doanh thu vẫn so sánh được giữa các mức giá.
    """
    if not prices:
        return []

    weights = weights_for(strategy)
    fee = context.channel_fee_rate
    current = product.current_price
    cost = product.cost_price

    base_demand = (
        float(expected_daily_demand)
        if expected_daily_demand is not None and expected_daily_demand > 0
        else 1.0
    )

    profits = [unit_profit(price, cost, fee) for price in prices]
    revenues = [
        price * _expected_demand(price, current, base_demand, elasticity)
        for price in prices
    ]

    competitor = market.competitor_price if market.is_usable else None
    if competitor is not None and competitor > 0:
        competitiveness = [
            -abs(price - competitor) / competitor for price in prices
        ]
        competitive_norm = _min_max(competitiveness)
    else:
        competitive_norm = [0.5] * len(prices)

    # Tồn cao -> giá thấp được ưu tiên; ngược lại giá cao hơn có lợi hơn.
    clearance_mode = product.inventory_days >= CLEARANCE_INVENTORY_DAYS
    inventory_raw = [-price if clearance_mode else price for price in prices]
    inventory_norm = _min_max(inventory_raw)

    risk_norm = _min_max([abs(price_change_ratio(price, current)) for price in prices])

    profit_norm = _min_max(profits)
    revenue_norm = _min_max(revenues)

    scored: list[CandidatePrice] = []
    for index, price in enumerate(prices):
        breakdown = ObjectiveBreakdown(
            profit=round(profit_norm[index], 4),
            revenue=round(revenue_norm[index], 4),
            competitive=round(competitive_norm[index], 4),
            inventory=round(inventory_norm[index], 4),
            risk=round(risk_norm[index], 4),
        )
        total = (
            weights["profit"] * breakdown.profit
            + weights["revenue"] * breakdown.revenue
            + weights["competitive"] * breakdown.competitive
            + weights["inventory"] * breakdown.inventory
            - weights["risk"] * breakdown.risk
        )
        scored.append(
            CandidatePrice(
                price=price,
                score=round(total, 4),
                breakdown=breakdown,
            )
        )

    scored.sort(key=lambda candidate: (-candidate.score, candidate.price))
    return scored
