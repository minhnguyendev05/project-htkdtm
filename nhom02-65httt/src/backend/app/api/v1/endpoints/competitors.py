"""Competitor-price reads and background crawler dispatch."""

from __future__ import annotations

import math
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from market_data.tasks import crawl_and_store_task
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.errors import NotFoundError
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.market import CompetitorPrice, CompetitorPriceHistory
from app.models.user import User
from app.schemas.common import Envelope, PageMeta
from app.schemas.competitor import (
    CompetitorPriceHistoryRead,
    CompetitorPriceRead,
    CrawlerRunCreate,
    CrawlerRunRead,
)

router = APIRouter(tags=["competitors"])


@router.get(
    "/competitor-prices",
    response_model=Envelope[list[CompetitorPriceRead]],
)
def list_competitor_prices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sku_code: str | None = Query(default=None, alias="skuCode", max_length=64),
    marketplace_code: str | None = Query(
        default=None, alias="marketplaceCode", max_length=32
    ),
    match_status: Literal["AUTO_MATCHED", "NEEDS_REVIEW", "REJECTED"] | None = Query(
        default=None, alias="matchStatus"
    ),
    _: User = Depends(require_permission(Permission.COMPETITOR_READ)),
    db: Session = Depends(get_db),
) -> Envelope[list[CompetitorPriceRead]]:
    """Return paginated competitor observations from the canonical market tables."""
    filters = []
    if sku_code and sku_code.strip():
        filters.append(CompetitorPrice.sku_code == sku_code.strip().upper())
    if marketplace_code and marketplace_code.strip():
        filters.append(
            CompetitorPrice.marketplace_code == marketplace_code.strip().upper()
        )
    if match_status and match_status.strip():
        filters.append(CompetitorPrice.match_status == match_status.strip().upper())

    total = int(
        db.scalar(
            select(func.count()).select_from(CompetitorPrice).where(*filters)
        )
        or 0
    )
    rows = db.scalars(
        select(CompetitorPrice)
        .where(*filters)
        .order_by(CompetitorPrice.observed_at.desc(), CompetitorPrice.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Envelope(
        data=[CompetitorPriceRead.model_validate(row) for row in rows],
        meta=PageMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=max(1, math.ceil(total / page_size)),
        ),
    )


@router.get(
    "/competitor-prices/{competitor_price_id}/history",
    response_model=Envelope[list[CompetitorPriceHistoryRead]],
)
def list_competitor_price_history(
    competitor_price_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100, alias="pageSize"),
    _: User = Depends(require_permission(Permission.COMPETITOR_READ)),
    db: Session = Depends(get_db),
) -> Envelope[list[CompetitorPriceHistoryRead]]:
    """Return daily history for one canonical competitor listing."""
    if db.get(CompetitorPrice, competitor_price_id) is None:
        raise NotFoundError("Không tìm thấy sản phẩm đối thủ.")

    filters = [CompetitorPriceHistory.competitor_price_id == competitor_price_id]
    total = int(
        db.scalar(
            select(func.count()).select_from(CompetitorPriceHistory).where(*filters)
        )
        or 0
    )
    rows = db.scalars(
        select(CompetitorPriceHistory)
        .where(*filters)
        .order_by(CompetitorPriceHistory.recorded_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Envelope(
        data=[CompetitorPriceHistoryRead.model_validate(row) for row in rows],
        meta=PageMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=max(1, math.ceil(total / page_size)),
        ),
    )


@router.post(
    "/crawler/run",
    response_model=Envelope[CrawlerRunRead],
    status_code=status.HTTP_202_ACCEPTED,
)
def run_crawler(
    payload: CrawlerRunCreate,
    _: User = Depends(require_permission(Permission.COMPETITOR_WRITE)),
) -> Envelope[CrawlerRunRead]:
    """Queue an allow-listed adapter; the Celery worker writes to shared ORM tables."""
    result = crawl_and_store_task.delay(
        payload.adapter_name,
        fetch_kwargs=payload.fetch_kwargs(),
        sku_code=payload.sku_code,
    )
    return Envelope(
        data=CrawlerRunRead(
            task_id=result.id,
            adapter_name=payload.adapter_name,
        )
    )
