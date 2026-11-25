"""Pricing Conflict Detection (WORK_SPEC §10).

Phát hiện xung đột thay vì âm thầm chọn một rule, để người duyệt nhìn thấy
vấn đề trước khi giá được thực thi.
"""

from __future__ import annotations

from ..core.feature_engineering import margin_of, price_change_ratio
from ..schemas.input_schema import MarketInput, PricingContextInput, ProductInput
from ..schemas.output_schema import ConflictReport

_CRITICAL_CODES = {
    "FLOOR_VIOLATION",
    "MIN_MARGIN_CONFLICT",
    "PRICE_CHANGE_LIMIT",
    "CHANNEL_CONFLICT",
}


def _conflict(
    code: str,
    severity: str,
    description: str,
    affected_price: float | None = None,
    required_price: float | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "code": code,
        "severity": severity,
        "description": description,
    }
    if affected_price is not None:
        item["affected_price"] = round(affected_price, 2)
    if required_price is not None:
        item["required_price"] = round(required_price, 2)
    return item


def detect_conflicts(
    *,
    price: float,
    product: ProductInput,
    market: MarketInput,
    context: PricingContextInput,
    floor_price: float | None,
    strategy: str,
) -> ConflictReport:
    """Trả về các xung đột phát hiện được và cách xử lý đề xuất."""
    conflicts: list[dict[str, object]] = []
    margin = margin_of(price, product.cost_price, context.channel_fee_rate)
    change = price_change_ratio(price, product.current_price)

    if context.channel_fee_rate + context.min_margin >= 1.0:
        conflicts.append(
            _conflict(
                "CHANNEL_CONFLICT",
                "CRITICAL",
                "Phí kênh cộng biên tối thiểu không còn chỗ cho giá vốn.",
            )
        )

    if floor_price is not None and price < floor_price - 1e-9:
        conflicts.append(
            _conflict(
                "FLOOR_VIOLATION",
                "HIGH",
                "Giá ứng viên thấp hơn giá sàn.",
                affected_price=price,
                required_price=floor_price,
            )
        )

    if margin < context.min_margin - 1e-9:
        conflicts.append(
            _conflict(
                "MIN_MARGIN_CONFLICT",
                "CRITICAL",
                "Giá ứng viên không đạt biên lợi nhuận tối thiểu.",
                affected_price=price,
                required_price=product.cost_price
                / max(1e-9, 1.0 - context.channel_fee_rate - context.min_margin),
            )
        )

    if abs(change) > context.max_price_change_percent + 1e-9:
        conflicts.append(
            _conflict(
                "PRICE_CHANGE_LIMIT",
                "HIGH",
                f"Mức thay đổi giá {change:+.1%} vượt giới hạn "
                f"{context.max_price_change_percent:.0%}.",
                affected_price=price,
            )
        )

    if strategy == "COMPETITIVE_PRICING" and not market.is_usable:
        conflicts.append(
            _conflict(
                "MARKET_RULE_CONFLICT",
                "MEDIUM",
                "Chiến lược cạnh tranh được chọn nhưng dữ liệu đối thủ "
                "không đủ tin cậy.",
            )
        )

    if strategy == "PROFIT_MAXIMIZATION" and change < -1e-9:
        conflicts.append(
            _conflict(
                "STRATEGY_OBJECTIVE_CONFLICT",
                "MEDIUM",
                "Chiến lược tối đa hóa lợi nhuận nhưng giá đề xuất lại giảm.",
            )
        )

    if strategy == "INVENTORY_CLEARANCE" and change > 1e-9:
        conflicts.append(
            _conflict(
                "STRATEGY_OBJECTIVE_CONFLICT",
                "MEDIUM",
                "Chiến lược xả hàng nhưng giá đề xuất lại tăng.",
            )
        )

    if product.inventory_days >= 90.0 and strategy == "PROFIT_MAXIMIZATION":
        conflicts.append(
            _conflict(
                "INVENTORY_STRATEGY_CONFLICT",
                "MEDIUM",
                "Tồn kho cao nhưng vẫn theo đuổi tối đa hóa lợi nhuận.",
            )
        )

    codes = {str(item["code"]) for item in conflicts}
    if not conflicts:
        resolution = "NONE"
    elif codes & _CRITICAL_CODES:
        resolution = "REJECT_CANDIDATE"
    else:
        resolution = "APPLY_WITH_WARNING"

    return ConflictReport(
        has_conflict=bool(conflicts),
        conflicts=conflicts,
        resolution=resolution,
    )
