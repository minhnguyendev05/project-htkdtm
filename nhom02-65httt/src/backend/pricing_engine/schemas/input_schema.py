"""Input contract của Pricing Engine (WORK_SPEC §16.1).

Engine nhận dữ liệu đã chuẩn hóa, không phụ thuộc trực tiếp frontend hay ERP.
Mọi lớp đều có ``from_dict`` để dễ tích hợp với JSON/API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


class ValidationError(ValueError):
    """Dữ liệu đầu vào không hợp lệ (WORK_SPEC §20 TC08)."""


def _as_float(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"'{name}' phải là số, nhận được {value!r}.") from exc


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"'{name}' phải là object/dict.")
    return value


@dataclass
class ProductInput:
    """Thông tin sản phẩm và trạng thái tồn kho."""

    product_id: str
    current_price: float
    cost_price: float
    product_name: str = ""
    category: str = "GENERAL"
    inventory_quantity: float = 0.0
    inventory_days: float = 0.0
    sales_velocity: float = 0.0
    product_lifecycle: str = "MATURE"
    product_position: str = "standard"  # premium | standard | value
    safety_stock: float = 0.0
    demand_growth: float = 0.0

    def validate(self) -> None:
        if not str(self.product_id).strip():
            raise ValidationError("product.product_id không được rỗng.")
        if self.current_price <= 0:
            raise ValidationError("product.current_price phải lớn hơn 0.")
        if self.cost_price < 0:
            raise ValidationError("product.cost_price không được âm.")
        if self.inventory_quantity < 0:
            raise ValidationError("product.inventory_quantity không được âm.")
        if self.inventory_days < 0:
            raise ValidationError("product.inventory_days không được âm.")
        if self.sales_velocity < 0:
            raise ValidationError("product.sales_velocity không được âm.")
        if self.product_position not in {"premium", "standard", "value"}:
            raise ValidationError(
                "product.product_position phải là premium|standard|value."
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProductInput":
        data = _require_mapping(data, "product")
        if "product_id" not in data:
            raise ValidationError("Thiếu product.product_id.")
        if "current_price" not in data:
            raise ValidationError("Thiếu product.current_price.")
        if "cost_price" not in data:
            raise ValidationError("Thiếu product.cost_price.")
        product = cls(
            product_id=str(data["product_id"]),
            product_name=str(data.get("product_name", "")),
            category=str(data.get("category", "GENERAL")),
            current_price=_as_float(data["current_price"], "current_price"),
            cost_price=_as_float(data["cost_price"], "cost_price"),
            inventory_quantity=_as_float(
                data.get("inventory_quantity", 0), "inventory_quantity"
            ),
            inventory_days=_as_float(data.get("inventory_days", 0), "inventory_days"),
            sales_velocity=_as_float(data.get("sales_velocity", 0), "sales_velocity"),
            product_lifecycle=str(data.get("product_lifecycle", "MATURE")),
            product_position=str(data.get("product_position", "standard")),
            safety_stock=_as_float(data.get("safety_stock", 0), "safety_stock"),
            demand_growth=_as_float(data.get("demand_growth", 0), "demand_growth"),
        )
        product.validate()
        return product


@dataclass
class MarketInput:
    """Dữ liệu thị trường/đối thủ đã thu thập."""

    competitor_price: float | None = None
    confidence_score: float = 0.0
    freshness_hours: float = 0.0
    source_reliability: float = 0.0

    @property
    def has_competitor(self) -> bool:
        return self.competitor_price is not None and self.competitor_price > 0

    @property
    def is_usable(self) -> bool:
        """Dữ liệu đối thủ chỉ dùng được khi đủ tin cậy (WORK_SPEC §5.4)."""
        from ..config import MIN_COMPETITOR_CONFIDENCE

        return self.has_competitor and self.confidence_score >= MIN_COMPETITOR_CONFIDENCE

    def validate(self) -> None:
        if self.competitor_price is not None and self.competitor_price < 0:
            raise ValidationError("market.competitor_price không được âm.")
        if not 0.0 <= self.confidence_score <= 1.0:
            raise ValidationError("market.confidence_score phải trong khoảng 0..1.")
        if self.freshness_hours < 0:
            raise ValidationError("market.freshness_hours không được âm.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "MarketInput":
        if data is None:
            return cls()
        data = _require_mapping(data, "market")
        raw_price = data.get("competitor_price")
        market = cls(
            competitor_price=None if raw_price is None else _as_float(raw_price, "competitor_price"),
            confidence_score=_as_float(data.get("confidence_score", 0), "confidence_score"),
            freshness_hours=_as_float(data.get("freshness_hours", 0), "freshness_hours"),
            source_reliability=_as_float(
                data.get("source_reliability", 0), "source_reliability"
            ),
        )
        market.validate()
        return market


@dataclass
class SalesInput:
    """Lịch sử bán hàng dùng cho dự báo nhu cầu."""

    historical_sales: list[float] = field(default_factory=list)
    period_days: int = 7

    def validate(self) -> None:
        for value in self.historical_sales:
            if value < 0:
                raise ValidationError("sales.historical_sales không được có giá trị âm.")
        if self.period_days <= 0:
            raise ValidationError("sales.period_days phải lớn hơn 0.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SalesInput":
        if data is None:
            return cls()
        data = _require_mapping(data, "sales")
        raw_history: Iterable[Any] = data.get("historical_sales", []) or []
        sales = cls(
            historical_sales=[_as_float(v, "historical_sales") for v in raw_history],
            period_days=int(data.get("period_days", 7) or 7),
        )
        sales.validate()
        return sales


@dataclass
class PricingContextInput:
    """Ràng buộc kinh doanh và tham số vận hành."""

    channel_fee_rate: float = 0.0
    min_margin: float = 0.15
    max_price_change_percent: float = 0.2
    price_step: float = 1000.0
    strategy: str | None = None
    objective: str = "BALANCED"

    def validate(self) -> None:
        if not 0.0 <= self.channel_fee_rate < 1.0:
            raise ValidationError("pricing_context.channel_fee_rate phải trong khoảng 0..1.")
        if not 0.0 <= self.min_margin < 1.0:
            raise ValidationError("pricing_context.min_margin phải trong khoảng 0..1.")
        if self.max_price_change_percent <= 0:
            raise ValidationError(
                "pricing_context.max_price_change_percent phải lớn hơn 0."
            )
        if self.price_step <= 0:
            raise ValidationError("pricing_context.price_step phải lớn hơn 0.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "PricingContextInput":
        if data is None:
            return cls()
        data = _require_mapping(data, "pricing_context")
        strategy = data.get("strategy")
        context = cls(
            channel_fee_rate=_as_float(data.get("channel_fee_rate", 0), "channel_fee_rate"),
            min_margin=_as_float(data.get("min_margin", 0.15), "min_margin"),
            max_price_change_percent=_as_float(
                data.get("max_price_change_percent", 0.2), "max_price_change_percent"
            ),
            price_step=_as_float(data.get("price_step", 1000), "price_step"),
            strategy=None if strategy in (None, "", "AUTO") else str(strategy),
            objective=str(data.get("objective", "BALANCED")),
        )
        context.validate()
        return context


@dataclass
class PricingRequest:
    """Một yêu cầu định giá hoàn chỉnh."""

    product: ProductInput
    market: MarketInput = field(default_factory=MarketInput)
    sales: SalesInput = field(default_factory=SalesInput)
    context: PricingContextInput = field(default_factory=PricingContextInput)
    simulation: bool = False

    @property
    def is_simulated(self) -> bool:
        """Mọi kết quả không đến từ dữ liệu thật đều phải gắn nhãn."""
        return True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PricingRequest":
        payload = _require_mapping(payload, "payload")
        if "product" not in payload:
            raise ValidationError("Payload thiếu 'product'.")
        return cls(
            product=ProductInput.from_dict(payload["product"]),
            market=MarketInput.from_dict(payload.get("market")),
            sales=SalesInput.from_dict(payload.get("sales")),
            context=PricingContextInput.from_dict(payload.get("pricing_context")),
            simulation=bool(payload.get("simulation", False)),
        )

    def validate(self) -> None:
        self.product.validate()
        self.market.validate()
        self.sales.validate()
        self.context.validate()
