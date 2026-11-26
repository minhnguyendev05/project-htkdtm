"""Tien xu ly du lieu ERP va lich su gia, cong thuc gia san Pmin."""
from typing import Iterable


def clean_price_history(rows: Iterable[dict]) -> list[dict]:
    out = []
    for r in rows:
        price = r.get("price")
        if price is None or price <= 0:
            continue
        out.append({"sku": r.get("sku"), "date": r.get("date"), "price": float(price)})
    return out


def compute_pmin(cost: float, fee_rate: float = 0.05, margin: float = 0.1) -> float:
    """Gia san = cost * (1 + phi + bien loi nhuan)."""
    return round(cost * (1 + fee_rate + margin), 2)
"""