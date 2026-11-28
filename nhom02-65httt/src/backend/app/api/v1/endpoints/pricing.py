"""Smart Pricing preview, batch run, and ML model-run endpoints."""

from __future__ import annotations

import math

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_any_permission, require_permission
from app.core.rbac import Permission
from app.db.session import get_db
from app.ml.model_runs import train_and_log_from_sales_records
from app.models.pricing import ModelRun
from app.models.user import User
from app.schemas.common import Envelope, PageMeta
from app.schemas.pricing import (
    ModelRunRead,
    ModelTrainRequest,
    PricingPreviewRequest,
    PricingPreviewResponse,
    PricingRunRequest,
    PricingRunResponse,
)
from app.services.pricing import execute_pricing_run, preview_pricing

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.post("/preview", response_model=Envelope[PricingPreviewResponse])
def preview_smart_pricing(
    payload: PricingPreviewRequest,
    _: User = Depends(require_any_permission(Permission.PRICING_READ, Permission.PRICING_RUN)),
    db: Session = Depends(get_db),
) -> Envelope[PricingPreviewResponse]:
    """Preview floor price (Pmin) and AI suggested price without persisting recommendations."""
    return Envelope(data=preview_pricing(db, payload))


@router.post(
    "/run",
    response_model=Envelope[PricingRunResponse],
    status_code=status.HTTP_201_CREATED,
)
def run_smart_pricing(
    payload: PricingRunRequest,
    current_user: User = Depends(require_permission(Permission.PRICING_RUN)),
    db: Session = Depends(get_db),
) -> Envelope[PricingRunResponse]:
    """Execute AI Pricing Engine on selected SKUs and persist recommendations to database."""
    return Envelope(data=execute_pricing_run(db, payload, current_user=current_user))


@router.get("/model-runs", response_model=Envelope[list[ModelRunRead]])
def list_model_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    _: User = Depends(require_permission(Permission.PRICING_READ)),
    db: Session = Depends(get_db),
) -> Envelope[list[ModelRunRead]]:
    """Return paginated ML model training comparison runs ordered newest first."""
    total = db.scalar(select(func.count()).select_from(ModelRun)) or 0
    total_pages = max(1, math.ceil(total / page_size))

    rows = db.scalars(
        select(ModelRun)
        .order_by(ModelRun.trained_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return Envelope(
        data=[ModelRunRead.model_validate(row) for row in rows],
        meta=PageMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.post(
    "/model-runs/train",
    response_model=Envelope[list[ModelRunRead]],
    status_code=status.HTTP_201_CREATED,
)
def train_model_runs(
    payload: ModelTrainRequest = Body(default_factory=ModelTrainRequest),
    current_user: User = Depends(require_permission(Permission.PRICING_RUN)),
    db: Session = Depends(get_db),
) -> Envelope[list[ModelRunRead]]:
    """Train and compare LinearRegression vs XGBoost on SalesRecord history."""
    rows = train_and_log_from_sales_records(
        db,
        product_id=payload.product_id,
        channel_id=payload.channel_id,
        split_ratio=payload.split_ratio,
        actor=current_user.full_name,
    )
    return Envelope(data=[ModelRunRead.model_validate(row) for row in rows])
