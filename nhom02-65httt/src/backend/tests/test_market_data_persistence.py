from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest
from app.models.erp import Category, Product
from app.models.market import CompetitorPrice, CompetitorPriceHistory
from app.worker.celery_app import celery_app
from market_data.load_postgres import crawl_active_products
from market_data.persistence import persist_competitor_prices
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_market_data_tasks_use_the_shared_celery_app() -> None:
    celery_app.loader.import_default_modules()

    assert "market_data.tasks.crawl_and_store_task" in celery_app.tasks
    assert "market_data.tasks.ingest_dataset_snapshot_task" in celery_app.tasks


def _records(price: int = 1_000_000) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "marketplace": "TIKI",
                "category": "audio",
                "product_id": "listing-1",
                "title": "Tai nghe Apple AirPods 4",
                "brand": "Apple",
                "seller": "Tiki Trading",
                "price_vnd": price,
                "observed_at": datetime(2026, 11, 27, tzinfo=UTC),
                "url": "https://tiki.vn/listing-1",
                "confidence": 0.85,
            }
        ]
    )


def _create_product(db: Session) -> Product:
    category = Category(code="AUDIO", name="Audio")
    db.add(category)
    db.flush()
    product = Product(
        sku_code="ERP-AIRPODS-4",
        name="Apple AirPods 4",
        brand="Apple",
        model_code="AIRPODS4",
        category_id=category.id,
        current_price=Decimal("1200000"),
    )
    db.add(product)
    db.flush()
    return product


def test_persist_links_matching_product_and_creates_daily_history(
    db_session: Session,
) -> None:
    product = _create_product(db_session)

    result = persist_competitor_prices(
        db_session,
        _records(),
        adapter_name="tiki",
    )
    db_session.commit()

    listing = db_session.scalar(select(CompetitorPrice))
    history = db_session.scalar(select(CompetitorPriceHistory))
    assert result == {
        "rows_received": 1,
        "rows_created": 1,
        "rows_updated": 0,
        "history_rows_created": 1,
        "history_rows_updated": 0,
    }
    assert listing is not None
    assert listing.product_id == product.id
    assert listing.sku_code == product.sku_code
    assert listing.source_type == "API"
    assert listing.match_status == "AUTO_MATCHED"
    assert listing.listed_price == Decimal("1000000.00")
    assert history is not None
    assert history.price == Decimal("1000000.00")


def test_persist_upserts_listing_and_history_without_duplicate_rows(
    db_session: Session,
) -> None:
    _create_product(db_session)
    persist_competitor_prices(db_session, _records(), adapter_name="tiki")
    db_session.commit()

    result = persist_competitor_prices(
        db_session,
        _records(price=950_000),
        adapter_name="tiki",
    )
    db_session.commit()

    assert result["rows_created"] == 0
    assert result["rows_updated"] == 1
    assert result["history_rows_created"] == 0
    assert result["history_rows_updated"] == 1
    assert len(db_session.scalars(select(CompetitorPrice)).all()) == 1
    assert len(db_session.scalars(select(CompetitorPriceHistory)).all()) == 1
    assert db_session.scalar(select(CompetitorPrice)).listed_price == Decimal("950000.00")
    assert db_session.scalar(select(CompetitorPriceHistory)).price == Decimal("950000.00")


def test_persist_flags_discount_at_or_above_50_percent(
    db_session: Session,
) -> None:
    _create_product(db_session)
    records = _records().assign(original_price_vnd=2_000_000)

    persist_competitor_prices(db_session, records, adapter_name="tiki")
    db_session.commit()

    listing = db_session.scalar(select(CompetitorPrice))
    assert listing is not None
    assert listing.fake_sale_warning is True


def test_persist_does_not_flag_discount_below_50_percent(
    db_session: Session,
) -> None:
    _create_product(db_session)
    records = _records().assign(original_price_vnd=1_500_000)

    persist_competitor_prices(db_session, records, adapter_name="tiki")
    db_session.commit()

    listing = db_session.scalar(select(CompetitorPrice))
    assert listing is not None
    assert listing.fake_sale_warning is False


def test_unmatched_listing_is_saved_for_manual_review(db_session: Session) -> None:
    _create_product(db_session)
    records = _records().assign(
        title="Unrelated toaster model Z900",
        brand="Other",
    )

    result = persist_competitor_prices(
        db_session,
        records,
        adapter_name="tiki",
    )
    db_session.commit()

    listing = db_session.scalar(select(CompetitorPrice))
    assert result["rows_created"] == 1
    assert listing is not None
    assert listing.product_id is None
    assert listing.sku_code is None
    assert listing.match_status == "REJECTED"


def test_crawl_active_products_persists_60_skus_without_network(
    db_session: Session,
) -> None:
    category = Category(code="BATCH", name="Batch")
    db_session.add(category)
    db_session.flush()
    products = [
        Product(
            sku_code=f"ERP-{index:03}",
            name=f"Device Model {index:03}",
            brand="DemoBrand",
            category_id=category.id,
            current_price=Decimal("100000"),
        )
        for index in range(60)
    ]
    db_session.add_all(products)
    db_session.flush()

    class FakeAdapter:
        def __init__(self, **kwargs) -> None:
            self.session = self
            self.keywords: list[str] = []

        def fetch(self, *, keyword: str, limit: int) -> pd.DataFrame:
            self.keywords.append(keyword)
            index = int(keyword.rsplit(" ", 1)[-1])
            return pd.DataFrame(
                [
                    {
                        "marketplace": "TIKI",
                        "category": "batch",
                        "product_id": f"listing-{index:03}",
                        "title": keyword,
                        "brand": "DemoBrand",
                        "price_vnd": 90_000 + index,
                        "observed_at": datetime(2026, 11, 27, tzinfo=UTC),
                    }
                ]
            )

        def close(self) -> None:
            return None

    result = crawl_active_products(
        db_session,
        limit=60,
        min_products=60,
        min_delay=0,
        max_delay=0,
        adapter_factory=FakeAdapter,
    )
    db_session.commit()

    assert result["products_requested"] == 60
    assert result["products_with_results"] == 60
    assert result["rows_created"] == 60
    assert result["history_rows_created"] == 60
    assert len(db_session.scalars(select(CompetitorPrice)).all()) == 60
    assert len(db_session.scalars(select(CompetitorPriceHistory)).all()) == 60


def test_crawl_active_products_requires_minimum_active_skus(
    db_session: Session,
) -> None:
    _create_product(db_session)

    with pytest.raises(ValueError, match="cần ít nhất 2 SKU"):
        crawl_active_products(
            db_session,
            limit=60,
            min_products=2,
            adapter_factory=lambda **kwargs: None,
        )


def test_celery_beat_schedules_daily_bulk_crawl() -> None:
    schedule = celery_app.conf.beat_schedule[
        "market-data-daily-active-product-crawl"
    ]

    assert schedule["task"] == "market_data.tasks.crawl_active_products_task"
    assert schedule["schedule"].hour == {2}
    assert schedule["schedule"].minute == {0}
