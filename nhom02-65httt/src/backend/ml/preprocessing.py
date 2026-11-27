"""Tien xu ly du lieu ERP va lich su gia, cong thuc gia san Pmin."""

from __future__ import annotations

from collections.abc import Iterable


def clean_price_history(rows: Iterable[dict]) -> list[dict]:
    """Loc bo ban ghi lich su gia thieu gia tri hoac gia <= 0."""
    out: list[dict] = []
    for row in rows:
        price = row.get("price")
        if price is None or price <= 0:
            continue
        out.append({"sku": row.get("sku"), "date": row.get("date"), "price": float(price)})
    return out


def compute_pmin(cost: float, fee_rate: float = 0.05, margin: float = 0.1) -> float:
    """Tinh gia san Pmin = cost / (1 - fee_rate - margin) dam bao bien loi nhuan sau phi kenh."""
    if cost < 0:
        raise ValueError("cost khong duoc am.")
    denominator = 1.0 - fee_rate - margin
    if denominator <= 0:
        raise ValueError("fee_rate + margin phai nho hon 1.")
    return round(cost / denominator, 2)
