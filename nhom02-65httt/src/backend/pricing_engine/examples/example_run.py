"""Demo 3 sản phẩm theo WORK_SPEC §22.

Chạy:  python pricing_engine/examples/example_run.py
(từ thư mục ``nhom02-65httt/src/backend``)
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# Console Windows mặc định cp1252 — chuyển sang UTF-8 để in được tiếng Việt.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from pricing_engine import PricingRequest, run_pricing  # noqa: E402

DEMO_REQUESTS: list[dict] = [
    {
        "label": "Product A — Nhu cầu cao / Tồn kho thấp",
        "payload": {
            "product": {
                "product_id": "SKU-A",
                "product_name": "Wireless Mouse",
                "category": "Electronics",
                "current_price": 100000,
                "cost_price": 65000,
                "inventory_quantity": 12,
                "inventory_days": 8,
                "sales_velocity": 1.4,
                "safety_stock": 40,
                "demand_growth": 0.28,
                "product_position": "standard",
            },
            "market": {
                "competitor_price": 99000,
                "confidence_score": 0.85,
                "freshness_hours": 2,
                "source_reliability": 0.9,
            },
            "sales": {"historical_sales": [18, 20, 21, 23, 24, 26, 27], "period_days": 7},
            "pricing_context": {
                "channel_fee_rate": 0.05,
                "min_margin": 0.15,
                "max_price_change_percent": 0.2,
                "price_step": 1000,
            },
            "simulation": False,
        },
    },
    {
        "label": "Product B — Tồn kho cao / Bán chậm",
        "payload": {
            "product": {
                "product_id": "SKU-B",
                "product_name": "Desk Lamp",
                "category": "Home",
                "current_price": 100000,
                "cost_price": 60000,
                "inventory_quantity": 1200,
                "inventory_days": 120,
                "sales_velocity": 0.15,
                "safety_stock": 100,
                "demand_growth": -0.05,
                "product_position": "standard",
            },
            "market": {
                "competitor_price": 98000,
                "confidence_score": 0.7,
                "freshness_hours": 5,
                "source_reliability": 0.8,
            },
            "sales": {"historical_sales": [4, 3, 5, 4, 3, 4, 2], "period_days": 7},
            "pricing_context": {
                "channel_fee_rate": 0.05,
                "min_margin": 0.15,
                "max_price_change_percent": 0.2,
                "price_step": 1000,
            },
            "simulation": False,
        },
    },
    {
        "label": "Product C — Áp lực đối thủ mạnh",
        "payload": {
            "product": {
                "product_id": "SKU-C",
                "product_name": "Mechanical Keyboard",
                "category": "Electronics",
                "current_price": 200000,
                "cost_price": 120000,
                "inventory_quantity": 200,
                "inventory_days": 20,
                "sales_velocity": 1.0,
                "safety_stock": 50,
                "demand_growth": 0.02,
                "product_position": "standard",
            },
            "market": {
                "competitor_price": 182000,
                "confidence_score": 0.92,
                "freshness_hours": 1,
                "source_reliability": 0.95,
            },
            "sales": {"historical_sales": [12, 13, 12, 14, 13, 15, 14], "period_days": 7},
            "pricing_context": {
                "channel_fee_rate": 0.05,
                "min_margin": 0.15,
                "max_price_change_percent": 0.2,
                "price_step": 1000,
            },
            "simulation": False,
        },
    },
]


def main() -> None:
    for demo in DEMO_REQUESTS:
        result = run_pricing(PricingRequest.from_dict(demo["payload"]))
        print("=" * 72)
        print(demo["label"])
        print("=" * 72)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()
