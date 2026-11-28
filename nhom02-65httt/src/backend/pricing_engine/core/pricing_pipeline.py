"""Pricing Pipeline — điều phối toàn bộ engine (WORK_SPEC §3, §18 Phase 1).

Luồng: validate -> feature -> forecast -> strategy -> candidates -> scoring ->
constraints -> risk -> conflict -> explanation -> recommendation.
"""

from __future__ import annotations

from ..config import (
    CLEARANCE_EXTRA_MAX_MARKDOWN,
    CLEARANCE_INVENTORY_DAYS,
    CLEARANCE_MIN_MARKDOWN,
    CLEARANCE_SEVERITY_SPAN_DAYS,
    COMPETITIVE_PRICE_BAND,
    DEFENSIVE_MAX_ABOVE_COMPETITOR,
    ENGINE_VERSION,
)
from ..explainability.explanation_engine import build_explanation
from ..forecasting.demand_forecaster import forecast_demand
from ..intelligence.conflict_detector import detect_conflicts
from ..intelligence.risk_engine import assess_risk
from ..optimization.constraints import evaluate_constraints
from ..optimization.scoring import score_candidates
from ..schemas.input_schema import (
    MarketInput,
    PricingContextInput,
    PricingRequest,
    ProductInput,
)
from ..schemas.output_schema import (
    CandidatePrice,
    ConflictReport,
    Explanation,
    PricingResult,
    RiskReport,
)
from ..strategies.base import STRATEGIES
from ..strategies.selector import select_strategy
from .candidate_generator import build_candidates
from .feature_engineering import margin_of, price_change_ratio, price_floor


class PricingPipeline:
    """Engine định giá độc lập, không truy cập DB hay thực thi giá."""

    def __init__(self, default_elasticity: float | None = None) -> None:
        # Elasticity là module P1; mặc định None để dùng nhu cầu từ dự báo.
        self.default_elasticity = default_elasticity

    # -- internal helpers -------------------------------------------------
    def _no_safe_price(
        self,
        request: PricingRequest,
        *,
        strategy: str,
        reasons: list[str],
        strategy_confidence: float,
        floor_price: float | None,
        forecast: dict[str, object],
        risk: RiskReport | None = None,
        conflicts: ConflictReport | None = None,
        candidates: list[CandidatePrice] | None = None,
        message: str = "",
    ) -> PricingResult:
        risk = risk or RiskReport()
        conflicts = conflicts or ConflictReport()
        explanation = Explanation(
            summary=message
            or "Không tìm được mức giá nào thoả đồng thời giá sàn, biên tối "
            "thiểu và giới hạn biến động giá.",
            strategy=strategy,
            positive_factors=[],
            negative_factors=[
                "Không có ứng viên hợp lệ trong phạm vi cho phép",
            ],
            constraints_applied=["Giá sàn (floor price)"],
            rejected_candidates=[],
            decision_confidence=0.0,
        )
        return PricingResult(
            product_id=request.product.product_id,
            current_price=request.product.current_price,
            recommended_price=None,
            price_change_percent=0.0,
            strategy=strategy,
            strategy_reason=reasons,
            strategy_confidence=strategy_confidence,
            recommendation_status="NO_SAFE_PRICE",
            confidence=0.0,
            risk=risk,
            conflicts=conflicts,
            explanation=explanation,
            floor_price=floor_price,
            min_margin_satisfied=False,
            max_price_change_satisfied=self._max_change_ok(
                request, request.product.current_price
            ),
            best_score=0.0,
            candidates=candidates or [],
            forecast=forecast,
            metadata=self._metadata(request),
        )

    @staticmethod
    def _narrow_to_strategy_band(
        strategy: str,
        prices: list[float],
        product: ProductInput,
        market: MarketInput,
        context: PricingContextInput,
    ) -> list[float]:
        """Thu hẹp ứng viên theo vị thế giá mà chiến lược yêu cầu.

        - Competitive: giữ giá trong dải ±5% quanh giá đối thủ.
        - Defensive: không vượt giá đối thủ quá 2%.
        - Inventory Clearance: chỉ xét giá thấp hơn giá hiện tại, độ sâu tăng
          theo mức độ tồn kho (tối đa bằng giới hạn biến động).
        - Demand Capture / Premium: không tự cắt giá.

        Nếu dải không còn ứng viên nào thì giữ nguyên danh sách để engine vẫn
        trả được giá trong giới hạn cứng.
        """
        current = product.current_price
        competitor = market.competitor_price

        if strategy == "INVENTORY_CLEARANCE":
            extra = min(
                CLEARANCE_EXTRA_MAX_MARKDOWN,
                max(
                    0.0,
                    (product.inventory_days - CLEARANCE_INVENTORY_DAYS)
                    / CLEARANCE_SEVERITY_SPAN_DAYS,
                ),
            )
            markdown = min(
                context.max_price_change_percent, CLEARANCE_MIN_MARKDOWN + extra
            )
            narrowed = [price for price in prices if price <= current * (1 - markdown)]
            # Không đạt được độ sâu mong muốn (thường do giá sàn chặn) thì
            # vẫn đi xuống sát giá sàn thay vì giữ nguyên giá cũ.
            return narrowed or [min(prices)]

        if strategy in {"DEMAND_CAPTURE", "PREMIUM_PRICING"}:
            narrowed = [price for price in prices if price >= current * 0.999]
            return narrowed or prices

        if not market.is_usable or competitor is None or competitor <= 0:
            return prices

        if strategy == "COMPETITIVE_PRICING":
            low = competitor * (1.0 - COMPETITIVE_PRICE_BAND)
            high = competitor * (1.0 + COMPETITIVE_PRICE_BAND)
        elif strategy == "DEFENSIVE_PRICING":
            low = 0.0
            high = competitor * (1.0 + DEFENSIVE_MAX_ABOVE_COMPETITOR)
        else:
            return prices

        narrowed = [price for price in prices if low <= price <= high]
        return narrowed or prices

    @staticmethod
    def _max_change_ok(request: PricingRequest, price: float) -> bool:
        change = abs(price_change_ratio(price, request.product.current_price))
        return change <= request.context.max_price_change_percent + 1e-9

    @staticmethod
    def _metadata(request: PricingRequest) -> dict[str, object]:
        return {
            "engine_version": ENGINE_VERSION,
            "evaluation_type": "SIMULATED" if request.simulation else "DEMO",
            "disclaimer": "Kết quả do engine mô phỏng, không phải dữ liệu thực tế.",
        }

    # -- public API -------------------------------------------------------
    def run(self, request: PricingRequest) -> PricingResult:
        """Chạy pipeline cho một yêu cầu định giá.

        Raises:
            ValidationError: dữ liệu đầu vào không hợp lệ (TC08). Không bao
                giờ trả recommendation giả khi dữ liệu sai.
        """
        request.validate()
        product = request.product
        market = request.market
        context = request.context

        floor = price_floor(product.cost_price, context)
        forecast = forecast_demand(request.sales.historical_sales)
        selection = select_strategy(product, market, context)
        strategy = selection.strategy

        if floor is None:
            return self._no_safe_price(
                request,
                strategy=strategy,
                reasons=selection.reasons
                + ["Phí kênh và biên tối thiểu không còn chỗ cho giá vốn."],
                strategy_confidence=selection.confidence,
                floor_price=None,
                forecast=forecast,
                conflicts=ConflictReport(
                    has_conflict=True,
                    conflicts=[
                        {
                            "code": "CHANNEL_CONFLICT",
                            "severity": "CRITICAL",
                            "description": "channel_fee_rate + min_margin >= 1",
                        }
                    ],
                    resolution="REJECT_CANDIDATE",
                ),
            )

        reference_price = (
            market.competitor_price if market.is_usable else product.current_price
        )
        anchor = STRATEGIES[strategy].anchor(float(reference_price or product.current_price))

        prices = build_candidates(
            current_price=product.current_price,
            floor_price=floor,
            competitor_price=market.competitor_price if market.is_usable else None,
            strategy_anchor=anchor,
            max_price_change_percent=context.max_price_change_percent,
            price_step=context.price_step,
        )
        prices = self._narrow_to_strategy_band(
            strategy, prices, product, market, context
        )

        if not prices:
            return self._no_safe_price(
                request,
                strategy=strategy,
                reasons=selection.reasons
                + ["Giá sàn cao hơn mức giá tối đa được phép."],
                strategy_confidence=selection.confidence,
                floor_price=floor,
                forecast=forecast,
            )

        forecast_daily_demand = forecast.get("demand")
        scored = score_candidates(
            prices,
            product=product,
            market=market,
            context=context,
            strategy=strategy,
            expected_daily_demand=(
                float(forecast_daily_demand)
                if isinstance(forecast_daily_demand, (int, float))
                else None
            ),
            elasticity=self.default_elasticity,
        )

        # Đánh dấu ứng viên vi phạm ràng buộc cứng (vẫn hiển thị để giải thích).
        feasible: list[CandidatePrice] = []
        for candidate in scored:
            violations = evaluate_constraints(
                candidate.price,
                current_price=product.current_price,
                cost_price=product.cost_price,
                context=context,
                floor_price=floor,
            )
            if violations:
                candidate.feasible = False
                candidate.rejection_reason = "; ".join(violations)
            else:
                feasible.append(candidate)

        if not feasible:
            return self._no_safe_price(
                request,
                strategy=strategy,
                reasons=selection.reasons
                + ["Mọi ứng viên đều vi phạm ràng buộc cứng."],
                strategy_confidence=selection.confidence,
                floor_price=floor,
                forecast=forecast,
                candidates=scored,
            )

        best = feasible[0]
        risk = assess_risk(
            price=best.price,
            product=product,
            market=market,
            context=context,
            forecast=forecast,
        )
        conflicts = detect_conflicts(
            price=best.price,
            product=product,
            market=market,
            context=context,
            floor_price=floor,
            strategy=strategy,
        )
        explanation = build_explanation(
            selected=best,
            candidates=scored,
            product=product,
            market=market,
            context=context,
            strategy=strategy,
            risk=risk,
            conflicts=conflicts,
        )

        margin = margin_of(best.price, product.cost_price, context.channel_fee_rate)
        status = "READY"
        if (
            risk.requires_review
            or not risk.execution_allowed
            or conflicts.resolution == "REJECT_CANDIDATE"
        ):
            status = "REVIEW_REQUIRED"

        confidence = round(
            min(selection.confidence, explanation.decision_confidence), 4
        )

        return PricingResult(
            product_id=product.product_id,
            current_price=product.current_price,
            recommended_price=best.price,
            price_change_percent=price_change_ratio(
                best.price, product.current_price
            )
            * 100.0,
            strategy=strategy,
            strategy_reason=selection.reasons,
            strategy_confidence=selection.confidence,
            recommendation_status=status,
            confidence=confidence,
            risk=risk,
            conflicts=conflicts,
            explanation=explanation,
            floor_price=floor,
            min_margin_satisfied=margin >= context.min_margin - 1e-9,
            max_price_change_satisfied=self._max_change_ok(request, best.price),
            best_score=best.score,
            candidates=scored,
            forecast=forecast,
            metadata=self._metadata(request),
        )


def run_pricing(request: PricingRequest) -> PricingResult:
    """Hàm tiện dụng chạy engine một lần."""
    return PricingPipeline().run(request)
