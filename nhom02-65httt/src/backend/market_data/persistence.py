from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pandas as pd
from app.models.erp import Product
from app.models.market import CompetitorPrice, CompetitorPriceHistory
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from .matching import extract_model, match_sku
from .normalize import normalize_dataframe

SOURCE_TYPES = {
    "dataset_snapshot": "CSV",
    "giarevn": "PUBLIC_PAGE",
    "lazada": "PUBLIC_PAGE",
    "price_history": "API",
    "retail_html": "PUBLIC_PAGE",
    "tiki": "API",
}

SOURCE_NAMES = {
    "dataset_snapshot": "CSV snapshot",
    "giarevn": "Giarevn price history",
    "lazada": "Lazada product page",
    "price_history": "Price history API",
    "retail_html": "Retail product page",
    "tiki": "Tiki API",
}


def _utc_datetime(value: Any) -> datetime:
    timestamp = pd.Timestamp(value).to_pydatetime()
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    return int(numeric)


def _bounded_text(value: Any, field: str, limit: int, *, required: bool = False) -> str | None:
    text = "" if value is None or pd.isna(value) else str(value).strip()
    if required and not text:
        raise ValueError(f"{field} không được để trống.")
    if len(text) > limit:
        raise ValueError(f"{field} vượt quá giới hạn {limit} ký tự.")
    return text or None


def _candidate_matches(
    product: Product,
    title: str,
    brand: str | None,
    marketplace: str,
    external_product_id: str,
) -> dict:
    product_name_parts = [product.name, product.variant_name]
    if product.model_code and not extract_model(product.name):
        product_name_parts.append(product.model_code)
    product_name = " ".join(
        part for part in product_name_parts if part
    )
    return match_sku(
        {"sku": product.sku_code, "name": product_name, "brand": product.brand},
        {
            "product_id": external_product_id,
            "title": title,
            "brand": brand,
            "marketplace": marketplace,
        },
    )


def _match_product(
    products: list[Product],
    *,
    title: str,
    brand: str | None,
    marketplace: str,
    external_product_id: str,
    sku_code: str | None,
) -> tuple[Product | None, str, str]:
    if sku_code:
        products = [product for product in products if product.sku_code == sku_code]
        if not products:
            return None, "NEEDS_REVIEW", f"Không tìm thấy SKU ERP {sku_code}."

    matches = [
        (
            product,
            _candidate_matches(
                product,
                title,
                brand,
                marketplace,
                external_product_id,
            ),
        )
        for product in products
    ]
    if not matches:
        return None, "NEEDS_REVIEW", "Chưa có sản phẩm ERP để đối chiếu."

    matches.sort(key=lambda item: item[1]["score"], reverse=True)
    best_product, best_match = matches[0]
    if best_match["status"] == "MATCHED":
        tied = [
            match
            for _, match in matches
            if match["status"] == "MATCHED"
            and match["score"] == best_match["score"]
        ]
        if len(tied) == 1:
            return (
                best_product,
                "AUTO_MATCHED",
                f"Khớp tự động với độ tương đồng {best_match['score']:.2f}.",
            )
        return None, "NEEDS_REVIEW", "Có nhiều SKU ERP cùng điểm khớp cao nhất."

    if best_match["status"] == "NEEDS_REVIEW":
        return (
            best_product,
            "NEEDS_REVIEW",
            f"Cần xác minh SKU {best_product.sku_code} "
            f"(độ tương đồng {best_match['score']:.2f}).",
        )

    return (
        None,
        "REJECTED",
        f"Ứng viên tốt nhất không đạt ngưỡng khớp "
        f"(độ tương đồng {best_match['score']:.2f}).",
    )


def persist_competitor_prices(
    db: Session,
    records: pd.DataFrame,
    *,
    adapter_name: str,
    sku_code: str | None = None,
) -> dict[str, int]:
    """Upsert current competitor listings and their daily history into app tables."""
    adapter_name = adapter_name.strip().casefold()
    if adapter_name not in SOURCE_TYPES:
        raise ValueError(f"Adapter không được hỗ trợ: {adapter_name}")
    if records.empty:
        return {
            "rows_received": 0,
            "rows_created": 0,
            "rows_updated": 0,
            "history_rows_created": 0,
            "history_rows_updated": 0,
        }

    normalized = normalize_dataframe(records).sort_values(
        ["marketplace", "product_id", "observed_at"]
    )
    products = list(
        db.scalars(select(Product).where(Product.status == "ACTIVE")).all()
    )
    counts = {
        "rows_received": int(len(normalized)),
        "rows_created": 0,
        "rows_updated": 0,
        "history_rows_created": 0,
        "history_rows_updated": 0,
    }

    external_ids_by_marketplace = {
        marketplace: group["product_id"].unique().tolist()
        for marketplace, group in normalized.groupby("marketplace", sort=False)
    }
    listings_by_key: dict[tuple[str, str], CompetitorPrice] = {}
    for marketplace, external_ids in external_ids_by_marketplace.items():
        for offset in range(0, len(external_ids), 500):
            batch_ids = external_ids[offset : offset + 500]
            existing = db.scalars(
                select(CompetitorPrice).where(
                    CompetitorPrice.marketplace_code == marketplace,
                    CompetitorPrice.external_item_id.in_(batch_ids),
                )
            ).all()
            for listing in existing:
                key = (listing.marketplace_code, listing.external_item_id or "")
                current = listings_by_key.get(key)
                if current is None or _utc_datetime(listing.observed_at) > _utc_datetime(
                    current.observed_at
                ):
                    listings_by_key[key] = listing

    incoming_dates: dict[tuple[str, str], set[date]] = {}
    for row in normalized[["marketplace", "product_id", "observed_at"]].itertuples(
        index=False
    ):
        key = (row.marketplace, row.product_id)
        incoming_dates.setdefault(key, set()).add(_utc_datetime(row.observed_at).date())

    history_keys = [
        (listing.id, observed_date)
        for key, observed_dates in incoming_dates.items()
        if (listing := listings_by_key.get(key)) is not None
        for observed_date in observed_dates
    ]
    history_by_key: dict[tuple[Any, date], CompetitorPriceHistory] = {}
    for offset in range(0, len(history_keys), 300):
        batch_keys = history_keys[offset : offset + 300]
        existing_history = db.scalars(
            select(CompetitorPriceHistory).where(
                tuple_(
                    CompetitorPriceHistory.competitor_price_id,
                    CompetitorPriceHistory.recorded_date,
                ).in_(batch_keys)
            )
        ).all()
        for history in existing_history:
            history_by_key[(history.competitor_price_id, history.recorded_date)] = history

    latest_observed_by_key = {
        key: _utc_datetime(listing.observed_at)
        for key, listing in listings_by_key.items()
    }

    for row in normalized.to_dict(orient="records"):
        marketplace = _bounded_text(
            row["marketplace"], "marketplace_code", 32, required=True
        )
        external_id = _bounded_text(
            row["product_id"], "external_item_id", 120, required=True
        )
        title = _bounded_text(row["title"], "raw_title", 500, required=True)
        product, match_status, verdict = _match_product(
            products,
            title=title or "",
            brand=_bounded_text(row.get("brand"), "brand", 255),
            marketplace=marketplace or "",
            external_product_id=external_id or "",
            sku_code=sku_code,
        )
        source_url = _bounded_text(row.get("url"), "source_url", 500)
        competitor_name = _bounded_text(
            row.get("seller") or marketplace, "competitor_name", 150, required=True
        )
        observed_at = _utc_datetime(row["observed_at"])
        listed_price = Decimal(str(row["price_vnd"]))
        listing_key = (marketplace or "", external_id or "")
        history_date = observed_at.date()
        listing = listings_by_key.get(listing_key)
        is_new = listing is None
        if listing is None:
            listing = CompetitorPrice(
                id=uuid4(),
                product_name=product.name if product is not None else title[:255],
                competitor_name=competitor_name or marketplace or "",
                marketplace_code=marketplace or "",
                source_type=SOURCE_TYPES[adapter_name],
                source_name=SOURCE_NAMES[adapter_name],
                listed_price=listed_price,
                observed_at=observed_at,
            )
            db.add(listing)
            listings_by_key[listing_key] = listing
            latest_observed_by_key[listing_key] = observed_at
            counts["rows_created"] += 1
        else:
            counts["rows_updated"] += 1

        previous_latest = latest_observed_by_key[listing_key]
        is_latest_observation = observed_at >= previous_latest
        if is_new or is_latest_observation:
            listing.product_id = product.id if product is not None else None
            listing.sku_code = product.sku_code if product is not None else None
            listing.product_name = product.name if product is not None else title[:255]
            listing.competitor_name = competitor_name or marketplace or ""
            listing.marketplace_code = marketplace or ""
            listing.source_type = SOURCE_TYPES[adapter_name]
            listing.source_name = SOURCE_NAMES[adapter_name]
            listing.source_url = source_url
            listing.external_item_id = external_id
            listing.raw_title = title
            listing.extracted_model_code = extract_model(title) or None
            listing.listed_price = listed_price
            listing.effective_price = listed_price
            listing.sold_count = _optional_int(row.get("sold"))
            rating = row.get("rating")
            listing.rating = Decimal(str(rating)) if not pd.isna(rating) else None
            confidence = float(row.get("confidence", 0.5))
            listing.confidence = Decimal(str(min(max(confidence, 0), 1)))
            listing.match_status = match_status
            listing.verdict = verdict
            listing.observed_at = observed_at

        history_key = (listing.id, history_date)
        history = history_by_key.get(history_key)
        if history is None:
            history = CompetitorPriceHistory(
                competitor_price_id=listing.id,
                recorded_date=history_date,
                price=listed_price,
            )
            db.add(history)
            history_by_key[history_key] = history
            counts["history_rows_created"] += 1
        elif is_latest_observation:
            history.price = listed_price
            counts["history_rows_updated"] += 1

    db.flush()
    return counts
