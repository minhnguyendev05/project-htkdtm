"""Ràng buộc cứng (WORK_SPEC §5.4, §23.4).

Điểm số không được phép vượt qua các điều kiện này: giá sàn, biên tối thiểu và
giới hạn biến động giá.
"""

from __future__ import annotations

from ..core.feature_engineering import margin_of, price_change_ratio
from ..schemas.input_schema import PricingContextInput


def evaluate_constraints(
    price: float,
    *,
    current_price: float,
    cost_price: float,
    context: PricingContextInput,
    floor_price: float | None,
) -> list[str]:
    """Trả về danh sách lý do vi phạm (rỗng nghĩa là hợp lệ)."""
    violations: list[str] = []

    if floor_price is not None and price < floor_price - 1e-9:
        violations.append("Giá dưới giá sàn")

    margin = margin_of(price, cost_price, context.channel_fee_rate)
    if margin < context.min_margin - 1e-9:
        violations.append("Biên lợi nhuận dưới mức tối thiểu")

    change = abs(price_change_ratio(price, current_price))
    if change > context.max_price_change_percent + 1e-9:
        violations.append("Vượt giới hạn biến động giá")

    return violations


def is_feasible(
    price: float,
    *,
    current_price: float,
    cost_price: float,
    context: PricingContextInput,
    floor_price: float | None,
) -> bool:
    """``True`` khi giá thoả toàn bộ ràng buộc cứng."""
    return not evaluate_constraints(
        price,
        current_price=current_price,
        cost_price=cost_price,
        context=context,
        floor_price=floor_price,
    )
