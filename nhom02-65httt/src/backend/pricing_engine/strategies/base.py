"""Định nghĩa 6 chiến lược định giá (WORK_SPEC §4.2)."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import STRATEGY_ANCHOR_MULTIPLIER


@dataclass(frozen=True)
class Strategy:
    key: str
    label: str
    goal: str
    anchor_multiplier: float

    def anchor(self, reference_price: float) -> float:
        """Mức giá neo của chiến lược so với giá tham chiếu."""
        return reference_price * self.anchor_multiplier


STRATEGIES: dict[str, Strategy] = {
    "PROFIT_MAXIMIZATION": Strategy(
        key="PROFIT_MAXIMIZATION",
        label="Tối đa hóa lợi nhuận",
        goal="Tối đa biên lợi nhuận khi nhu cầu và dữ liệu ổn định.",
        anchor_multiplier=STRATEGY_ANCHOR_MULTIPLIER["PROFIT_MAXIMIZATION"],
    ),
    "COMPETITIVE_PRICING": Strategy(
        key="COMPETITIVE_PRICING",
        label="Định giá cạnh tranh",
        goal="Duy trì vị thế giá so với đối thủ đáng tin cậy.",
        anchor_multiplier=STRATEGY_ANCHOR_MULTIPLIER["COMPETITIVE_PRICING"],
    ),
    "INVENTORY_CLEARANCE": Strategy(
        key="INVENTORY_CLEARANCE",
        label="Xả hàng tồn kho",
        goal="Giải phóng hàng tồn khi tồn cao và bán chậm.",
        anchor_multiplier=STRATEGY_ANCHOR_MULTIPLIER["INVENTORY_CLEARANCE"],
    ),
    "DEMAND_CAPTURE": Strategy(
        key="DEMAND_CAPTURE",
        label="Khai thác nhu cầu",
        goal="Tận dụng nhu cầu tăng khi tồn kho thấp.",
        anchor_multiplier=STRATEGY_ANCHOR_MULTIPLIER["DEMAND_CAPTURE"],
    ),
    "PREMIUM_PRICING": Strategy(
        key="PREMIUM_PRICING",
        label="Định giá cao cấp",
        goal="Duy trì định vị premium cho sản phẩm lợi thế.",
        anchor_multiplier=STRATEGY_ANCHOR_MULTIPLIER["PREMIUM_PRICING"],
    ),
    "DEFENSIVE_PRICING": Strategy(
        key="DEFENSIVE_PRICING",
        label="Định giá phòng thủ",
        goal="Bảo vệ thị phần khi đối thủ hạ giá mạnh.",
        anchor_multiplier=STRATEGY_ANCHOR_MULTIPLIER["DEFENSIVE_PRICING"],
    ),
}


def get_strategy(key: str) -> Strategy:
    """Lấy chiến lược theo mã, mặc định về tối đa hóa lợi nhuận."""
    return STRATEGIES.get(key, STRATEGIES["PROFIT_MAXIMIZATION"])


def strategy_anchor(key: str, reference_price: float) -> float:
    """Giá neo của chiến lược tại một giá tham chiếu."""
    return get_strategy(key).anchor(reference_price)
