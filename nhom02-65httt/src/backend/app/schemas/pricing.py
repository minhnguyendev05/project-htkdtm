"""Smart Pricing rules, preview/run requests, recommendations, and approval schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.common import ApiModel

RuleType = Literal[
    "FLASH_SALE",
    "SKIMMING",
    "CLEARANCE",
    "COMPETITOR_MATCH",
    "MARGIN_GUARD",
]
RuleStatus = Literal["DRAFT", "ACTIVE", "PAUSED", "ARCHIVED"]
PricingObjective = Literal["PROFIT", "COMPETITIVE", "CLEAR_STOCK"]
AlgorithmType = Literal["RULE_BASED", "ML_ASSISTED"]
CompetitorStrategy = Literal["IGNORE", "STAY_WITHIN_RANGE", "MATCH_MEDIAN"]
StockStrategy = Literal["NEUTRAL", "CLEAR_SLOW_MOVING"]


class PricingRuleCreate(ApiModel):
    """Payload to create a new pricing strategy or guardrail rule."""

    name: str = Field(min_length=1, max_length=150)
    rule_type: RuleType
    priority: int = Field(default=100, ge=1, le=10000)
    scope_label: str = Field(min_length=1, max_length=200)
    category_id: UUID | None = None
    channel_id: UUID | None = None
    min_margin: Decimal = Field(ge=Decimal("0"), lt=Decimal("1"))
    max_price_change_pct: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    approval_required: bool = True
    status: RuleStatus = "DRAFT"
    starts_at: datetime
    ends_at: datetime | None = None

    @field_validator("name", "scope_label")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Giá trị không được để trống.")
        return cleaned

    @model_validator(mode="after")
    def _validate_window(self) -> PricingRuleCreate:
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("endsAt phải lớn hơn startsAt.")
        return self


class PricingRuleUpdate(ApiModel):
    """Partial update payload for an existing pricing rule."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    rule_type: RuleType | None = None
    priority: int | None = Field(default=None, ge=1, le=10000)
    scope_label: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: UUID | None = None
    channel_id: UUID | None = None
    min_margin: Decimal | None = Field(default=None, ge=Decimal("0"), lt=Decimal("1"))
    max_price_change_pct: Decimal | None = Field(default=None, gt=Decimal("0"), le=Decimal("1"))
    approval_required: bool | None = None
    status: RuleStatus | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("name", "scope_label")
    @classmethod
    def _clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Giá trị không được để trống.")
        return cleaned


class PricingRuleStatusUpdate(ApiModel):
    """Status transition payload for a pricing rule."""

    status: RuleStatus


class PricingRuleRead(ApiModel):
    """Persisted pricing rule representation."""

    id: UUID
    name: str
    rule_type: str
    priority: int
    scope_label: str
    category_id: UUID | None
    channel_id: UUID | None
    min_margin: Decimal
    max_price_change_pct: Decimal
    approval_required: bool
    status: str
    starts_at: datetime
    ends_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PricingPreviewRequest(ApiModel):
    """Request payload for non-persisted pricing preview (catalog batch or ad-hoc)."""

    sku_ids: list[UUID] | None = Field(default=None, max_length=200)
    channel_id: UUID | None = None
    cost: Decimal | None = Field(default=None, ge=Decimal("0"))
    current_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    competitor_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    channel_fee_rate: Decimal = Field(
        default=Decimal("0.0500"),
        ge=Decimal("0"),
        lt=Decimal("1"),
    )
    objective: PricingObjective = "PROFIT"
    target_margin: Decimal = Field(default=Decimal("0.1800"), gt=Decimal("0"), lt=Decimal("1"))
    mode: AlgorithmType = "RULE_BASED"
    competitor_strategy: CompetitorStrategy = "STAY_WITHIN_RANGE"
    stock_strategy: StockStrategy = "NEUTRAL"
    price_step: Decimal | None = Field(default=None, gt=Decimal("0"))

    @model_validator(mode="after")
    def _validate_mode(self) -> PricingPreviewRequest:
        has_catalog = bool(self.sku_ids) and self.channel_id is not None
        has_adhoc = self.cost is not None
        if not has_catalog and not has_adhoc:
            raise ValueError(
                "Cần cung cấp (skuIds + channelId) để xem trước theo danh mục "
                "hoặc cung cấp cost để tính thử trực tiếp."
            )
        return self


class PricingPreviewItemRead(ApiModel):
    """Single SKU preview row computed by the AI Pricing Engine without DB writes."""

    sku_id: UUID | None = None
    sku_code: str
    product_name: str
    current_price: Decimal
    unit_cost: Decimal
    channel_fee_rate: Decimal
    floor_price: Decimal | None
    suggested_price: Decimal | None
    expected_profit_per_unit: Decimal | None
    expected_margin: Decimal | None
    competitor_median: Decimal | None
    competitor_sample_count: int
    competitor_fresh: bool
    data_quality: str
    strategy: str
    risk_level: str
    no_safe_price: bool
    summary: str


class PricingPreviewResponse(ApiModel):
    """Aggregated response for /pricing/preview."""

    mode: Literal["CATALOG", "ADHOC"]
    channel_id: UUID | None = None
    channel_name: str | None = None
    channel_fee_rate: Decimal
    pmin: Decimal | None = None
    suggested_price: Decimal | None = None
    items: list[PricingPreviewItemRead]


class PricingRunRequest(ApiModel):
    """Request payload to run AI Pricing Engine and persist PriceRecommendation rows."""

    sku_ids: list[UUID] = Field(min_length=1, max_length=200)
    channel_id: UUID
    rule_id: UUID | None = None
    objective: PricingObjective = "PROFIT"
    target_margin: Decimal = Field(default=Decimal("0.1800"), gt=Decimal("0"), lt=Decimal("1"))
    mode: AlgorithmType = "RULE_BASED"
    competitor_strategy: CompetitorStrategy = "STAY_WITHIN_RANGE"
    stock_strategy: StockStrategy = "NEUTRAL"
    submit_for_approval: bool = False


class PriceApprovalRead(ApiModel):
    """Recorded manager decision on a price recommendation."""

    id: UUID
    recommendation_id: UUID
    reviewer_id: UUID | None
    reviewer_name: str
    decision: str
    adjusted_price: Decimal | None
    reason: str | None
    decided_at: datetime


class RecommendationRead(ApiModel):
    """Persisted price recommendation matching the frontend Recommendation contract."""

    id: UUID
    sku_id: UUID
    sku_code: str
    product_name: str
    channel_id: UUID
    channel_name: str
    rule_id: UUID | None
    status: str
    current_price: Decimal
    floor_price: Decimal
    recommended_price: Decimal
    expected_profit_per_unit: Decimal
    expected_margin: Decimal
    unit_cost: Decimal
    channel_fee_rate: Decimal
    competitor_median: Decimal | None
    target_margin: Decimal
    predicted_demand: Decimal | None
    data_quality: str
    algorithm_type: str
    algorithm_version: str
    explanation: dict[str, Any]
    created_by: str
    created_at: datetime
    expires_at: datetime
    approvals: list[PriceApprovalRead] = Field(default_factory=list)


class PricingRunResponse(ApiModel):
    """Summary returned after executing a Smart Pricing batch run."""

    job_id: str
    requested_count: int
    results: list[RecommendationRead]
    no_safe_price_sku_codes: list[str]


class RecommendationDecisionRequest(ApiModel):
    """Optional adjustment and reason when approving or rejecting a recommendation."""

    adjusted_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _clean_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ModelTrainRequest(ApiModel):
    """Request payload to run LinearRegression vs XGBoost evaluation on SalesRecord data."""

    product_id: UUID | None = None
    channel_id: UUID | None = None
    split_ratio: float = Field(default=0.8, ge=0.5, le=0.95)


class ModelRunRead(ApiModel):
    """Persisted ML training run evaluation metrics (MAE, RMSE)."""

    id: UUID
    model_name: str
    model_version: str
    algorithm_type: str
    feature_columns_json: list[str]
    train_samples: int
    test_samples: int
    mae: Decimal
    rmse: Decimal
    artifact_path: str | None
    trained_at: datetime
