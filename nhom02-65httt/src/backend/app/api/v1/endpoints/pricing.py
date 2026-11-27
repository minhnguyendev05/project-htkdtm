"""Smart Pricing preview and batch run endpoints wired to AI Pricing Engine."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_any_permission, require_permission
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Envelope
from app.schemas.pricing import (
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
