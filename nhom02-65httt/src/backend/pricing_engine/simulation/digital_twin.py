"""Digital twin simulation for what-if price, demand, revenue, and profit curves."""

from __future__ import annotations

from collections.abc import Iterable


def simulate_price_curve(
    *,
    current_price: float,
    unit_cost: float,
    channel_fee_rate: float,
    floor_price: float | None,
    base_demand: float,
    elasticity: float = -1.2,
    candidate_prices: Iterable[float] | None = None,
    competitor_price: float | None = None,
) -> list[dict[str, float | bool | None]]:
    """Simulate demand, revenue, profit, and margin across candidate prices."""
    if candidate_prices is not None:
        prices = sorted({round(float(p), 2) for p in candidate_prices if float(p) > 0})
    else:
        step_pcts = (-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15)
        prices = sorted(
            {round(current_price * (1.0 + pct), 2) for pct in step_pcts if current_price > 0}
        )

    safe_base = max(0.1, float(base_demand))
    safe_current = max(1.0, float(current_price))
    points: list[dict[str, float | bool | None]] = []

    for price in prices:
        rel_change = (price - safe_current) / safe_current
        demand_multiplier = max(0.05, 1.0 + elasticity * rel_change)
        predicted_demand = round(safe_base * demand_multiplier, 2)
        expected_revenue = round(price * predicted_demand, 2)
        unit_profit = price - unit_cost - (price * channel_fee_rate)
        expected_profit = round(unit_profit * predicted_demand, 2)
        expected_margin = round(unit_profit / price, 4) if price > 0 else 0.0
        above_floor = True if floor_price is None else price >= floor_price
        competitor_gap_pct = (
            round((price - competitor_price) / competitor_price, 4)
            if competitor_price and competitor_price > 0
            else None
        )
        points.append(
            {
                "price": price,
                "above_floor": above_floor,
                "predicted_demand": predicted_demand,
                "expected_revenue": expected_revenue,
                "expected_profit": expected_profit,
                "expected_margin": expected_margin,
                "competitor_gap_pct": competitor_gap_pct,
            }
        )

    return points


def simulate(prices, demand_fn):
    """Lightweight compatibility helper mapping prices via demand_fn."""
    return [{"price": p, "demand": demand_fn(p)} for p in prices]
