from __future__ import annotations

import os
from pathlib import Path

from app.db.session import SessionLocal
from app.worker.celery_app import celery_app

from .adapters import (
    DatasetSnapshotAdapter,
    GiarevnAstroAdapter,
    LazadaDirectPdpAdapter,
    PriceHistoryApiAdapter,
    RetailHtmlAdapter,
    TikiOpenApiAdapter,
)
from .normalize import load_dataset
from .persistence import persist_competitor_prices

ADAPTERS = {
    "dataset_snapshot": DatasetSnapshotAdapter,
    "giarevn": GiarevnAstroAdapter,
    "lazada": LazadaDirectPdpAdapter,
    "price_history": PriceHistoryApiAdapter,
    "retail_html": RetailHtmlAdapter,
    "tiki": TikiOpenApiAdapter,
}


def _crawl_and_store(
    adapter_name: str,
    *,
    fetch_kwargs: dict | None = None,
    adapter_options: dict | None = None,
    sku_code: str | None = None,
) -> dict:
    normalized_name = adapter_name.strip().casefold()
    adapter_type = ADAPTERS.get(normalized_name)
    if adapter_type is None:
        raise ValueError(
            f"Adapter không được hỗ trợ: {adapter_name}. "
            f"Chọn một trong: {', '.join(sorted(ADAPTERS))}"
        )

    adapter = adapter_type(**(adapter_options or {}))
    try:
        records = adapter.fetch(**(fetch_kwargs or {}))
    finally:
        adapter.session.close()
    if records.empty:
        return {
            "status": "OK",
            "adapter": normalized_name,
            "rows_received": 0,
            "rows_created": 0,
            "rows_updated": 0,
            "history_rows_created": 0,
            "history_rows_updated": 0,
        }

    with SessionLocal() as db:
        result = persist_competitor_prices(
            db,
            records,
            adapter_name=normalized_name,
            sku_code=sku_code,
        )
        db.commit()

    return {"status": "OK", "adapter": normalized_name, **result}


@celery_app.task(name="market_data.tasks.crawl_and_store_task")
def crawl_and_store_task(
    adapter_name: str,
    fetch_kwargs: dict | None = None,
    adapter_options: dict | None = None,
    sku_code: str | None = None,
) -> dict:
    """Fetch competitor observations and persist them through the app ORM."""
    return _crawl_and_store(
        adapter_name,
        fetch_kwargs=fetch_kwargs,
        adapter_options=adapter_options,
        sku_code=sku_code,
    )


@celery_app.task(name="market_data.tasks.validate_dataset_task")
def validate_dataset_task():
    default = Path(__file__).resolve().parents[3] / "datasets" / "competitor-prices-vnd.csv"
    csv_path = Path(os.getenv("COMPETITOR_DATASET_PATH", str(default)))
    if not csv_path.exists():
        return {"status": "CONFIG_REQUIRED", "message": f"Dataset not found: {csv_path}"}
    df = load_dataset(str(csv_path))
    return {"status": "OK", "rows_valid": int(len(df)),
            "marketplaces": sorted(df["marketplace"].unique().tolist()),
            "observed_at_unique": int(df["observed_at"].nunique())}


@celery_app.task(name="market_data.tasks.ingest_dataset_snapshot_task")
def ingest_dataset_snapshot_task(input_path: str | None = None) -> dict:
    """Load the configured CSV snapshot into the canonical competitor tables."""
    default = Path(__file__).resolve().parents[3] / "datasets" / "competitor-prices-vnd.csv"
    source = Path(input_path or os.getenv("COMPETITOR_DATASET_PATH", str(default)))
    if not source.exists():
        return {"status": "CONFIG_REQUIRED", "message": f"Dataset not found: {source}"}
    return _crawl_and_store(
        "dataset_snapshot",
        adapter_options={"csv_path": str(source)},
    )
