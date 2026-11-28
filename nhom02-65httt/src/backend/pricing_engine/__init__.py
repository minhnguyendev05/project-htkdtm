"""AI Pricing Engine — lõi định giá của ERP Smart Pricing.

Chạy độc lập với dữ liệu JSON/dict, không phụ thuộc FastAPI, database hay
frontend (WORK_SPEC §17, §23.12).

Ví dụ nhanh:

    from pricing_engine import run_pricing, PricingRequest

    result = run_pricing(PricingRequest.from_dict(payload))
    print(result.to_dict())
"""

from __future__ import annotations

from .config import ENGINE_VERSION
from .core.pricing_pipeline import PricingPipeline, run_pricing
from .schemas.input_schema import (
    MarketInput,
    PricingContextInput,
    PricingRequest,
    ProductInput,
    SalesInput,
    ValidationError,
)
from .schemas.output_schema import PricingResult

__all__ = [
    "ENGINE_VERSION",
    "PricingPipeline",
    "run_pricing",
    "PricingRequest",
    "ProductInput",
    "MarketInput",
    "SalesInput",
    "PricingContextInput",
    "PricingResult",
    "ValidationError",
]
