"""Smart Pricing business service connecting ORM data, AI Pricing Engine, and approvals."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from pricing_engine import ENGINE_VERSION, PricingRequest
from pricing_engine import run_pricing as run_engine
from pricing_engine.evaluation.closed_loop import (
    evaluate as evaluate_closed_loop_point,
)
from pricing_engine.evaluation.closed_loop import (
    summarize_closed_loop,
)
from pricing_engine.schemas.output_schema import PricingResult
from pricing_engine.simulation.digital_twin import simulate_price_curve
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.base import utc_now
from app.ml.demand_baseline import forecast_demand_ml
from app.models.erp import Category, CostComponent, Inventory, Product, SupplierProduct
from app.models.market import ChannelProduct, CompetitorPrice, SalesChannel, SalesRecord
from app.models.pricing import ModelRun, PriceApproval, PriceRecommendation, PricingRule
from app.models.user import User
from app.schemas.pricing import (
    ClosedLoopItemRead,
    ClosedLoopSummaryRead,
    ModelRunRead,
    ModelRunSummaryRead,
    PriceApprovalRead,
    PricingPreviewItemRead,
    PricingPreviewRequest,
    PricingPreviewResponse,
    PricingRunRequest,
    PricingRunResponse,
    PricingSimulateRequest,
    PricingSimulateResponse,
    RecommendationDecisionRequest,
    RecommendationRead,
    SimulationPointRead,
)
from app.services.audit import record_audit_log

COMPETITOR_MAX_AGE_HOURS = 24.0
DEFAULT_MAX_PRICE_CHANGE_PCT = Decimal("0.2000")
RECOMMENDATION_TTL_HOURS = 24
_MONEY_QUANT = Decimal("0.01")
_RATE_QUANT = Decimal("0.0001")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _rate(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(_RATE_QUANT, rounding=ROUND_HALF_UP)


def _price_step_for(reference_price: float, override: Decimal | None = None) -> float:
    if override is not None:
        return float(override)
    return 1000.0 if reference_price >= 1000.0 else 1.0


def _resolve_unit_cost(db: Session, product: Product) -> Decimal:
    cost_row = db.scalar(select(CostComponent).where(CostComponent.product_id == product.id))
    if cost_row is not None:
        total = (
            Decimal(cost_row.purchase_cost)
            + Decimal(cost_row.inbound_cost)
            + Decimal(cost_row.packaging_cost)
            + Decimal(cost_row.other_cost)
        )
        return _money(total)

    supplier_quote = db.scalar(
        select(SupplierProduct)
        .where(SupplierProduct.product_id == product.id)
        .order_by(SupplierProduct.is_preferred.desc(), SupplierProduct.updated_at.desc())
    )
    if supplier_quote is not None:
        return _money(supplier_quote.purchase_cost)

    return Decimal("0.00")


def _resolve_current_price(db: Session, product: Product, channel: SalesChannel) -> Decimal:
    listing = db.scalar(
        select(ChannelProduct).where(
            ChannelProduct.product_id == product.id,
            ChannelProduct.channel_id == channel.id,
        )
    )
    if listing is not None and listing.current_price > 0:
        return _money(listing.current_price)
    return _money(product.current_price)


def _collect_competitor_signal(
    db: Session,
    product: Product,
    channel: SalesChannel,
    *,
    now: datetime,
) -> dict[str, Any]:
    rows = db.scalars(
        select(CompetitorPrice)
        .where(
            CompetitorPrice.product_id == product.id,
            CompetitorPrice.marketplace_code == channel.code,
            CompetitorPrice.is_outlier.is_(False),
            CompetitorPrice.match_status != "REJECTED",
        )
        .order_by(CompetitorPrice.observed_at.desc())
    ).all()

    usable_prices: list[Decimal] = []
    confidences: list[float] = []
    fresh_count = 0
    newest_age_hours = 72.0

    for row in rows:
        price = row.effective_price if row.effective_price is not None else row.listed_price
        if price is None or price <= 0:
            continue
        age_hours = max(0.0, (now - _as_utc(row.observed_at)).total_seconds() / 3600.0)
        if not usable_prices:
            newest_age_hours = age_hours
        if age_hours <= COMPETITOR_MAX_AGE_HOURS:
            fresh_count += 1
        usable_prices.append(Decimal(price))
        conf_val = float(row.confidence)
        if conf_val > 1.0:
            conf_val = min(1.0, conf_val / 100.0)
        confidences.append(max(0.0, min(1.0, conf_val)))

    if not usable_prices:
        return {
            "median": None,
            "sample_count": 0,
            "fresh": False,
            "freshness_hours": 72.0,
            "confidence": 0.0,
            "data_quality": "LOW",
        }

    usable_prices.sort()
    mid = len(usable_prices) // 2
    if len(usable_prices) % 2 == 1:
        median_price = usable_prices[mid]
    else:
        median_price = (usable_prices[mid - 1] + usable_prices[mid]) / Decimal("2")

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.8
    is_fresh = fresh_count > 0
    if is_fresh and fresh_count >= 2:
        quality = "HIGH"
    elif len(usable_prices) >= 1:
        quality = "MEDIUM"
    else:
        quality = "LOW"

    return {
        "median": _money(median_price),
        "sample_count": len(usable_prices),
        "fresh": is_fresh,
        "freshness_hours": round(newest_age_hours, 2),
        "confidence": round(avg_confidence, 4),
        "data_quality": quality,
    }


def _collect_sales_signal(
    db: Session,
    product: Product,
    channel: SalesChannel,
) -> tuple[list[SalesRecord], list[float], float, float]:
    records = db.scalars(
        select(SalesRecord)
        .where(
            SalesRecord.product_id == product.id,
            SalesRecord.channel_id == channel.id,
        )
        .order_by(SalesRecord.order_date.desc())
        .limit(30)
    ).all()
    if not records:
        return [], [], 1.0, 0.0

    ordered = list(reversed(records))
    history = [float(max(0, r.quantity)) for r in ordered]
    avg_daily = sum(history) / len(history) if history else 1.0

    growth = 0.0
    if len(history) >= 4:
        split = len(history) // 2
        prev_avg = sum(history[:split]) / split
        recent_avg = sum(history[split:]) / (len(history) - split)
        if prev_avg > 0:
            growth = max(-0.5, min(1.0, (recent_avg - prev_avg) / prev_avg))

    return ordered, history, max(0.0, avg_daily), growth


def _resolve_active_rules_and_guards(
    db: Session,
    *,
    rule_id: UUID | None,
    category_id: UUID,
    channel_id: UUID,
    now: datetime,
) -> tuple[PricingRule | None, list[PricingRule], list[dict[str, Any]]]:
    """Resolve primary active rule, applicable MARGIN_GUARD rules, and priority/scope conflicts."""
    explicit_rule: PricingRule | None = None
    if rule_id is not None:
        explicit_rule = db.get(PricingRule, rule_id)
        if explicit_rule is None:
            raise NotFoundError("Không tìm thấy quy tắc định giá.")

    all_active = db.scalars(
        select(PricingRule)
        .where(PricingRule.status == "ACTIVE")
        .order_by(PricingRule.priority.asc(), PricingRule.created_at.desc())
    ).all()

    matching: list[PricingRule] = []
    for rule in all_active:
        starts = _as_utc(rule.starts_at)
        ends = _as_utc(rule.ends_at) if rule.ends_at is not None else None
        if starts > now or (ends is not None and ends < now):
            continue
        if rule.channel_id is not None and rule.channel_id != channel_id:
            continue
        if rule.category_id is not None and rule.category_id != category_id:
            continue
        matching.append(rule)

    guards = [rule for rule in matching if rule.rule_type == "MARGIN_GUARD"]
    non_guards = [rule for rule in matching if rule.rule_type != "MARGIN_GUARD"]

    rule_conflicts: list[dict[str, Any]] = []
    for idx, left in enumerate(non_guards):
        for right in non_guards[idx + 1 :]:
            if left.priority == right.priority and left.scope_label == right.scope_label:
                rule_conflicts.append(
                    {
                        "code": "RULE_PRIORITY_CONFLICT",
                        "priority": left.priority,
                        "scopeLabel": left.scope_label,
                        "rules": [left.name, right.name],
                    }
                )

    primary = explicit_rule or (non_guards[0] if non_guards else None)
    return primary, guards, rule_conflicts


def _select_strategy_override(
    objective: str,
    competitor_strategy: str,
    stock_strategy: str,
    mode: str,
) -> str | None:
    if objective == "CLEAR_STOCK" or stock_strategy == "CLEAR_SLOW_MOVING":
        return "INVENTORY_CLEARANCE"
    if objective == "COMPETITIVE" or competitor_strategy == "MATCH_MEDIAN":
        return "COMPETITIVE_PRICING"
    if mode == "ML_ASSISTED":
        return None
    return "PROFIT_MAXIMIZATION"


def _build_explanation_payload(
    *,
    engine_result: PricingResult,
    unit_cost: Decimal,
    channel_fee_rate: Decimal,
    floor_price: Decimal,
    competitor_median: Decimal | None,
    competitor_fresh: bool,
    data_quality: str,
    rule_conflicts: list[dict[str, Any]] | None = None,
    ml_model_used: str | None = None,
    ml_predicted_demand: float | None = None,
) -> dict[str, Any]:
    factors: list[dict[str, Any]] = [
        {
            "key": "unit_cost",
            "label": "Giá vốn đơn vị",
            "value": str(unit_cost),
            "format": "money",
            "impact": "raises_floor",
        },
        {
            "key": "channel_fee_rate",
            "label": "Phí kênh bán",
            "value": str(channel_fee_rate),
            "format": "percent",
            "impact": "raises_floor",
        },
        {
            "key": "floor_price",
            "label": "Giá sàn tối thiểu (Pmin)",
            "value": str(floor_price),
            "format": "money",
            "impact": "raises_floor",
        },
    ]
    if competitor_median is not None:
        factors.append(
            {
                "key": "competitor_median",
                "label": "Trung vị giá đối thủ",
                "value": str(competitor_median),
                "format": "money",
                "impact": "anchors_price",
            }
        )
    factors.append(
        {
            "key": "ai_strategy",
            "label": "Chiến lược AI",
            "value": engine_result.strategy,
            "impact": "neutral",
        }
    )
    factors.append(
        {
            "key": "risk_level",
            "label": "Mức rủi ro",
            "value": f"{engine_result.risk.level} ({round(engine_result.risk.score, 2)})",
            "impact": "neutral",
        }
    )

    summary = (
        engine_result.explanation.summary
        or (engine_result.strategy_reason[0] if engine_result.strategy_reason else "")
        or "Đề xuất giá được tính toán từ AI Pricing Engine."
    )

    return {
        "summary": summary,
        "factors": factors,
        "constraints": {
            "floorPassed": bool(engine_result.min_margin_satisfied),
            "maxChangePassed": bool(engine_result.max_price_change_satisfied),
            "competitorFresh": competitor_fresh,
        },
        "dataQuality": data_quality,
        "engine": {
            "strategy": engine_result.strategy,
            "strategyReason": list(engine_result.strategy_reason),
            "confidence": round(engine_result.confidence, 4),
            "risk": engine_result.risk.to_dict(),
            "conflicts": engine_result.conflicts.to_dict(),
            "ruleConflicts": rule_conflicts or [],
            "mlModelUsed": ml_model_used,
            "mlPredictedDemand": ml_predicted_demand,
            "forecast": engine_result.forecast,
        },
    }


def _evaluate_catalog_product(
    db: Session,
    *,
    product: Product,
    channel: SalesChannel,
    objective: str,
    target_margin: Decimal,
    mode: str,
    competitor_strategy: str,
    stock_strategy: str,
    active_rule: PricingRule | None,
    guard_rules: list[PricingRule],
    rule_conflicts: list[dict[str, Any]],
    now: datetime,
    price_step_override: Decimal | None = None,
) -> tuple[PricingResult, dict[str, Any]]:
    unit_cost = _resolve_unit_cost(db, product)
    current_price = _resolve_current_price(db, product, channel)
    category = db.get(Category, product.category_id)
    inventory = db.scalar(select(Inventory).where(Inventory.product_id == product.id))
    comp = _collect_competitor_signal(db, product, channel, now=now)
    sales_records, history, velocity, growth = _collect_sales_signal(db, product, channel)

    ml_model_used: str | None = None
    ml_predicted_demand: float | None = None
    if mode == "ML_ASSISTED" and sales_records:
        ml_forecast = forecast_demand_ml(sales_records, target_price=float(current_price))
        if ml_forecast is not None:
            ml_predicted_demand, growth, ml_model_used = ml_forecast

    available_qty = (
        max(0, inventory.on_hand_qty - inventory.reserved_qty) if inventory is not None else 50
    )
    safety_stock = inventory.reorder_point if inventory is not None else 10
    if stock_strategy == "CLEAR_SLOW_MOVING" or objective == "CLEAR_STOCK":
        inventory_days = float(
            inventory.days_of_supply if inventory and inventory.days_of_supply else 120
        )
        effective_velocity = min(velocity, 0.2) if history else 0.2
    elif inventory is not None and inventory.days_of_supply is not None:
        inventory_days = float(inventory.days_of_supply)
        effective_velocity = velocity
    else:
        effective_velocity = velocity if velocity > 0 else 1.0
        inventory_days = min(180.0, max(5.0, float(available_qty) / max(0.5, effective_velocity)))

    effective_min_margin = target_margin
    max_change_pct = DEFAULT_MAX_PRICE_CHANGE_PCT
    if active_rule is not None:
        effective_min_margin = max(effective_min_margin, Decimal(active_rule.min_margin))
        max_change_pct = Decimal(active_rule.max_price_change_pct)
    for guard in guard_rules:
        effective_min_margin = max(effective_min_margin, Decimal(guard.min_margin))
        max_change_pct = min(max_change_pct, Decimal(guard.max_price_change_pct))

    competitor_price = (
        float(comp["median"])
        if comp["median"] is not None and competitor_strategy != "IGNORE"
        else None
    )
    step = _price_step_for(float(current_price), price_step_override)
    strategy_override = _select_strategy_override(
        objective, competitor_strategy, stock_strategy, mode
    )

    engine_payload = {
        "product": {
            "product_id": product.sku_code,
            "product_name": product.name,
            "category": category.name if category is not None else "GENERAL",
            "current_price": float(current_price),
            "cost_price": float(unit_cost),
            "inventory_quantity": float(available_qty),
            "inventory_days": float(inventory_days),
            "sales_velocity": float(effective_velocity),
            "safety_stock": float(safety_stock),
            "demand_growth": float(growth if history else (0.05 if mode == "ML_ASSISTED" else 0.0)),
            "product_position": "standard",
        },
        "market": {
            "competitor_price": competitor_price,
            "confidence_score": float(comp["confidence"]) if competitor_price is not None else 0.0,
            "freshness_hours": float(comp["freshness_hours"]),
            "source_reliability": 0.9 if competitor_price is not None else 0.0,
        },
        "sales": {
            "historical_sales": history,
            "period_days": max(7, len(history)),
        },
        "pricing_context": {
            "channel_fee_rate": float(channel.fee_rate),
            "min_margin": float(effective_min_margin),
            "max_price_change_percent": float(max_change_pct),
            "price_step": step,
            "strategy": strategy_override,
            "objective": objective,
        },
        "simulation": False,
    }

    result = run_engine(PricingRequest.from_dict(engine_payload))
    return result, {
        "unit_cost": unit_cost,
        "current_price": current_price,
        "effective_min_margin": effective_min_margin,
        "competitor": comp,
        "rule_conflicts": rule_conflicts,
        "ml_model_used": ml_model_used,
        "ml_predicted_demand": ml_predicted_demand,
    }


def serialize_recommendation(
    db: Session,
    rec: PriceRecommendation,
    *,
    product: Product | None = None,
    channel: SalesChannel | None = None,
    approvals: list[PriceApproval] | None = None,
) -> RecommendationRead:
    """Build RecommendationRead from ORM models."""
    resolved_product = product or db.get(Product, rec.product_id)
    resolved_channel = channel or db.get(SalesChannel, rec.channel_id)
    if approvals is None:
        approvals = list(
            db.scalars(
                select(PriceApproval)
                .where(PriceApproval.recommendation_id == rec.id)
                .order_by(PriceApproval.decided_at.desc())
            ).all()
        )

    return RecommendationRead(
        id=rec.id,
        sku_id=rec.product_id,
        sku_code=resolved_product.sku_code if resolved_product is not None else str(rec.product_id),
        product_name=resolved_product.name if resolved_product is not None else "",
        channel_id=rec.channel_id,
        channel_name=resolved_channel.name if resolved_channel is not None else str(rec.channel_id),
        rule_id=rec.rule_id,
        status=rec.status,
        current_price=_money(rec.current_price),
        floor_price=_money(rec.floor_price),
        recommended_price=_money(rec.recommended_price),
        expected_profit_per_unit=_money(rec.expected_profit_per_unit),
        expected_margin=_rate(rec.expected_margin),
        unit_cost=_money(rec.unit_cost),
        channel_fee_rate=_rate(rec.channel_fee_rate),
        competitor_median=_money(rec.competitor_median) if rec.competitor_median else None,
        target_margin=_rate(rec.target_margin),
        predicted_demand=_money(rec.predicted_demand) if rec.predicted_demand is not None else None,
        data_quality=rec.data_quality,
        algorithm_type=rec.algorithm_type,
        algorithm_version=rec.algorithm_version,
        explanation=rec.explanation_json,
        created_by=rec.created_by,
        created_at=rec.created_at,
        expires_at=rec.expires_at,
        approvals=[PriceApprovalRead.model_validate(item) for item in approvals],
    )


def preview_pricing(db: Session, payload: PricingPreviewRequest) -> PricingPreviewResponse:
    """Run non-persisted pricing preview for catalog SKUs or ad-hoc inputs."""
    now = utc_now()

    if payload.sku_ids and payload.channel_id is not None:
        channel = db.get(SalesChannel, payload.channel_id)
        if channel is None:
            raise NotFoundError("Không tìm thấy kênh bán.")

        items: list[PricingPreviewItemRead] = []
        for sku_id in payload.sku_ids:
            product = db.get(Product, sku_id)
            if product is None:
                continue
            active_rule, guard_rules, rule_conflicts = _resolve_active_rules_and_guards(
                db,
                rule_id=None,
                category_id=product.category_id,
                channel_id=channel.id,
                now=now,
            )
            engine_res, ctx = _evaluate_catalog_product(
                db,
                product=product,
                channel=channel,
                objective=payload.objective,
                target_margin=payload.target_margin,
                mode=payload.mode,
                competitor_strategy=payload.competitor_strategy,
                stock_strategy=payload.stock_strategy,
                active_rule=active_rule,
                guard_rules=guard_rules,
                rule_conflicts=rule_conflicts,
                now=now,
                price_step_override=payload.price_step,
            )
            unit_cost: Decimal = ctx["unit_cost"]
            current_price: Decimal = ctx["current_price"]
            comp: dict[str, Any] = ctx["competitor"]
            floor_dec = (
                _money(engine_res.floor_price) if engine_res.floor_price is not None else None
            )
            rec_dec = (
                _money(engine_res.recommended_price)
                if engine_res.recommended_price is not None
                else None
            )
            profit_dec: Decimal | None = None
            margin_dec: Decimal | None = None
            if rec_dec is not None and rec_dec > 0:
                profit_dec = _money(rec_dec - unit_cost - rec_dec * Decimal(channel.fee_rate))
                margin_dec = _rate(profit_dec / rec_dec)

            items.append(
                PricingPreviewItemRead(
                    sku_id=product.id,
                    sku_code=product.sku_code,
                    product_name=product.name,
                    current_price=current_price,
                    unit_cost=unit_cost,
                    channel_fee_rate=_rate(channel.fee_rate),
                    floor_price=floor_dec,
                    suggested_price=rec_dec,
                    expected_profit_per_unit=profit_dec,
                    expected_margin=margin_dec,
                    competitor_median=comp["median"],
                    competitor_sample_count=comp["sample_count"],
                    competitor_fresh=comp["fresh"],
                    data_quality=comp["data_quality"],
                    strategy=engine_res.strategy,
                    risk_level=engine_res.risk.level,
                    no_safe_price=rec_dec is None
                    or engine_res.recommendation_status == "NO_SAFE_PRICE",
                    summary=engine_res.explanation.summary,
                )
            )

        first = items[0] if items else None
        return PricingPreviewResponse(
            mode="CATALOG",
            channel_id=channel.id,
            channel_name=channel.name,
            channel_fee_rate=_rate(channel.fee_rate),
            pmin=first.floor_price if first else None,
            suggested_price=first.suggested_price if first else None,
            items=items,
        )

    assert payload.cost is not None
    unit_cost = _money(payload.cost)
    fee_rate = _rate(payload.channel_fee_rate)
    denom = Decimal("1") - fee_rate - payload.target_margin
    base_current = payload.current_price
    if base_current is None:
        if payload.competitor_price is not None:
            base_current = _money(payload.competitor_price)
        elif denom > 0 and unit_cost > 0:
            base_current = _money(unit_cost / denom)
        else:
            base_current = _money(max(unit_cost, Decimal("1.00")))

    step = _price_step_for(float(base_current), payload.price_step)
    strategy_override = _select_strategy_override(
        payload.objective,
        payload.competitor_strategy,
        payload.stock_strategy,
        payload.mode,
    )
    engine_payload = {
        "product": {
            "product_id": "ADHOC-PREVIEW",
            "product_name": "Ad-hoc SKU Preview",
            "current_price": float(base_current),
            "cost_price": float(unit_cost),
            "inventory_quantity": 50,
            "inventory_days": 30,
            "sales_velocity": 1.0,
            "safety_stock": 10,
        },
        "market": {
            "competitor_price": (
                float(payload.competitor_price)
                if payload.competitor_price is not None
                and payload.competitor_strategy != "IGNORE"
                else None
            ),
            "confidence_score": 0.9 if payload.competitor_price is not None else 0.0,
            "freshness_hours": 1.0 if payload.competitor_price is not None else 72.0,
            "source_reliability": 0.9 if payload.competitor_price is not None else 0.0,
        },
        "sales": {"historical_sales": [], "period_days": 7},
        "pricing_context": {
            "channel_fee_rate": float(fee_rate),
            "min_margin": float(payload.target_margin),
            "max_price_change_percent": float(DEFAULT_MAX_PRICE_CHANGE_PCT),
            "price_step": step,
            "strategy": strategy_override,
            "objective": payload.objective,
        },
        "simulation": True,
    }
    engine_res = run_engine(PricingRequest.from_dict(engine_payload))
    floor_dec = _money(engine_res.floor_price) if engine_res.floor_price is not None else None
    rec_dec = (
        _money(engine_res.recommended_price) if engine_res.recommended_price is not None else None
    )
    profit_dec: Decimal | None = None
    margin_dec: Decimal | None = None
    if rec_dec is not None and rec_dec > 0:
        profit_dec = _money(rec_dec - unit_cost - rec_dec * fee_rate)
        margin_dec = _rate(profit_dec / rec_dec)

    item = PricingPreviewItemRead(
        sku_id=None,
        sku_code="ADHOC-PREVIEW",
        product_name="Ad-hoc SKU Preview",
        current_price=base_current,
        unit_cost=unit_cost,
        channel_fee_rate=fee_rate,
        floor_price=floor_dec,
        suggested_price=rec_dec,
        expected_profit_per_unit=profit_dec,
        expected_margin=margin_dec,
        competitor_median=_money(payload.competitor_price) if payload.competitor_price else None,
        competitor_sample_count=1 if payload.competitor_price is not None else 0,
        competitor_fresh=payload.competitor_price is not None,
        data_quality="MEDIUM" if payload.competitor_price is not None else "LOW",
        strategy=engine_res.strategy,
        risk_level=engine_res.risk.level,
        no_safe_price=rec_dec is None or engine_res.recommendation_status == "NO_SAFE_PRICE",
        summary=engine_res.explanation.summary,
    )
    return PricingPreviewResponse(
        mode="ADHOC",
        channel_id=None,
        channel_name=None,
        channel_fee_rate=fee_rate,
        pmin=floor_dec,
        suggested_price=rec_dec,
        items=[item],
    )


def execute_pricing_run(
    db: Session,
    payload: PricingRunRequest,
    *,
    current_user: User,
) -> PricingRunResponse:
    """Run AI Pricing Engine for requested SKUs and persist recommendations to DB."""
    channel = db.get(SalesChannel, payload.channel_id)
    if channel is None:
        raise NotFoundError("Không tìm thấy kênh bán.")

    if Decimal("1") - Decimal(channel.fee_rate) - payload.target_margin <= 0:
        raise AppError(
            code="VALIDATION_ERROR",
            message="Phí kênh cộng biên lợi nhuận mục tiêu >= 100%, không tồn tại giá an toàn.",
            status_code=422,
        )

    explicit_rule: PricingRule | None = None
    if payload.rule_id is not None:
        explicit_rule = db.get(PricingRule, payload.rule_id)
        if explicit_rule is None:
            raise NotFoundError("Không tìm thấy quy tắc định giá.")

    now = utc_now()
    expires_at = now + timedelta(hours=RECOMMENDATION_TTL_HOURS)
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    created_records: list[tuple[PriceRecommendation, Product]] = []
    no_safe_sku_codes: list[str] = []

    for sku_id in payload.sku_ids:
        product = db.get(Product, sku_id)
        if product is None:
            continue

        active_rule, guard_rules, rule_conflicts = _resolve_active_rules_and_guards(
            db,
            rule_id=explicit_rule.id if explicit_rule is not None else None,
            category_id=product.category_id,
            channel_id=channel.id,
            now=now,
        )

        engine_res, ctx = _evaluate_catalog_product(
            db,
            product=product,
            channel=channel,
            objective=payload.objective,
            target_margin=payload.target_margin,
            mode=payload.mode,
            competitor_strategy=payload.competitor_strategy,
            stock_strategy=payload.stock_strategy,
            active_rule=active_rule,
            guard_rules=guard_rules,
            rule_conflicts=rule_conflicts,
            now=now,
        )

        if (
            engine_res.recommended_price is None
            or engine_res.floor_price is None
            or engine_res.recommendation_status == "NO_SAFE_PRICE"
        ):
            no_safe_sku_codes.append(product.sku_code)
            continue

        unit_cost: Decimal = ctx["unit_cost"]
        current_price: Decimal = ctx["current_price"]
        effective_min_margin: Decimal = ctx["effective_min_margin"]
        comp: dict[str, Any] = ctx["competitor"]
        ml_predicted_demand: float | None = ctx["ml_predicted_demand"]

        floor_price = _money(engine_res.floor_price)
        recommended_price = _money(engine_res.recommended_price)
        expected_profit = _money(
            recommended_price - unit_cost - recommended_price * Decimal(channel.fee_rate)
        )
        expected_margin = (
            _rate(expected_profit / recommended_price)
            if recommended_price > 0
            else Decimal("0.0000")
        )
        forecast_demand_raw = (
            ml_predicted_demand
            if ml_predicted_demand is not None
            else engine_res.forecast.get("demand")
        )
        predicted_demand = (
            _money(forecast_demand_raw)
            if isinstance(forecast_demand_raw, (int, float))
            else None
        )

        requires_approval = (
            payload.submit_for_approval
            or engine_res.recommendation_status == "REVIEW_REQUIRED"
            or (active_rule is not None and active_rule.approval_required)
        )
        initial_status = "PENDING_APPROVAL" if requires_approval else "DRAFT"

        explanation_json = _build_explanation_payload(
            engine_result=engine_res,
            unit_cost=unit_cost,
            channel_fee_rate=_rate(channel.fee_rate),
            floor_price=floor_price,
            competitor_median=comp["median"],
            competitor_fresh=comp["fresh"],
            data_quality=comp["data_quality"],
            rule_conflicts=ctx["rule_conflicts"],
            ml_model_used=ctx["ml_model_used"],
            ml_predicted_demand=ml_predicted_demand,
        )

        rec = PriceRecommendation(
            product_id=product.id,
            channel_id=channel.id,
            rule_id=active_rule.id if active_rule is not None else None,
            status=initial_status,
            current_price=current_price,
            floor_price=floor_price,
            recommended_price=recommended_price,
            expected_profit_per_unit=expected_profit,
            expected_margin=expected_margin,
            unit_cost=unit_cost,
            channel_fee_rate=_rate(channel.fee_rate),
            competitor_median=comp["median"],
            target_margin=_rate(effective_min_margin),
            predicted_demand=predicted_demand,
            data_quality=comp["data_quality"],
            algorithm_type=payload.mode,
            algorithm_version=f"pricing-engine-{ENGINE_VERSION}",
            explanation_json=explanation_json,
            created_by=current_user.full_name,
            expires_at=expires_at,
        )
        db.add(rec)
        created_records.append((rec, product))

    record_audit_log(
        db,
        actor=current_user.full_name,
        action="RUN_PRICING",
        resource_type="price_recommendation",
        after_summary=(
            f"job={job_id}, channel={channel.code}, requested={len(payload.sku_ids)}, "
            f"created={len(created_records)}, noSafe={len(no_safe_sku_codes)}"
        ),
    )
    db.commit()

    results: list[RecommendationRead] = []
    for rec, product in created_records:
        db.refresh(rec)
        results.append(
            serialize_recommendation(db, rec, product=product, channel=channel, approvals=[])
        )

    return PricingRunResponse(
        job_id=job_id,
        requested_count=len(payload.sku_ids),
        results=results,
        no_safe_price_sku_codes=no_safe_sku_codes,
    )


def submit_recommendation_for_approval(
    db: Session,
    recommendation: PriceRecommendation,
    *,
    current_user: User,
) -> RecommendationRead:
    """Move a DRAFT recommendation into PENDING_APPROVAL."""
    now = utc_now()
    if _as_utc(recommendation.expires_at) <= now:
        recommendation.status = "EXPIRED"
        db.commit()
        raise ConflictError("Đề xuất giá đã hết hạn — vui lòng chạy lại định giá.")

    if recommendation.status != "DRAFT":
        raise ConflictError("Chỉ có thể gửi duyệt đề xuất đang ở trạng thái DRAFT.")

    before = recommendation.status
    recommendation.status = "PENDING_APPROVAL"
    record_audit_log(
        db,
        actor=current_user.full_name,
        action="SUBMIT_RECOMMENDATION",
        resource_type="price_recommendation",
        before_summary=before,
        after_summary="PENDING_APPROVAL",
    )
    db.commit()
    db.refresh(recommendation)
    return serialize_recommendation(db, recommendation)


def decide_recommendation(
    db: Session,
    recommendation: PriceRecommendation,
    *,
    decision: str,
    payload: RecommendationDecisionRequest,
    current_user: User,
) -> RecommendationRead:
    """Approve or reject a recommendation and persist PriceApproval history."""
    now = utc_now()
    if _as_utc(recommendation.expires_at) <= now:
        recommendation.status = "EXPIRED"
        db.commit()
        raise ConflictError("Đề xuất giá đã hết hạn — vui lòng chạy lại định giá.")

    if recommendation.status not in {"DRAFT", "PENDING_APPROVAL"}:
        raise ConflictError(
            f"Không thể {decision} đề xuất đang ở trạng thái {recommendation.status}."
        )

    adjusted_price: Decimal | None = None
    if decision == "APPROVED" and payload.adjusted_price is not None:
        adjusted_price = _money(payload.adjusted_price)
        if adjusted_price < Decimal(recommendation.floor_price):
            raise ConflictError(
                f"Giá điều chỉnh ({adjusted_price}) không được thấp hơn "
                f"giá sàn ({recommendation.floor_price})."
            )

    before = recommendation.status
    recommendation.status = decision
    approval = PriceApproval(
        recommendation_id=recommendation.id,
        reviewer_id=current_user.id,
        reviewer_name=current_user.full_name,
        decision=decision,
        adjusted_price=adjusted_price,
        reason=payload.reason,
    )
    db.add(approval)

    action = "APPROVE_RECOMMENDATION" if decision == "APPROVED" else "REJECT_RECOMMENDATION"
    after_parts = [decision]
    if adjusted_price is not None:
        after_parts.append(f"adjustedPrice={adjusted_price}")
    if payload.reason:
        after_parts.append(f"reason={payload.reason}")

    record_audit_log(
        db,
        actor=current_user.full_name,
        action=action,
        resource_type="price_recommendation",
        before_summary=before,
        after_summary=", ".join(after_parts),
    )
    db.commit()
    db.refresh(recommendation)
    return serialize_recommendation(db, recommendation)


def simulate_pricing(db: Session, payload: PricingSimulateRequest) -> PricingSimulateResponse:
    """Run Digital Twin what-if simulation across candidate prices for a SKU & channel."""
    product = db.get(Product, payload.sku_id)
    if product is None:
        raise NotFoundError("Không tìm thấy sản phẩm.")
    channel = db.get(SalesChannel, payload.channel_id)
    if channel is None:
        raise NotFoundError("Không tìm thấy kênh bán.")

    now = utc_now()
    unit_cost = _resolve_unit_cost(db, product)
    current_price = _resolve_current_price(db, product, channel)
    comp = _collect_competitor_signal(db, product, channel, now=now)
    sales_records, _, velocity, _ = _collect_sales_signal(db, product, channel)

    base_demand = velocity
    if sales_records:
        ml_forecast = forecast_demand_ml(sales_records, target_price=float(current_price))
        if ml_forecast is not None:
            base_demand = ml_forecast[0]

    denom = Decimal("1") - Decimal(channel.fee_rate) - payload.target_margin
    floor_price = _money(unit_cost / denom) if denom > 0 and unit_cost > 0 else None

    raw_points = simulate_price_curve(
        current_price=float(current_price),
        unit_cost=float(unit_cost),
        channel_fee_rate=float(channel.fee_rate),
        floor_price=float(floor_price) if floor_price is not None else None,
        base_demand=float(base_demand),
        elasticity=payload.elasticity,
        candidate_prices=(
            [float(p) for p in payload.candidate_prices]
            if payload.candidate_prices is not None
            else None
        ),
        competitor_price=float(comp["median"]) if comp["median"] is not None else None,
    )

    points = [
        SimulationPointRead(
            price=_money(pt["price"]),  # type: ignore[arg-type]
            above_floor=bool(pt["above_floor"]),
            predicted_demand=_money(pt["predicted_demand"]),  # type: ignore[arg-type]
            expected_revenue=_money(pt["expected_revenue"]),  # type: ignore[arg-type]
            expected_profit=_money(pt["expected_profit"]),  # type: ignore[arg-type]
            expected_margin=_rate(pt["expected_margin"]),  # type: ignore[arg-type]
            competitor_gap_pct=(
                _rate(pt["competitor_gap_pct"])  # type: ignore[arg-type]
                if pt["competitor_gap_pct"] is not None
                else None
            ),
        )
        for pt in raw_points
    ]

    feasible = [pt for pt in points if pt.above_floor]
    optimal = max(feasible, key=lambda pt: pt.expected_profit) if feasible else None

    return PricingSimulateResponse(
        sku_id=product.id,
        sku_code=product.sku_code,
        product_name=product.name,
        channel_id=channel.id,
        channel_name=channel.name,
        current_price=current_price,
        floor_price=floor_price,
        competitor_median=comp["median"],
        optimal_price=optimal.price if optimal is not None else None,
        points=points,
    )


def evaluate_closed_loop(
    db: Session,
    *,
    window_days: int = 14,
) -> ClosedLoopSummaryRead:
    """Compare predicted demand on executed/approved recommendations with realized SalesRecord."""
    recs = db.execute(
        select(PriceRecommendation, Product, SalesChannel)
        .join(Product, PriceRecommendation.product_id == Product.id)
        .join(SalesChannel, PriceRecommendation.channel_id == SalesChannel.id)
        .where(
            PriceRecommendation.status.in_(["APPROVED", "EXECUTION_QUEUED", "EXECUTED"]),
            PriceRecommendation.predicted_demand.is_not(None),
        )
        .order_by(PriceRecommendation.created_at.desc())
        .limit(100)
    ).all()

    items: list[ClosedLoopItemRead] = []
    metric_inputs: list[dict[str, float]] = []

    for rec, product, channel in recs:
        start_date = _as_utc(rec.created_at).date()
        end_date = start_date + timedelta(days=window_days)
        sales_rows = db.scalars(
            select(SalesRecord).where(
                SalesRecord.product_id == rec.product_id,
                SalesRecord.channel_id == rec.channel_id,
                SalesRecord.order_date >= start_date,
                SalesRecord.order_date <= end_date,
            )
        ).all()
        if not sales_rows:
            continue

        actual_avg = sum(float(max(0, r.quantity)) for r in sales_rows) / len(sales_rows)
        predicted = float(rec.predicted_demand or 0)
        err = evaluate_closed_loop_point(predicted, actual_avg)
        metric_inputs.append(err)
        items.append(
            ClosedLoopItemRead(
                recommendation_id=rec.id,
                sku_code=product.sku_code,
                channel_name=channel.name,
                recommended_price=_money(rec.recommended_price),
                predicted_demand=_money(predicted),
                actual_avg_daily_demand=_money(actual_avg),
                absolute_error=_rate(err["error"]),
                percentage_error=_rate(err["percentage_error"]),
                sales_days_observed=len(sales_rows),
            )
        )

    summary = summarize_closed_loop(metric_inputs)
    return ClosedLoopSummaryRead(
        evaluated_count=int(summary["evaluated_count"]),
        mae=_rate(summary["mae"]),
        within_tolerance_count=int(summary["within_tolerance_count"]),
        items=items,
    )


def summarize_model_runs(db: Session) -> ModelRunSummaryRead:
    """Summarize latest ModelRun per algorithm and identify the best performing model."""
    rows = db.scalars(select(ModelRun).order_by(ModelRun.trained_at.desc()).limit(50)).all()
    if not rows:
        return ModelRunSummaryRead()

    latest_by_algo: dict[str, ModelRun] = {}
    for row in rows:
        if row.algorithm_type not in latest_by_algo:
            latest_by_algo[row.algorithm_type] = row

    latest_list = list(latest_by_algo.values())
    best = min(latest_list, key=lambda r: (Decimal(r.rmse), Decimal(r.mae)))

    improvement_pct: Decimal | None = None
    if len(latest_list) >= 2:
        worst_rmse = max(Decimal(r.rmse) for r in latest_list)
        if worst_rmse > 0:
            improvement_pct = _rate((worst_rmse - Decimal(best.rmse)) / worst_rmse)

    return ModelRunSummaryRead(
        best_model_name=best.model_name,
        best_algorithm_type=best.algorithm_type,
        rmse_improvement_pct=improvement_pct,
        latest_runs=[ModelRunRead.model_validate(r) for r in latest_list],
    )
