"""Execution synchronization service connecting PriceSyncLog and MarketplaceAdapter."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ProviderUnavailableError
from app.db.base import utc_now
from app.integrations.marketplace import (
    MarketplaceAdapter,
    PriceUpdateRequest,
    SyncMode,
    get_adapter,
)
from app.models.market import ChannelProduct
from app.models.pricing import PriceSyncLog

MAX_ATTEMPTS = 3


def execute_sync_log(
    db: Session,
    sync_log: PriceSyncLog,
    *,
    external_listing_id: str | None = None,
    external_sku: str | None = None,
    adapter_override: MarketplaceAdapter | None = None,
) -> PriceSyncLog:
    """Execute a queued PriceSyncLog via MarketplaceAdapter and update persisted status."""
    sync_log.status = "RUNNING"

    listing_id = external_listing_id or sync_log.sku_code
    channel_sku = external_sku or f"{sync_log.channel_code}-{sync_log.sku_code}"
    if sync_log.product_id is not None and sync_log.channel_id is not None:
        mapping = db.scalar(
            select(ChannelProduct).where(
                ChannelProduct.product_id == sync_log.product_id,
                ChannelProduct.channel_id == sync_log.channel_id,
            )
        )
        if mapping is not None:
            listing_id = external_listing_id or mapping.external_listing_id
            channel_sku = external_sku or mapping.external_sku
    else:
        mapping = None

    attempt_key = (
        sync_log.idempotency_key
        if sync_log.attempts <= 1
        else f"{sync_log.idempotency_key}#attempt-{sync_log.attempts}"
    )

    try:
        adapter = adapter_override or get_adapter(
            sync_log.channel_code,
            mode="LIVE" if sync_log.mode == "LIVE" else "SIMULATED",
        )
    except ProviderUnavailableError as exc:
        sync_log.status = "FAILED"
        sync_log.sync_mode = SyncMode.API_CONFIRMED.value
        sync_log.http_status = 503
        sync_log.error_code = exc.code
        sync_log.error_message = exc.message
        return sync_log

    result = adapter.update_price(
        PriceUpdateRequest(
            channel_code=sync_log.channel_code,
            external_listing_id=listing_id,
            external_sku=channel_sku,
            new_price=sync_log.requested_price,
            previous_price=sync_log.previous_price,
            idempotency_key=attempt_key,
        )
    )

    sync_log.sync_mode = result.sync_mode.value
    sync_log.http_status = result.http_status
    sync_log.external_reference = result.external_reference
    sync_log.error_code = result.error_code
    sync_log.error_message = result.error_message
    sync_log.status = "SUCCEEDED" if result.success else "FAILED"

    if result.success and mapping is not None:
        mapping.current_price = sync_log.requested_price
        mapping.sync_status = "SYNCED"
        mapping.last_synced_at = utc_now()

    return sync_log
