"""Pricing rule management endpoints protected by RBAC and backed by SQLAlchemy."""

from __future__ import annotations

import math
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.errors import ConflictError, NotFoundError
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.erp import Category
from app.models.market import SalesChannel
from app.models.pricing import PricingRule
from app.models.user import User
from app.schemas.common import Envelope, PageMeta
from app.schemas.pricing import (
    PricingRuleCreate,
    PricingRuleRead,
    PricingRuleStatusUpdate,
    PricingRuleUpdate,
    RuleStatus,
    RuleType,
)
from app.services.audit import record_audit_log

router = APIRouter(prefix="/pricing-rules", tags=["pricing-rules"])


def _validate_rule_foreign_keys(
    db: Session,
    *,
    category_id: UUID | None,
    channel_id: UUID | None,
) -> None:
    if category_id is not None and db.get(Category, category_id) is None:
        raise NotFoundError("Không tìm thấy danh mục sản phẩm cho quy tắc định giá.")
    if channel_id is not None and db.get(SalesChannel, channel_id) is None:
        raise NotFoundError("Không tìm thấy kênh bán cho quy tắc định giá.")


def _validate_activation_guardrails(
    *,
    scope_label: str,
    min_margin: Decimal,
    max_price_change_pct: Decimal,
) -> None:
    missing: list[str] = []
    if not scope_label.strip():
        missing.append("phạm vi áp dụng")
    if min_margin <= 0:
        missing.append("biên lợi nhuận tối thiểu > 0")
    if max_price_change_pct <= 0:
        missing.append("giới hạn biến động giá > 0")
    if missing:
        raise ConflictError(f"Không thể kích hoạt quy tắc: thiếu {', '.join(missing)}.")


def _validate_status_transition(rule: PricingRule, next_status: str) -> None:
    if rule.rule_type == "MARGIN_GUARD" and next_status != "ACTIVE":
        raise ConflictError("Margin Guard là rào chắn hệ thống, không thể tạm dừng hoặc lưu trữ.")
    if rule.status == "ARCHIVED" and next_status != "ARCHIVED":
        raise ConflictError("Quy tắc đã lưu trữ, không thể kích hoạt lại.")


@router.get("", response_model=Envelope[list[PricingRuleRead]])
def list_pricing_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    rule_status: RuleStatus | None = Query(default=None, alias="status"),
    rule_type: RuleType | None = Query(default=None, alias="ruleType"),
    channel_id: UUID | None = Query(default=None, alias="channelId"),
    q: str | None = Query(default=None),
    _: User = Depends(require_permission(Permission.RULE_READ)),
    db: Session = Depends(get_db),
) -> Envelope[list[PricingRuleRead]]:
    """Return paginated pricing rules ordered by priority."""
    filters = []
    if rule_status is not None:
        filters.append(PricingRule.status == rule_status)
    if rule_type is not None:
        filters.append(PricingRule.rule_type == rule_type)
    if channel_id is not None:
        filters.append(PricingRule.channel_id == channel_id)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                PricingRule.name.ilike(pattern),
                PricingRule.scope_label.ilike(pattern),
            )
        )

    total = db.scalar(select(func.count()).select_from(PricingRule).where(*filters)) or 0
    total_pages = max(1, math.ceil(total / page_size))

    rows = db.scalars(
        select(PricingRule)
        .where(*filters)
        .order_by(PricingRule.priority.asc(), PricingRule.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return Envelope(
        data=[PricingRuleRead.model_validate(row) for row in rows],
        meta=PageMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.post("", response_model=Envelope[PricingRuleRead], status_code=status.HTTP_201_CREATED)
def create_pricing_rule(
    payload: PricingRuleCreate,
    current_user: User = Depends(require_permission(Permission.RULE_WRITE)),
    db: Session = Depends(get_db),
) -> Envelope[PricingRuleRead]:
    """Create a persisted pricing rule and record an audit log entry."""
    _validate_rule_foreign_keys(
        db,
        category_id=payload.category_id,
        channel_id=payload.channel_id,
    )
    if payload.status == "ACTIVE":
        _validate_activation_guardrails(
            scope_label=payload.scope_label,
            min_margin=payload.min_margin,
            max_price_change_pct=payload.max_price_change_pct,
        )

    rule = PricingRule(
        name=payload.name,
        rule_type=payload.rule_type,
        priority=payload.priority,
        scope_label=payload.scope_label,
        category_id=payload.category_id,
        channel_id=payload.channel_id,
        min_margin=payload.min_margin,
        max_price_change_pct=payload.max_price_change_pct,
        approval_required=payload.approval_required,
        status=payload.status,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    db.add(rule)
    record_audit_log(
        db,
        actor=current_user.full_name,
        action="CREATE_PRICING_RULE",
        resource_type="pricing_rule",
        after_summary=f"{rule.name} ({rule.rule_type}, status={rule.status})",
    )
    db.commit()
    db.refresh(rule)
    return Envelope(data=PricingRuleRead.model_validate(rule))


@router.get("/{rule_id}", response_model=Envelope[PricingRuleRead])
def get_pricing_rule(
    rule_id: UUID,
    _: User = Depends(require_permission(Permission.RULE_READ)),
    db: Session = Depends(get_db),
) -> Envelope[PricingRuleRead]:
    """Retrieve a single pricing rule by ID."""
    rule = db.get(PricingRule, rule_id)
    if rule is None:
        raise NotFoundError("Không tìm thấy quy tắc định giá.")
    return Envelope(data=PricingRuleRead.model_validate(rule))


@router.patch("/{rule_id}", response_model=Envelope[PricingRuleRead])
def update_pricing_rule(
    rule_id: UUID,
    payload: PricingRuleUpdate,
    current_user: User = Depends(require_permission(Permission.RULE_WRITE)),
    db: Session = Depends(get_db),
) -> Envelope[PricingRuleRead]:
    """Update a pricing rule's parameters or status while enforcing business guardrails."""
    rule = db.get(PricingRule, rule_id)
    if rule is None:
        raise NotFoundError("Không tìm thấy quy tắc định giá.")

    updates = payload.model_dump(exclude_unset=True)
    _validate_rule_foreign_keys(
        db,
        category_id=updates.get("category_id"),
        channel_id=updates.get("channel_id"),
    )

    next_status = updates.get("status", rule.status)
    if "status" in updates and next_status is not None:
        _validate_status_transition(rule, next_status)

    next_starts = updates.get("starts_at", rule.starts_at)
    next_ends = updates.get("ends_at", rule.ends_at)
    if next_ends is not None and next_ends <= next_starts:
        raise ConflictError("Thời gian kết thúc phải lớn hơn thời gian bắt đầu.")

    next_scope = updates.get("scope_label", rule.scope_label)
    next_min_margin = updates.get("min_margin", rule.min_margin)
    next_max_change = updates.get("max_price_change_pct", rule.max_price_change_pct)
    if next_status == "ACTIVE":
        _validate_activation_guardrails(
            scope_label=next_scope,
            min_margin=Decimal(next_min_margin),
            max_price_change_pct=Decimal(next_max_change),
        )

    before_summary = (
        f"name={rule.name}, status={rule.status}, priority={rule.priority}, "
        f"minMargin={rule.min_margin}"
    )

    for field_name, value in updates.items():
        setattr(rule, field_name, value)

    record_audit_log(
        db,
        actor=current_user.full_name,
        action="UPDATE_PRICING_RULE",
        resource_type="pricing_rule",
        before_summary=before_summary,
        after_summary=(
            f"name={rule.name}, status={rule.status}, priority={rule.priority}, "
            f"minMargin={rule.min_margin}"
        ),
    )
    db.commit()
    db.refresh(rule)
    return Envelope(data=PricingRuleRead.model_validate(rule))


@router.post("/{rule_id}/status", response_model=Envelope[PricingRuleRead])
def transition_pricing_rule_status(
    rule_id: UUID,
    payload: PricingRuleStatusUpdate,
    current_user: User = Depends(require_permission(Permission.RULE_WRITE)),
    db: Session = Depends(get_db),
) -> Envelope[PricingRuleRead]:
    """Transition a pricing rule's status (DRAFT/ACTIVE/PAUSED/ARCHIVED)."""
    rule = db.get(PricingRule, rule_id)
    if rule is None:
        raise NotFoundError("Không tìm thấy quy tắc định giá.")

    _validate_status_transition(rule, payload.status)
    if payload.status == "ACTIVE":
        _validate_activation_guardrails(
            scope_label=rule.scope_label,
            min_margin=Decimal(rule.min_margin),
            max_price_change_pct=Decimal(rule.max_price_change_pct),
        )

    before = rule.status
    rule.status = payload.status
    record_audit_log(
        db,
        actor=current_user.full_name,
        action="UPDATE_PRICING_RULE_STATUS",
        resource_type="pricing_rule",
        before_summary=before,
        after_summary=rule.status,
    )
    db.commit()
    db.refresh(rule)
    return Envelope(data=PricingRuleRead.model_validate(rule))
