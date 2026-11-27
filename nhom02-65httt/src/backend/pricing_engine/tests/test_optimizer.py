"""Test chấm điểm đa mục tiêu và sinh ứng viên (WORK_SPEC §5)."""

from __future__ import annotations

import unittest

from pricing_engine.config import STRATEGY_WEIGHTS
from pricing_engine.core.candidate_generator import build_candidates
from pricing_engine.optimization.scoring import score_candidates
from pricing_engine.schemas.input_schema import (
    MarketInput,
    PricingContextInput,
    ProductInput,
)


def make_product(**overrides) -> ProductInput:
    data = {
        "product_id": "SKU-O",
        "current_price": 100000,
        "cost_price": 65000,
        "inventory_quantity": 100,
        "inventory_days": 20,
        "sales_velocity": 1.0,
        "safety_stock": 50,
    }
    data.update(overrides)
    return ProductInput(**data)


class TestCandidateGenerator(unittest.TestCase):
    def test_candidates_respect_floor_and_change_limit(self) -> None:
        prices = build_candidates(
            current_price=100000,
            floor_price=85000,
            competitor_price=95000,
            strategy_anchor=98000,
            max_price_change_percent=0.2,
            price_step=1000,
        )
        self.assertTrue(prices)
        for price in prices:
            self.assertGreaterEqual(price, 85000)
            self.assertLessEqual(price, 120000)

    def test_returns_empty_when_floor_above_upper_bound(self) -> None:
        prices = build_candidates(
            current_price=100000,
            floor_price=150000,
            competitor_price=None,
            strategy_anchor=100000,
            max_price_change_percent=0.2,
            price_step=1000,
        )
        self.assertEqual(prices, [])

    def test_candidates_are_unique_and_sorted(self) -> None:
        prices = build_candidates(
            current_price=100000,
            floor_price=80000,
            competitor_price=100000,
            strategy_anchor=100000,
            max_price_change_percent=0.2,
            price_step=5000,
        )
        self.assertEqual(prices, sorted(set(prices)))


class TestScoring(unittest.TestCase):
    def test_all_components_normalized_between_zero_and_one(self) -> None:
        prices = [85000, 90000, 95000, 100000, 105000]
        scored = score_candidates(
            prices,
            product=make_product(),
            market=MarketInput(competitor_price=95000, confidence_score=0.9),
            context=PricingContextInput(),
            strategy="COMPETITIVE_PRICING",
        )
        self.assertEqual(len(scored), len(prices))
        for candidate in scored:
            self.assertIsNotNone(candidate.breakdown)
            for value in candidate.breakdown.to_dict().values():
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_scores_sorted_descending(self) -> None:
        scored = score_candidates(
            [60000, 90000, 100000, 110000],
            product=make_product(),
            market=MarketInput(),
            context=PricingContextInput(),
            strategy="PROFIT_MAXIMIZATION",
        )
        scores = [candidate.score for candidate in scored]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_competitive_component_neutral_without_market(self) -> None:
        scored = score_candidates(
            [90000, 100000],
            product=make_product(),
            market=MarketInput(),
            context=PricingContextInput(),
            strategy="COMPETITIVE_PRICING",
        )
        for candidate in scored:
            self.assertAlmostEqual(candidate.breakdown.competitive, 0.5)

    def test_every_strategy_weight_sums_to_one(self) -> None:
        for strategy, weights in STRATEGY_WEIGHTS.items():
            self.assertAlmostEqual(
                sum(weights.values()), 1.0, places=6, msg=f"{strategy} weights"
            )


if __name__ == "__main__":
    unittest.main()
