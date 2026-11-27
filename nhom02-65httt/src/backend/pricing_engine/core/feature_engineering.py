"""Feature engineering — các đại lượng dẫn xuất dùng chung.

Giữ một nguồn công thức duy nhất cho giá sàn, biên lợi nhuận và biến động giá
để mọi module khác không tự tính lại theo cách khác nhau.
"""

from __future__ import annotations

from typing import Protocol


class _ContextLike(Protocol):
    channel_fee_rate: float
    min_margin: float


def price_floor(cost_price: float, context: _ContextLike) -> float | None:
    """Giá sàn để đạt ``min_margin`` sau khi trừ phí kênh.

    Giá bán P thoả: (P - cost - P*fee) / P >= margin
    => P >= cost / (1 - fee - margin)

    Trả ``None`` khi mẫu số <= 0: không tồn tại giá nào đạt ràng buộc.
    """
    denominator = 1.0 - context.channel_fee_rate - context.min_margin
    if denominator <= 0:
        return None
    return cost_price / denominator


def unit_profit(price: float, cost_price: float, channel_fee_rate: float) -> float:
    """Lợi nhuận gộp trên một đơn vị sau phí kênh."""
    return price - cost_price - price * channel_fee_rate


def margin_of(price: float, cost_price: float, channel_fee_rate: float) -> float:
    """Biên lợi nhuận trên giá bán (0..1)."""
    if price <= 0:
        return 0.0
    return unit_profit(price, cost_price, channel_fee_rate) / price


def price_change_ratio(new_price: float, current_price: float) -> float:
    """Mức thay đổi giá so với giá hiện tại (dạng tỷ lệ, có dấu)."""
    if current_price <= 0:
        return 0.0
    return (new_price - current_price) / current_price
