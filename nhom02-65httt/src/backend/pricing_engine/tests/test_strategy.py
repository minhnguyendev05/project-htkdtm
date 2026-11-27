"""Test bộ chọn chiến lược thích ứng (WORK_SPEC §4)."""

from __future__ import annotations

import unittest

from pricing_engine.schemas.input_schema import (
    MarketInput,
    PricingContextInput,
    ProductInput,
)
from pricing_engine.strategies.selector import select_strategy


def product(**overrides) -> ProductInput:
    data = {
        "product_id": "SKU-T",
        "current_price": 100000,
        "cost_price": 65000,
        "inventory_quantity": 100,
        "inventory_days": 20,
        "sales_velocity": 1.0,
        "safety_stock": 50,
        "demand_growth": 0.0,
        "product_position": "standard",
    }
    data.update(overrides)
    return ProductInput(**data)


def market(**overrides) -> MarketInput:
    data = {
        "competitor_price": 98000,
        "confidence_score": 0.9,
        "freshness_hours": 2,
    }
    data.update(overrides)
    return MarketInput(**data)


class TestStrategySelection(unittest.TestCase):
    def test_clearance_when_overstock_and_slow(self) -> None:
        selection = select_strategy(
            product(inventory_days=120, sales_velocity=0.1),
            market(),
            PricingContextInput(),
        )
        self.assertEqual(selection.strategy, "INVENTORY_CLEARANCE")
        self.assertGreaterEqual(len(selection.reasons), 2)

    def test_demand_capture_when_growth_and_low_stock(self) -> None:
        selection = select_strategy(
            product(demand_growth=0.3, inventory_quantity=10, safety_stock=50),
            market(),
            PricingContextInput(),
        )
        self.assertEqual(selection.strategy, "DEMAND_CAPTURE")

    def test_defensive_when_competitor_deep_discount(self) -> None:
        selection = select_strategy(
            product(current_price=100000),
            market(competitor_price=80000, confidence_score=0.9),
            PricingContextInput(),
        )
        self.assertEqual(selection.strategy, "DEFENSIVE_PRICING")

    def test_competitive_when_reliable_market(self) -> None:
        selection = select_strategy(
            product(), market(competitor_price=98000, confidence_score=0.9),
            PricingContextInput(),
        )
        self.assertEqual(selection.strategy, "COMPETITIVE_PRICING")

    def test_premium_for_premium_position(self) -> None:
        selection = select_strategy(
            product(product_position="premium"),
            MarketInput(),
            PricingContextInput(),
        )
        self.assertEqual(selection.strategy, "PREMIUM_PRICING")

    def test_profit_maximization_default(self) -> None:
        selection = select_strategy(
            product(),
            MarketInput(),
            PricingContextInput(),
        )
        self.assertEqual(selection.strategy, "PROFIT_MAXIMIZATION")

    def test_override_strategy_has_full_confidence(self) -> None:
        selection = select_strategy(
            product(),
            MarketInput(),
            PricingContextInput(strategy="PREMIUM_PRICING"),
        )
        self.assertEqual(selection.strategy, "PREMIUM_PRICING")
        self.assertEqual(selection.confidence, 1.0)

    def test_confidence_within_unit_interval(self) -> None:
        for selection in (
            select_strategy(product(), market(), PricingContextInput()),
            select_strategy(product(), MarketInput(), PricingContextInput()),
        ):
            self.assertGreaterEqual(selection.confidence, 0.0)
            self.assertLessEqual(selection.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
