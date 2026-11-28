"""Test pipeline đầu-cuối theo bảng test tối thiểu WORK_SPEC §20."""

from __future__ import annotations

import unittest

from pricing_engine import PricingRequest, ValidationError, run_pricing
from pricing_engine.core.candidate_generator import build_candidates
from pricing_engine.core.feature_engineering import price_change_ratio, price_floor
from pricing_engine.forecasting.demand_forecaster import forecast_demand
from pricing_engine.optimization.constraints import evaluate_constraints
from pricing_engine.schemas.input_schema import PricingContextInput


def make_payload(
    *,
    product: dict | None = None,
    market: dict | None = None,
    sales: dict | None = None,
    context: dict | None = None,
) -> dict:
    base_product = {
        "product_id": "SKU-1",
        "current_price": 100000,
        "cost_price": 65000,
        "inventory_quantity": 120,
        "inventory_days": 20,
        "sales_velocity": 1.0,
        "safety_stock": 50,
        "demand_growth": 0.0,
        "product_position": "standard",
    }
    base_market = {
        "competitor_price": 98000,
        "confidence_score": 0.9,
        "freshness_hours": 2,
    }
    base_sales = {"historical_sales": [10, 11, 12, 12, 13, 14, 13], "period_days": 7}
    base_context = {
        "channel_fee_rate": 0.05,
        "min_margin": 0.15,
        "max_price_change_percent": 0.2,
        "price_step": 1000,
    }
    base_product.update(product or {})
    base_market.update(market or {})
    base_sales.update(sales or {})
    base_context.update(context or {})
    return {
        "product": base_product,
        "market": base_market,
        "sales": base_sales,
        "pricing_context": base_context,
    }


class TestPipelineConstraints(unittest.TestCase):
    def test_tc01_below_floor_is_rejected(self) -> None:
        ctx = PricingContextInput(channel_fee_rate=0.05, min_margin=0.15)
        floor = price_floor(65000, ctx)
        self.assertIsNotNone(floor)
        violations = evaluate_constraints(
            80000,
            current_price=100000,
            cost_price=65000,
            context=ctx,
            floor_price=floor,
        )
        self.assertIn("Giá dưới giá sàn", violations)

        result = run_pricing(PricingRequest.from_dict(make_payload()))
        self.assertIsNotNone(result.recommended_price)
        self.assertGreaterEqual(result.recommended_price, floor - 1e-6)

    def test_tc02_below_min_margin_is_rejected(self) -> None:
        ctx = PricingContextInput(channel_fee_rate=0.05, min_margin=0.15)
        violations = evaluate_constraints(
            70000,
            current_price=100000,
            cost_price=65000,
            context=ctx,
            floor_price=price_floor(65000, ctx),
        )
        self.assertIn("Biên lợi nhuận dưới mức tối thiểu", violations)

    def test_tc06_price_change_limit_is_enforced(self) -> None:
        ctx = PricingContextInput(
            channel_fee_rate=0.05, min_margin=0.15, max_price_change_percent=0.2
        )
        violations = evaluate_constraints(
            200000,
            current_price=100000,
            cost_price=65000,
            context=ctx,
            floor_price=price_floor(65000, ctx),
        )
        self.assertIn("Vượt giới hạn biến động giá", violations)

        result = run_pricing(PricingRequest.from_dict(make_payload()))
        for candidate in result.candidates:
            if candidate.feasible:
                change = abs(candidate.price - 100000) / 100000
                self.assertLessEqual(change, 0.2 + 1e-9)


class TestPipelineStrategy(unittest.TestCase):
    def test_tc03_overstock_slow_moving_uses_clearance(self) -> None:
        payload = make_payload(
            product={
                "inventory_quantity": 1200,
                "inventory_days": 120,
                "sales_velocity": 0.1,
            }
        )
        result = run_pricing(PricingRequest.from_dict(payload))
        self.assertEqual(result.strategy, "INVENTORY_CLEARANCE")
        self.assertTrue(result.strategy_reason)

    def test_tc04_high_demand_low_stock_uses_demand_capture(self) -> None:
        payload = make_payload(
            product={
                "inventory_quantity": 10,
                "safety_stock": 50,
                "demand_growth": 0.3,
                "inventory_days": 5,
            }
        )
        result = run_pricing(PricingRequest.from_dict(payload))
        self.assertEqual(result.strategy, "DEMAND_CAPTURE")

    def test_clearance_cuts_price_deeper_for_older_stock(self) -> None:
        payload = make_payload(
            product={
                "inventory_quantity": 1200,
                "inventory_days": 150,
                "sales_velocity": 0.1,
            }
        )
        result = run_pricing(PricingRequest.from_dict(payload))
        self.assertEqual(result.strategy, "INVENTORY_CLEARANCE")
        self.assertIsNotNone(result.recommended_price)
        self.assertLessEqual(result.recommended_price, 100000 * 0.9)

    def test_competitive_strategy_stays_near_competitor(self) -> None:
        payload = make_payload(
            product={"current_price": 200000, "cost_price": 120000},
            market={"competitor_price": 182000, "confidence_score": 0.95},
        )
        result = run_pricing(PricingRequest.from_dict(payload))
        self.assertEqual(result.strategy, "COMPETITIVE_PRICING")
        self.assertIsNotNone(result.recommended_price)
        gap = abs(result.recommended_price - 182000) / 182000
        self.assertLessEqual(gap, 0.05 + 1e-6)

    def test_tc05_low_confidence_does_not_silently_use_market(self) -> None:
        payload = make_payload(
            market={"competitor_price": 60000, "confidence_score": 0.1}
        )
        result = run_pricing(PricingRequest.from_dict(payload))
        self.assertNotEqual(result.strategy, "COMPETITIVE_PRICING")
        codes = {factor["code"] for factor in result.risk.factors}
        self.assertIn("LOW_DATA_CONFIDENCE", codes)


class TestPipelineDataQuality(unittest.TestCase):
    def test_tc07_missing_history_returns_insufficient_data(self) -> None:
        forecast = forecast_demand([5, 6])
        self.assertEqual(forecast["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(forecast["predicted_demand"])

        result = run_pricing(
            PricingRequest.from_dict(
                make_payload(sales={"historical_sales": []})
            )
        )
        self.assertEqual(result.forecast["status"], "INSUFFICIENT_DATA")
        self.assertIsNotNone(result.recommended_price)

    def test_tc08_negative_sales_raises_validation_error(self) -> None:
        payload = make_payload(sales={"historical_sales": [10, -3, 12]})
        with self.assertRaises(ValidationError):
            PricingRequest.from_dict(payload)

    def test_tc10_candidate_equal_to_current_has_zero_change(self) -> None:
        prices = build_candidates(
            current_price=100000,
            floor_price=81250,
            competitor_price=98000,
            strategy_anchor=100000,
            max_price_change_percent=0.2,
            price_step=1000,
        )
        self.assertIn(100000, prices)
        self.assertAlmostEqual(price_change_ratio(100000, 100000), 0.0)

    def test_tc12_impossible_constraints_return_no_safe_price(self) -> None:
        payload = make_payload(
            context={"channel_fee_rate": 0.05, "min_margin": 0.95}
        )
        result = run_pricing(PricingRequest.from_dict(payload))
        self.assertEqual(result.recommendation_status, "NO_SAFE_PRICE")
        self.assertIsNone(result.recommended_price)

    def test_result_metadata_marks_simulated_data(self) -> None:
        result = run_pricing(PricingRequest.from_dict(make_payload()))
        self.assertIn(result.metadata["evaluation_type"], {"DEMO", "SIMULATED"})
        self.assertEqual(result.metadata["engine_version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
