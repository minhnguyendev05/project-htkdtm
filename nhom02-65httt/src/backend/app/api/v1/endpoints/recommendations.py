"""Price recommendation listing, submission, and approval workflow endpoints."""

from __future__ import annotations

import math
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.errors import NotFoundError
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.erp import Product
from app.models.market import SalesChannel
from app.models.pricing import PriceApproval, PriceRecommendation
from app.models.user import User
from app.schemas.common import Envelope, PageMeta
from app.schemas.pricing import RecommendationDecisionRequest, RecommendationRead
from app.services.pricing import (
    decide_recommendation,
    serialize_recommendation,
    submit_recommendation_for_approval,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=Envelope[list[RecommendationRead]])
def list_recommendations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    rec_status: str | None = Query(default=None, alias="status"),
    channel_id: UUID | None = Query(default=None, alias="channelId"),
    product_id: UUID | None = Query(default=None, alias="productId"),
    q: str | None = Query(default=None),
    _: User = Depends(require_permission(Permission.PRICING_READ)),
    db: Session = Depends(get_db),
) -> Envelope[list[RecommendationRead]]:
    """Return a paginated, filterable list of persisted price recommendations."""
    filters = []
    if rec_status and rec_status.strip():
        filters.append(PriceRecommendation.status == rec_status.strip().upper())
    if channel_id is not None:
        filters.append(PriceRecommendation.channel_id == channel_id)
    if product_id is not None:
        filters.append(PriceRecommendation.product_id == product_id)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                Product.sku_code.ilike(pattern),
                Product.name.ilike(pattern),
                PriceRecommendation.created_by.ilike(pattern),
            )
        )

    total = (
        db.scalar(
            select(func.count())
            .select_from(PriceRecommendation)
            .join(Product, PriceRecommendation.product_id == Product.id)
            .where(*filters)
        )
        or 0
    )
    total_pages = max(1, math.ceil(total / page_size))

    rows = db.execute(
        select(PriceRecommendation, Product, SalesChannel)
        .join(Product, PriceRecommendation.product_id == Product.id)
        .join(SalesChannel, PriceRecommendation.channel_id == SalesChannel.id)
        .where(*filters)
        .order_by(PriceRecommendation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    rec_ids = [rec.id for rec, _, _ in rows]
    approvals_by_rec: dict[UUID, list[PriceApproval]] = {rec_id: [] for rec_id in rec_ids}
    if rec_ids:
        approval_rows = db.scalars(
            select(PriceApproval)
            .where(PriceApproval.recommendation_id.in_(rec_ids))
            .order_by(PriceApproval.decided_at.desc())
        ).all()
        for approval in approval_rows:
            approvals_by_rec[approval.recommendation_id].append(approval)

    data = [
        serialize_recommendation(
            db,
            rec,
            product=product,
            channel=channel,
            approvals=approvals_by_rec.get(rec.id, []),
        )
        for rec, product, channel in rows
    ]

    return Envelope(
        data=data,
        meta=PageMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/{recommendation_id}", response_model=Envelope[RecommendationRead])
def get_recommendation(
    recommendation_id: UUID,
    _: User = Depends(require_permission(Permission.PRICING_READ)),
    db: Session = Depends(get_db),
) -> Envelope[RecommendationRead]:
    """Retrieve a single price recommendation with its approval history."""
    rec = db.get(PriceRecommendation, recommendation_id)
    if rec is None:
        raise NotFoundError("Không tìm thấy đề xuất giá.")
    return Envelope(data=serialize_recommendation(db, rec))


@router.post("/{recommendation_id}/submit", response_model=Envelope[RecommendationRead])
def submit_recommendation(
    recommendation_id: UUID,
    current_user: User = Depends(require_permission(Permission.PRICING_RUN)),
    db: Session = Depends(get_db),
) -> Envelope[RecommendationRead]:
    """Submit a DRAFT recommendation into PENDING_APPROVAL."""
    rec = db.get(PriceRecommendation, recommendation_id)
    if rec is None:
        raise NotFoundError("Không tìm thấy đề xuất giá.")
    return Envelope(
        data=submit_recommendation_for_approval(db, rec, current_user=current_user)
    )


@router.post("/{recommendation_id}/approve", response_model=Envelope[RecommendationRead])
def approve_recommendation(
    recommendation_id: UUID,
    payload: RecommendationDecisionRequest = Body(default_factory=RecommendationDecisionRequest),
    current_user: User = Depends(require_permission(Permission.PRICING_APPROVE)),
    db: Session = Depends(get_db),
) -> Envelope[RecommendationRead]:
    """Approve a recommendation (optionally adjusting price above floor_price)."""
    rec = db.get(PriceRecommendation, recommendation_id)
    if rec is None:
        raise NotFoundError("Không tìm thấy đề xuất giá.")
    return Envelope(
        data=decide_recommendation(
            db,
            rec,
            decision="APPROVED",
            payload=payload,
            current_user=current_user,
        )
    )


@router.post("/{recommendation_id}/reject", response_model=Envelope[RecommendationRead])
def reject_recommendation(
    recommendation_id: UUID,
    payload: RecommendationDecisionRequest = Body(default_factory=RecommendationDecisionRequest),
    current_user: User = Depends(require_permission(Permission.PRICING_APPROVE)),
    db: Session = Depends(get_db),
) -> Envelope[RecommendationRead]:
    """Reject a recommendation and record reviewer reason."""
    rec = db.get(PriceRecommendation, recommendation_id)
    if rec is None:
        raise NotFoundError("Không tìm thấy đề xuất giá.")
    return Envelope(
        data=decide_recommendation(
            db,
            rec,
            decision="REJECTED",
            payload=payload,
            current_user=current_user,
        )
    )
