"""Test Pricing Risk Engine và Conflict Detection (WORK_SPEC §9, §10)."""

from __future__ import annotations

import unittest

from pricing_engine.config import risk_level_for
from pricing_engine.core.feature_engineering import price_floor
from pricing_engine.intelligence.conflict_detector import detect_conflicts
from pricing_engine.intelligence.risk_engine import assess_risk
from pricing_engine.schemas.input_schema import (
    MarketInput,
    PricingContextInput,
    ProductInput,
)


def make_product(**overrides) -> ProductInput:
    data = {
        "product_id": "SKU-R",
        "current_price": 100000,
        "cost_price": 65000,
        "inventory_quantity": 100,
        "inventory_days": 20,
        "sales_velocity": 1.0,
        "safety_stock": 50,
    }
    data.update(overrides)
    return ProductInput(**data)


class TestRiskEngine(unittest.TestCase):
    def test_margin_below_minimum_is_flagged(self) -> None:
        report = assess_risk(
            price=70000,
            product=make_product(),
            market=MarketInput(competitor_price=98000, confidence_score=0.9),
            context=PricingContextInput(),
        )
        codes = {factor["code"] for factor in report.factors}
        self.assertIn("MARGIN_BELOW_MIN", codes)

    def test_low_confidence_is_flagged(self) -> None:
        report = assess_risk(
            price=95000,
            product=make_product(),
            market=MarketInput(competitor_price=98000, confidence_score=0.2),
            context=PricingContextInput(),
        )
        codes = {factor["code"] for factor in report.factors}
        self.assertIn("LOW_DATA_CONFIDENCE", codes)

    def test_large_price_change_flagged(self) -> None:
        report = assess_risk(
            price=118000,
            product=make_product(),
            market=MarketInput(competitor_price=98000, confidence_score=0.9),
            context=PricingContextInput(),
        )
        codes = {factor["code"] for factor in report.factors}
        self.assertIn("HIGH_PRICE_CHANGE", codes)

    def test_insufficient_forecast_triggers_uncertainty(self) -> None:
        report = assess_risk(
            price=95000,
            product=make_product(),
            market=MarketInput(competitor_price=98000, confidence_score=0.9),
            context=PricingContextInput(),
            forecast={"status": "INSUFFICIENT_DATA", "demand": None, "mae": 0.0},
        )
        codes = {factor["code"] for factor in report.factors}
        self.assertIn("FORECAST_UNCERTAINTY", codes)

    def test_score_within_bounds_and_level_consistent(self) -> None:
        report = assess_risk(
            price=95000,
            product=make_product(),
            market=MarketInput(competitor_price=98000, confidence_score=0.9),
            context=PricingContextInput(),
        )
        self.assertGreaterEqual(report.score, 0.0)
        self.assertLessEqual(report.score, 100.0)
        self.assertEqual(report.level, risk_level_for(report.score))

    def test_critical_risk_blocks_execution(self) -> None:
        report = assess_risk(
            price=55000,
            product=make_product(),
            market=MarketInput(competitor_price=30000, confidence_score=0.1),
            context=PricingContextInput(),
            forecast={"status": "INSUFFICIENT_DATA"},
        )
        self.assertIn(report.level, {"HIGH", "CRITICAL"})
        self.assertTrue(report.requires_review)
        if report.level == "CRITICAL":
            self.assertFalse(report.execution_allowed)


class TestConflictDetection(unittest.TestCase):
    def test_floor_violation_rejects_candidate(self) -> None:
        ctx = PricingContextInput()
        report = detect_conflicts(
            price=70000,
            product=make_product(),
            market=MarketInput(),
            context=ctx,
            floor_price=price_floor(65000, ctx),
            strategy="PROFIT_MAXIMIZATION",
        )
        codes = {item["code"] for item in report.conflicts}
        self.assertIn("FLOOR_VIOLATION", codes)
        self.assertEqual(report.resolution, "REJECT_CANDIDATE")

    def test_competitive_strategy_without_market_conflicts(self) -> None:
        ctx = PricingContextInput()
        report = detect_conflicts(
            price=95000,
            product=make_product(),
            market=MarketInput(),
            context=ctx,
            floor_price=price_floor(65000, ctx),
            strategy="COMPETITIVE_PRICING",
        )
        codes = {item["code"] for item in report.conflicts}
        self.assertIn("MARKET_RULE_CONFLICT", codes)
        self.assertEqual(report.resolution, "APPLY_WITH_WARNING")

    def test_no_conflict_for_valid_price(self) -> None:
        ctx = PricingContextInput()
        report = detect_conflicts(
            price=100000,
            product=make_product(),
            market=MarketInput(competitor_price=98000, confidence_score=0.9),
            context=ctx,
            floor_price=price_floor(65000, ctx),
            strategy="COMPETITIVE_PRICING",
        )
        self.assertFalse(report.has_conflict)
        self.assertEqual(report.resolution, "NONE")


if __name__ == "__main__":
    unittest.main()
