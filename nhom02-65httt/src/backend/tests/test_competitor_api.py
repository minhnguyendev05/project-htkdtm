"""Tests for authenticated crawler dispatch and canonical competitor-price reads."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.core.rbac import Role
from app.models.market import CompetitorPrice, CompetitorPriceHistory
from fastapi.testclient import TestClient
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
