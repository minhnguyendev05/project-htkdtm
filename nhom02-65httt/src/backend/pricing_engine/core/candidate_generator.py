"""Sinh danh sách giá ứng viên (WORK_SPEC §5.2).

Ứng viên được tạo từ nhiều nguồn: giá hiện tại, giá sàn, giá đối thủ, các mức
tăng/giảm theo phần trăm và mức neo của chiến lược. Bước giá cấu hình được
theo sản phẩm/khoảng giá, không cố định.
"""

from __future__ import annotations

from typing import Iterable

from ..config import CANDIDATE_PERCENT_STEPS


def round_to_step(value: float, step: float) -> float:
    """Làm tròn về bội số gần nhất của ``step``."""
    if step <= 0:
        return value
    return round(value / step) * step


def build_candidates(
    *,
    current_price: float,
    floor_price: float,
    competitor_price: float | None,
    strategy_anchor: float,
    max_price_change_percent: float,
    price_step: float,
) -> list[float]:
    """Trả về danh sách giá ứng viên đã sắp xếp, khử trùng lặp.

    Mọi ứng viên nằm trong ``[lower, upper]`` với:
      - ``lower`` = max(giá sàn, giá hiện tại * (1 - giới hạn))
      - ``upper`` = giá hiện tại * (1 + giới hạn)

    Danh sách rỗng nghĩa là không có mức giá hợp lệ nào — pipeline phải trả
    ``NO_SAFE_PRICE`` thay vì bịa ra một con số (WORK_SPEC §20 TC12).
    """
    upper_bound = current_price * (1.0 + max_price_change_percent)
    lower_bound = max(floor_price, current_price * (1.0 - max_price_change_percent))
    if lower_bound > upper_bound:
        return []

    raw: list[float] = [current_price]
    for pct in CANDIDATE_PERCENT_STEPS:
        raw.append(current_price * (1.0 + pct))
    raw.append(strategy_anchor)
    if competitor_price is not None and competitor_price > 0:
        raw.extend(
            [competitor_price, competitor_price * 0.98, competitor_price * 1.02]
        )

    candidates: list[float] = []
    seen: set[float] = set()

    def _add(value: float) -> None:
        if value <= 0:
            return
        clamped = min(max(value, lower_bound), upper_bound)
        # Giá sàn luôn là mốc hợp lệ tuyệt đối, không làm tròn xuống dưới nó.
        rounded = max(round_to_step(clamped, price_step), floor_price)
        rounded = round(rounded, 2)
        if rounded > upper_bound or rounded < floor_price:
            return
        if rounded in seen:
            return
        seen.add(rounded)
        candidates.append(rounded)

    for value in raw:
        _add(value)

    return sorted(candidates)


def dedupe_prices(values: Iterable[float]) -> list[float]:
    """Khử trùng lặp và sắp xếp danh sách giá."""
    return sorted({round(float(value), 2) for value in values})
