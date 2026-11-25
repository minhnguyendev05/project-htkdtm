"""Chọn chiến lược thích ứng theo trạng thái sản phẩm (WORK_SPEC §4.4).

Không chiến lược nào xử lý mọi sản phẩm; mỗi quyết định đều kèm lý do để
giải thích được (WORK_SPEC §4.5).
"""

from __future__ import annotations

from ..config import (
    CLEARANCE_INVENTORY_DAYS,
    CLEARANCE_MAX_SALES_VELOCITY,
    COMPETITOR_RELIABLE_CONFIDENCE,
    DEMAND_CAPTURE_MIN_GROWTH,
)
from ..schemas.input_schema import MarketInput, PricingContextInput, ProductInput
from ..schemas.output_schema import StrategySelection
from .base import STRATEGIES


def _confidence(reasons: list[str], market: MarketInput) -> float:
    """Độ tin cậy tăng theo số tín hiệu khớp và chất lượng dữ liệu thị trường."""
    score = 0.55 + 0.10 * len(reasons) + 0.10 * max(0.0, market.confidence_score)
    return round(min(0.95, score), 4)


def select_strategy(
    product: ProductInput,
    market: MarketInput,
    context: PricingContextInput,
) -> StrategySelection:
    """Chọn chiến lược phù hợp nhất với trạng thái sản phẩm.

    Thứ tự ưu tiên bám baseline trong spec; có thêm nhánh phòng thủ khi đối thủ
    hạ giá sâu để dùng đủ 6 chiến lược của §4.2.
    """
    if context.strategy in STRATEGIES:
        return StrategySelection(
            strategy=context.strategy,
            reasons=["Chiến lược được chỉ định từ cấu hình yêu cầu."],
            confidence=1.0,
        )

    # 1) Tồn kho cao + bán chậm -> xả hàng.
    if (
        product.inventory_days >= CLEARANCE_INVENTORY_DAYS
        and product.sales_velocity < CLEARANCE_MAX_SALES_VELOCITY
    ):
        reasons = ["Tồn kho vượt ngưỡng mục tiêu"]
        if product.inventory_days >= CLEARANCE_INVENTORY_DAYS:
            reasons.append("Tuổi tồn kho cao")
        reasons.append("Tốc độ bán thấp")
        return StrategySelection(
            strategy="INVENTORY_CLEARANCE",
            reasons=reasons,
            confidence=_confidence(reasons, market),
        )

    # 2) Nhu cầu tăng + tồn dưới mức an toàn -> khai thác nhu cầu.
    if (
        product.demand_growth >= DEMAND_CAPTURE_MIN_GROWTH
        and product.inventory_quantity < product.safety_stock
    ):
        reasons = [
            "Nhu cầu tăng trưởng ở mức cao",
            "Tồn kho thấp hơn mức an toàn",
        ]
        return StrategySelection(
            strategy="DEMAND_CAPTURE",
            reasons=reasons,
            confidence=_confidence(reasons, market),
        )

    # 3) Đối thủ hạ giá sâu nhưng dữ liệu đủ tin cậy -> phòng thủ.
    if market.is_usable and market.competitor_price is not None:
        if market.competitor_price <= product.current_price * 0.90:
            reasons = [
                "Giá đối thủ thấp hơn đáng kể so với giá hiện tại",
                "Dữ liệu đối thủ đủ độ tin cậy",
            ]
            return StrategySelection(
                strategy="DEFENSIVE_PRICING",
                reasons=reasons,
                confidence=_confidence(reasons, market),
            )

    # 4) Có dữ liệu đối thủ đáng tin cậy -> cạnh tranh.
    if market.confidence_score >= COMPETITOR_RELIABLE_CONFIDENCE and market.has_competitor:
        reasons = [
            "Có dữ liệu giá đối thủ",
            "Độ tin cậy dữ liệu đối thủ ở mức cao",
        ]
        return StrategySelection(
            strategy="COMPETITIVE_PRICING",
            reasons=reasons,
            confidence=_confidence(reasons, market),
        )

    # 5) Sản phẩm định vị premium -> giữ giá cao.
    if product.product_position == "premium":
        reasons = ["Sản phẩm được định vị phân khúc cao cấp"]
        return StrategySelection(
            strategy="PREMIUM_PRICING",
            reasons=reasons,
            confidence=_confidence(reasons, market),
        )

    # 6) Mặc định.
    reasons = ["Không có tín hiệu đặc biệt nào vượt ngưỡng chuyển chiến lược"]
    return StrategySelection(
        strategy="PROFIT_MAXIMIZATION",
        reasons=reasons,
        confidence=_confidence(reasons, market),
    )
