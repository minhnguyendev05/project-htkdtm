"""Tests for authenticated crawler dispatch and canonical competitor-price reads."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.core.rbac import Role
from app.models.audit_log import AuditLog
from app.models.erp import Category, Product
from app.models.market import CompetitorPrice, CompetitorPriceHistory
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_crawler_run_queues_allow_listed_task(
    client: TestClient,
    make_user,
    auth_headers,
    monkeypatch,
) -> None:
    queued: dict = {}

    class QueuedTask:
        id = "celery-task-123"

    def fake_delay(*args, **kwargs):
        queued["args"] = args
        queued["kwargs"] = kwargs
        return QueuedTask()

    from app.api.v1.endpoints import competitors

    monkeypatch.setattr(competitors.crawl_and_store_task, "delay", fake_delay)
    operator = make_user("crawler-operator@erp.demo", role=Role.PRICING_ANALYST)

    response = client.post(
        "/api/v1/crawler/run",
        headers=auth_headers(operator),
        json={
            "adapterName": "tiki",
            "keyword": "AirPods",
            "limit": 5,
            "skuCode": "ERP-AIRPODS-4",
        },
    )

    assert response.status_code == 202
    assert response.json()["data"] == {
        "taskId": "celery-task-123",
        "adapterName": "tiki",
        "status": "QUEUED",
    }
    assert queued == {
        "args": ("tiki",),
        "kwargs": {
            "fetch_kwargs": {"keyword": "AirPods", "limit": 5},
            "sku_code": "ERP-AIRPODS-4",
        },
    }


def test_crawler_run_rejects_unapproved_remote_url(
    client: TestClient,
    make_user,
    auth_headers,
) -> None:
    operator = make_user("crawler-url-operator@erp.demo", role=Role.PRICING_ANALYST)

    response = client.post(
        "/api/v1/crawler/run",
        headers=auth_headers(operator),
        json={
            "adapterName": "retail_html",
            "url": "http://127.0.0.1/admin",
        },
    )

    assert response.status_code == 422


def test_crawler_run_requires_competitor_write_permission(
    client: TestClient,
    make_user,
    auth_headers,
) -> None:
    viewer = make_user("crawler-viewer@erp.demo", role=Role.VIEWER)

    response = client.post(
        "/api/v1/crawler/run",
        headers=auth_headers(viewer),
        json={"adapterName": "tiki", "keyword": "AirPods"},
    )

    assert response.status_code == 403


def test_list_competitor_prices_reads_canonical_table(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    db_session.add(
        CompetitorPrice(
            id=uuid4(),
            sku_code="ERP-AIRPODS-4",
            product_name="Apple AirPods 4",
            competitor_name="Tiki Trading",
            marketplace_code="TIKI",
            source_type="API",
            source_name="Tiki API",
            external_item_id="listing-1",
            raw_title="Tai nghe Apple AirPods 4",
            listed_price=Decimal("1000000.00"),
            effective_price=Decimal("1000000.00"),
            confidence=Decimal("0.85"),
            match_status="AUTO_MATCHED",
            observed_at=datetime(2026, 11, 27, tzinfo=UTC),
        )
    )
    db_session.commit()
    listing = db_session.query(CompetitorPrice).one()
    db_session.add(
        CompetitorPriceHistory(
            competitor_price_id=listing.id,
            recorded_date=datetime(2026, 11, 27, tzinfo=UTC).date(),
            price=Decimal("1000000.00"),
        )
    )
    db_session.commit()
    viewer = make_user("competitor-reader@erp.demo", role=Role.VIEWER)

    response = client.get(
        "/api/v1/competitor-prices?marketplaceCode=tiki&matchStatus=AUTO_MATCHED",
        headers=auth_headers(viewer),
    )

    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1
    assert response.json()["data"][0]["skuCode"] == "ERP-AIRPODS-4"
    assert response.json()["data"][0]["marketplaceCode"] == "TIKI"

    history = client.get(
        f"/api/v1/competitor-prices/{listing.id}/history",
        headers=auth_headers(viewer),
    )
    assert history.status_code == 200
    assert history.json()["meta"]["total"] == 1
    assert history.json()["data"][0]["price"] == "1000000.00"


def test_cdp_ingest_normalizes_and_persists_structured_capture(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    operator = make_user("cdp-ingest-operator@erp.demo", role=Role.PRICING_ANALYST)

    response = client.post(
        "/api/v1/crawler/ingest-cdp",
        headers=auth_headers(operator),
        json={
            "structuredRecords": [
                {
                    "platform": "shopee",
                    "recordType": "pdp",
                    "shopId": 123,
                    "itemId": 456,
                    "name": "Apple AirPods 4",
                    "priceVnd": 1_000_000,
                    "originalPriceVnd": 2_000_000,
                    "shopName": "Shop Demo",
                    "capturedAtUtc": "2026-11-27T12:00:00Z",
                },
                {
                    "platform": "tiktok_shop",
                    "recordType": "ssr",
                    "itemId": "unpriced-item",
                    "name": "Unpriced product",
                },
            ]
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["rowsCreated"] == 1
    assert response.json()["data"]["rowsSkipped"] == 1
    listing = db_session.scalar(select(CompetitorPrice))
    assert listing is not None
    assert listing.source_type == "API"
    assert listing.marketplace_code == "SHOPEE"
    assert listing.external_item_id == "456"
    assert listing.fake_sale_warning is True
    assert listing.source_url == "https://shopee.vn/product/123/456"


def test_cdp_ingest_rejects_untrusted_marketplace_url(
    client: TestClient,
    make_user,
    auth_headers,
) -> None:
    operator = make_user("cdp-url-operator@erp.demo", role=Role.PRICING_ANALYST)

    response = client.post(
        "/api/v1/crawler/ingest-cdp",
        headers=auth_headers(operator),
        json={
            "structuredRecords": [
                {
                    "platform": "shopee",
                    "itemId": "456",
                    "name": "Product",
                    "priceVnd": 100_000,
                    "url": "https://example.com/product/456",
                }
            ]
        },
    )

    assert response.status_code == 422


def test_review_queue_approves_match_and_audits_decision(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    category = Category(code="REVIEW", name="Review")
    db_session.add(category)
    db_session.flush()
    product = Product(
        sku_code="ERP-REVIEW-1",
        name="Review Product",
        category_id=category.id,
        current_price=Decimal("100000"),
    )
    listing = CompetitorPrice(
        product_name="Observed Product",
        competitor_name="Shop",
        marketplace_code="TIKI",
        source_type="API",
        source_name="Tiki API",
        external_item_id="review-item",
        listed_price=Decimal("90000"),
        confidence=Decimal("0.70"),
        match_status="NEEDS_REVIEW",
        verdict="Manual review required",
        observed_at=datetime(2026, 11, 27, tzinfo=UTC),
    )
    db_session.add_all([product, listing])
    db_session.commit()
    operator = make_user("match-review-operator@erp.demo", role=Role.PRICING_ANALYST)

    response = client.post(
        f"/api/v1/competitor-prices/{listing.id}/review",
        headers=auth_headers(operator),
        json={
            "decision": "APPROVE",
            "skuCode": "erp-review-1",
            "reason": "Model and brand verified",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["matchStatus"] == "MANUALLY_MATCHED"
    assert response.json()["data"]["skuCode"] == "ERP-REVIEW-1"
    event = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "APPROVE_COMPETITOR_MATCH")
    )
    assert event is not None
    assert event.reason == "Model and brand verified"


def test_review_queue_rejects_match_and_is_not_repeatable(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    listing = CompetitorPrice(
        product_name="Suggested ERP name",
        competitor_name="Shop",
        marketplace_code="TIKI",
        source_type="API",
        source_name="Tiki API",
        external_item_id="reject-item",
        raw_title="Observed item title",
        listed_price=Decimal("90000"),
        confidence=Decimal("0.70"),
        match_status="NEEDS_REVIEW",
        observed_at=datetime(2026, 11, 27, tzinfo=UTC),
    )
    db_session.add(listing)
    db_session.commit()
    operator = make_user("match-reject-operator@erp.demo", role=Role.PRICING_ANALYST)
    endpoint = f"/api/v1/competitor-prices/{listing.id}/review"
    headers = auth_headers(operator)

    response = client.post(
        endpoint,
        headers=headers,
        json={"decision": "REJECT", "reason": "Brand and model do not match"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["matchStatus"] == "REJECTED"
    assert response.json()["data"]["productName"] == "Observed item title"
    repeated = client.post(
        endpoint,
        headers=headers,
        json={"decision": "REJECT", "reason": "Repeated decision"},
    )
    assert repeated.status_code == 409
