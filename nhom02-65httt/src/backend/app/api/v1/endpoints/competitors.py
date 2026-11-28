"""Competitor-price reads and background crawler dispatch."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, Query, status
from market_data.persistence import persist_competitor_prices
from market_data.tasks import crawl_and_store_task
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.errors import ConflictError, NotFoundError
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.erp import Product
from app.models.market import CompetitorPrice, CompetitorPriceHistory
from app.models.user import User
from app.schemas.common import Envelope, PageMeta
from app.schemas.competitor import (
    CdpIngestCreate,
    CdpIngestRead,
    CompetitorMatchReviewCreate,
    CompetitorPriceHistoryRead,
    CompetitorPriceRead,
    CrawlerRunCreate,
    CrawlerRunRead,
)
from app.services.audit import record_audit_log

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
    match_status: Literal[
        "AUTO_MATCHED", "MANUALLY_MATCHED", "NEEDS_REVIEW", "REJECTED"
    ] | None = Query(default=None, alias="matchStatus"),
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


@router.post(
    "/crawler/ingest-cdp",
    response_model=Envelope[CdpIngestRead],
    status_code=status.HTTP_201_CREATED,
)
def ingest_cdp_records(
    payload: CdpIngestCreate,
    _: User = Depends(require_permission(Permission.COMPETITOR_WRITE)),
    db: Session = Depends(get_db),
) -> Envelope[CdpIngestRead]:
    """Persist structured CDP observations without accepting or fetching raw URLs."""
    rows: list[dict[str, object]] = []
    records_received = 0
    for record in payload.structured_records:
        candidates = record.items or [record]
        for item in candidates:
            records_received += 1
            item_id = item.item_id or item.sku_id
            title = item.name or item.title
            price = item.price_vnd
            if not item_id or not title or price is None:
                continue

            marketplace = record.platform.upper()
            shop_id = item.shop_id or record.shop_id
            source_url = item.url or record.url
            if not source_url and marketplace == "SHOPEE" and shop_id:
                source_url = f"https://shopee.vn/product/{shop_id}/{item_id}"
            original_price = item.original_price_vnd or item.price_before_discount_vnd
            discount_percent = None
            if original_price and original_price > price:
                discount_percent = float(
                    (original_price - price) / original_price * Decimal("100")
                )
            rows.append(
                {
                    "marketplace": marketplace,
                    "category": marketplace.casefold(),
                    "product_id": str(item_id),
                    "title": title,
                    "brand": item.brand,
                    "seller": item.shop_name or record.shop_name or marketplace,
                    "price_vnd": float(price),
                    "original_price_vnd": (
                        float(original_price) if original_price is not None else None
                    ),
                    "discount_percent": discount_percent,
                    "sold": (
                        item.sold
                        if item.sold is not None
                        else item.historical_sold
                    ),
                    "rating": (
                        float(item.rating_star)
                        if item.rating_star is not None
                        else None
                    ),
                    "observed_at": (
                        item.captured_at_utc
                        or record.captured_at_utc
                        or datetime.now(UTC)
                    ),
                    "url": source_url,
                    "confidence": 0.8,
                }
            )

    if not rows:
        raise ConflictError(
            "Không có bản ghi CDP đủ mã sản phẩm, tên và giá để nạp."
        )

    result = persist_competitor_prices(
        db,
        pd.DataFrame(rows),
        adapter_name="cdp",
    )
    db.commit()
    return Envelope(
        data=CdpIngestRead(
            records_received=records_received,
            rows_skipped=records_received - result["rows_received"],
            **result,
        )
    )


@router.post(
    "/competitor-prices/{competitor_price_id}/review",
    response_model=Envelope[CompetitorPriceRead],
)
def review_competitor_match(
    competitor_price_id: UUID,
    payload: CompetitorMatchReviewCreate,
    current_user: User = Depends(require_permission(Permission.COMPETITOR_WRITE)),
    db: Session = Depends(get_db),
) -> Envelope[CompetitorPriceRead]:
    """Approve a manual SKU match or reject a listing awaiting review."""
    listing = db.get(CompetitorPrice, competitor_price_id)
    if listing is None:
        raise NotFoundError("Không tìm thấy sản phẩm đối thủ.")
    if listing.match_status != "NEEDS_REVIEW":
        raise ConflictError("Chỉ xử lý sản phẩm đang ở trạng thái NEEDS_REVIEW.")

    before_summary = f"{listing.match_status}:{listing.sku_code or '-'}"
    if payload.decision == "APPROVE":
        product = db.scalar(
            select(Product).where(
                Product.sku_code == payload.sku_code,
                Product.status == "ACTIVE",
            )
        )
        if product is None:
            raise NotFoundError("Không tìm thấy SKU ACTIVE để liên kết.")
        listing.product_id = product.id
        listing.sku_code = product.sku_code
        listing.product_name = product.name
        listing.match_status = "MANUALLY_MATCHED"
        listing.verdict = f"Duyệt thủ công: {payload.reason[:80]}"
        action = "APPROVE_COMPETITOR_MATCH"
    else:
        listing.product_id = None
        listing.sku_code = None
        listing.product_name = (listing.raw_title or listing.product_name)[:255]
        listing.match_status = "REJECTED"
        listing.verdict = f"Từ chối thủ công: {payload.reason[:80]}"
        action = "REJECT_COMPETITOR_MATCH"

    record_audit_log(
        db,
        actor=current_user.full_name,
        action=action,
        resource_type="competitor_price",
        reason=payload.reason,
        before_summary=before_summary,
        after_summary=f"{listing.match_status}:{listing.sku_code or '-'}",
    )
    db.commit()
    db.refresh(listing)
    return Envelope(data=CompetitorPriceRead.model_validate(listing))
