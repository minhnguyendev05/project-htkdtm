"""Integration and RBAC tests for Smart Pricing API v1 routers and ML preprocessing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from app.core.rbac import Role
from app.models.erp import Category, CostComponent, Inventory, Product
from app.models.market import ChannelProduct, CompetitorPrice, SalesChannel, SalesRecord
from app.models.pricing import PriceRecommendation
from app.services.channels import seed_default_channels
from fastapi.testclient import TestClient
from ml.preprocessing import clean_price_history, compute_pmin
from sqlalchemy.orm import Session


def _seed_catalog(db_session: Session) -> tuple[SalesChannel, Category, Product, ChannelProduct]:
    seed_default_channels(db_session)
    shopee = db_session.query(SalesChannel).filter_by(code="SHOPEE").one()

    category = Category(code="ACC", name="Phụ kiện công nghệ")
    db_session.add(category)
    db_session.flush()

    product = Product(
        sku_code="MOUSE-M185",
        name="Chuột không dây Logitech M185",
        category_id=category.id,
        current_price=Decimal("250000.00"),
    )
    db_session.add(product)
    db_session.flush()

    cost = CostComponent(
        product_id=product.id,
        purchase_cost=Decimal("130000.00"),
        inbound_cost=Decimal("10000.00"),
        packaging_cost=Decimal("5000.00"),
        other_cost=Decimal("5000.00"),
    )
    inventory = Inventory(
        product_id=product.id,
        warehouse_name="Kho HCM",
        on_hand_qty=120,
        reserved_qty=10,
        reorder_point=20,
        days_of_supply=45,
    )
    listing = ChannelProduct(
        product_id=product.id,
        channel_id=shopee.id,
        external_listing_id="SHP-M185-001",
        external_sku="SHP-MOUSE-M185",
        current_price=Decimal("250000.00"),
        sync_status="PENDING",
    )
    now = datetime.now(UTC)
    comp1 = CompetitorPrice(
        product_id=product.id,
        sku_code=product.sku_code,
        product_name=product.name,
        competitor_name="Shop A",
        marketplace_code="SHOPEE",
        source_type="API",
        source_name="shopee-crawler",
        listed_price=Decimal("245000.00"),
        effective_price=Decimal("242000.00"),
        confidence=Decimal("0.92"),
        match_status="AUTO_MATCHED",
        observed_at=now - timedelta(hours=2),
    )
    comp2 = CompetitorPrice(
        product_id=product.id,
        sku_code=product.sku_code,
        product_name=product.name,
        competitor_name="Shop B",
        marketplace_code="SHOPEE",
        source_type="API",
        source_name="shopee-crawler",
        listed_price=Decimal("255000.00"),
        effective_price=Decimal("250000.00"),
        confidence=Decimal("0.88"),
        match_status="AUTO_MATCHED",
        observed_at=now - timedelta(hours=4),
    )
    sales_rows = [
        SalesRecord(
            product_id=product.id,
            channel_id=shopee.id,
            order_date=(now - timedelta(days=offset)).date(),
            quantity=5 + (offset % 3),
            unit_price=Decimal("250000.00"),
            gross_revenue=Decimal("1250000.00"),
            unit_cost=Decimal("150000.00"),
            channel_fee_amount=Decimal("150000.00"),
            net_profit=Decimal("350000.00"),
        )
        for offset in range(7, 0, -1)
    ]

    db_session.add_all([cost, inventory, listing, comp1, comp2, *sales_rows])
    db_session.commit()
    return shopee, category, product, listing


def test_pricing_rules_crud_guardrails_and_rbac(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    shopee, category, _, _ = _seed_catalog(db_session)
    analyst = make_user("analyst@erp.demo", role=Role.PRICING_ANALYST, full_name="Lê Minh Tú")
    viewer = make_user("viewer@erp.demo", role=Role.VIEWER, full_name="Nguyễn Xem")

    now = datetime.now(UTC)
    payload = {
        "name": "Bám giá Shopee Phụ kiện",
        "ruleType": "COMPETITOR_MATCH",
        "priority": 10,
        "scopeLabel": "Phụ kiện công nghệ / Shopee",
        "categoryId": str(category.id),
        "channelId": str(shopee.id),
        "minMargin": "0.1500",
        "maxPriceChangePct": "0.2000",
        "approvalRequired": True,
        "status": "DRAFT",
        "startsAt": (now - timedelta(hours=1)).isoformat(),
        "endsAt": (now + timedelta(days=30)).isoformat(),
    }

    # VIEWER cannot create rules
    forbidden = client.post("/api/v1/pricing-rules", json=payload, headers=auth_headers(viewer))
    assert forbidden.status_code == 403

    # PRICING_ANALYST creates rule
    created = client.post("/api/v1/pricing-rules", json=payload, headers=auth_headers(analyst))
    assert created.status_code == 201
    rule_data = created.json()["data"]
    rule_id = rule_data["id"]
    assert rule_data["status"] == "DRAFT"
    assert rule_data["ruleType"] == "COMPETITOR_MATCH"

    # VIEWER can read rules
    listed = client.get("/api/v1/pricing-rules", headers=auth_headers(viewer))
    assert listed.status_code == 200
    assert listed.json()["meta"]["total"] == 1

    # Activate then archive rule; reactivating archived rule must be blocked
    activated = client.post(
        f"/api/v1/pricing-rules/{rule_id}/status",
        json={"status": "ACTIVE"},
        headers=auth_headers(analyst),
    )
    assert activated.status_code == 200
    assert activated.json()["data"]["status"] == "ACTIVE"

    archived = client.patch(
        f"/api/v1/pricing-rules/{rule_id}",
        json={"status": "ARCHIVED"},
        headers=auth_headers(analyst),
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "ARCHIVED"

    reactivate = client.post(
        f"/api/v1/pricing-rules/{rule_id}/status",
        json={"status": "ACTIVE"},
        headers=auth_headers(analyst),
    )
    assert reactivate.status_code == 409

    # MARGIN_GUARD rule cannot be paused
    guard_payload = {
        **payload,
        "name": "Rào chắn biên lợi nhuận",
        "ruleType": "MARGIN_GUARD",
        "status": "ACTIVE",
    }
    guard_resp = client.post(
        "/api/v1/pricing-rules", json=guard_payload, headers=auth_headers(analyst)
    )
    assert guard_resp.status_code == 201
    guard_id = guard_resp.json()["data"]["id"]

    pause_guard = client.post(
        f"/api/v1/pricing-rules/{guard_id}/status",
        json={"status": "PAUSED"},
        headers=auth_headers(analyst),
    )
    assert pause_guard.status_code == 409


def test_pricing_preview_adhoc_and_catalog_modes(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    shopee, _, product, _ = _seed_catalog(db_session)
    viewer = make_user("viewer@erp.demo", role=Role.VIEWER)

    # Ad-hoc preview mode
    adhoc_resp = client.post(
        "/api/v1/pricing/preview",
        json={
            "cost": "100.00",
            "competitorPrice": "135.00",
            "channelFeeRate": "0.0500",
            "targetMargin": "0.1500",
        },
        headers=auth_headers(viewer),
    )
    assert adhoc_resp.status_code == 200
    adhoc_data = adhoc_resp.json()["data"]
    assert adhoc_data["mode"] == "ADHOC"
    assert Decimal(adhoc_data["pmin"]) == Decimal("125.00")
    assert Decimal(adhoc_data["suggestedPrice"]) >= Decimal(adhoc_data["pmin"])
    assert len(adhoc_data["items"]) == 1

    # Catalog DB-backed preview mode
    catalog_resp = client.post(
        "/api/v1/pricing/preview",
        json={
            "skuIds": [str(product.id)],
            "channelId": str(shopee.id),
            "objective": "COMPETITIVE",
            "targetMargin": "0.1500",
        },
        headers=auth_headers(viewer),
    )
    assert catalog_resp.status_code == 200
    catalog_data = catalog_resp.json()["data"]
    assert catalog_data["mode"] == "CATALOG"
    assert len(catalog_data["items"]) == 1
    item = catalog_data["items"][0]
    assert item["skuCode"] == "MOUSE-M185"
    assert item["competitorFresh"] is True
    assert item["dataQuality"] == "HIGH"
    assert item["noSafePrice"] is False
    assert Decimal(item["suggestedPrice"]) >= Decimal(item["floorPrice"])

    # Missing both catalog and ad-hoc fields -> 422
    invalid = client.post(
        "/api/v1/pricing/preview",
        json={"objective": "PROFIT"},
        headers=auth_headers(viewer),
    )
    assert invalid.status_code == 422


def test_pricing_run_approval_workflow_and_execution_integration(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    shopee, _, product, listing = _seed_catalog(db_session)
    viewer = make_user("viewer@erp.demo", role=Role.VIEWER, full_name="Viewer")
    analyst = make_user("analyst@erp.demo", role=Role.PRICING_ANALYST, full_name="Lê Minh Tú")
    manager = make_user("manager@erp.demo", role=Role.MANAGER, full_name="Nguyễn Anh Minh")

    run_payload = {
        "skuIds": [str(product.id)],
        "channelId": str(shopee.id),
        "objective": "PROFIT",
        "targetMargin": "0.1500",
        "mode": "ML_ASSISTED",
    }

    # RBAC: VIEWER cannot run pricing
    denied = client.post("/api/v1/pricing/run", json=run_payload, headers=auth_headers(viewer))
    assert denied.status_code == 403

    # PRICING_ANALYST runs pricing -> persists PriceRecommendation
    run_resp = client.post("/api/v1/pricing/run", json=run_payload, headers=auth_headers(analyst))
    assert run_resp.status_code == 201
    run_data = run_resp.json()["data"]
    assert run_data["requestedCount"] == 1
    assert len(run_data["results"]) == 1
    rec = run_data["results"][0]
    rec_id = rec["id"]
    floor_price = Decimal(rec["floorPrice"])
    assert Decimal(rec["recommendedPrice"]) >= floor_price
    assert rec["skuCode"] == "MOUSE-M185"
    assert rec["algorithmType"] == "ML_ASSISTED"
    assert "factors" in rec["explanation"]
    assert "engine" in rec["explanation"]

    # List & detail endpoints work
    listed = client.get(
        "/api/v1/recommendations?q=MOUSE-M185",
        headers=auth_headers(viewer),
    )
    assert listed.status_code == 200
    assert listed.json()["meta"]["total"] == 1

    # Submit DRAFT -> PENDING_APPROVAL if still DRAFT
    if rec["status"] == "DRAFT":
        submitted = client.post(
            f"/api/v1/recommendations/{rec_id}/submit",
            headers=auth_headers(analyst),
        )
        assert submitted.status_code == 200
        assert submitted.json()["data"]["status"] == "PENDING_APPROVAL"

    # RBAC: PRICING_ANALYST cannot self-approve
    self_approve = client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={"reason": "Tự duyệt"},
        headers=auth_headers(analyst),
    )
    assert self_approve.status_code == 403

    # MANAGER cannot adjust price below floor_price
    below_floor = client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={"adjustedPrice": str(floor_price - Decimal("10000.00"))},
        headers=auth_headers(manager),
    )
    assert below_floor.status_code == 409

    # MANAGER approves with valid adjustedPrice >= floor_price
    adjusted_price = floor_price + Decimal("15000.00")
    approved = client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={
            "adjustedPrice": str(adjusted_price),
            "reason": "Điều chỉnh nhẹ theo chiến dịch tháng",
        },
        headers=auth_headers(manager),
    )
    assert approved.status_code == 200
    approved_data = approved.json()["data"]
    assert approved_data["status"] == "APPROVED"
    assert len(approved_data["approvals"]) == 1
    assert approved_data["approvals"][0]["decision"] == "APPROVED"
    assert Decimal(approved_data["approvals"][0]["adjustedPrice"]) == adjusted_price

    # End-to-end handoff to existing executions endpoint!
    sync_resp = client.post(
        f"/api/v1/executions/from-recommendation/{rec_id}",
        headers=auth_headers(manager),
    )
    assert sync_resp.status_code == 201
    sync_data = sync_resp.json()["data"]
    assert sync_data["status"] == "SUCCEEDED"
    assert Decimal(sync_data["requestedPrice"]) == adjusted_price

    db_session.refresh(listing)
    assert listing.current_price == adjusted_price
    assert listing.sync_status == "SYNCED"

    # Verify audit logs recorded
    audit_resp = client.get(
        "/api/v1/audit-logs?action=APPROVE_RECOMMENDATION",
        headers=auth_headers(manager),
    )
    assert audit_resp.status_code == 200
    assert audit_resp.json()["meta"]["total"] == 1


def test_recommendation_reject_and_expired_handling(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    shopee, _, product, _ = _seed_catalog(db_session)
    analyst = make_user("analyst@erp.demo", role=Role.PRICING_ANALYST)
    manager = make_user("manager@erp.demo", role=Role.MANAGER)

    run_resp = client.post(
        "/api/v1/pricing/run",
        json={
            "skuIds": [str(product.id)],
            "channelId": str(shopee.id),
            "objective": "CLEAR_STOCK",
            "targetMargin": "0.1000",
            "submitForApproval": True,
        },
        headers=auth_headers(analyst),
    )
    assert run_resp.status_code == 201
    rec_id = run_resp.json()["data"]["results"][0]["id"]

    # Reject with reason
    rejected = client.post(
        f"/api/v1/recommendations/{rec_id}/reject",
        json={"reason": "Chờ cập nhật giá nhập mới"},
        headers=auth_headers(manager),
    )
    assert rejected.status_code == 200
    rejected_data = rejected.json()["data"]
    assert rejected_data["status"] == "REJECTED"
    assert rejected_data["approvals"][0]["reason"] == "Chờ cập nhật giá nhập mới"

    # Cannot approve an already REJECTED recommendation
    approve_again = client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        headers=auth_headers(manager),
    )
    assert approve_again.status_code == 409

    # Expired recommendation returns 409 and marks EXPIRED
    run_resp_2 = client.post(
        "/api/v1/pricing/run",
        json={
            "skuIds": [str(product.id)],
            "channelId": str(shopee.id),
            "targetMargin": "0.1200",
        },
        headers=auth_headers(analyst),
    )
    rec_id_2 = run_resp_2.json()["data"]["results"][0]["id"]
    rec_row = db_session.get(PriceRecommendation, UUID(rec_id_2))
    assert rec_row is not None
    rec_row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    expired_resp = client.post(
        f"/api/v1/recommendations/{rec_id_2}/approve",
        headers=auth_headers(manager),
    )
    assert expired_resp.status_code == 409
    db_session.refresh(rec_row)
    assert rec_row.status == "EXPIRED"


def test_pricing_run_reports_no_safe_price_skus(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    shopee, category, _, _ = _seed_catalog(db_session)
    analyst = make_user("analyst-nosafe@erp.demo", role=Role.PRICING_ANALYST)

    # Current price 100k, cost 95k -> floor > 120k (exceeds +20% max change bound)
    risky_product = Product(
        sku_code="RISKY-SKU-01",
        name="Sản phẩm giá vốn sát giá bán",
        category_id=category.id,
        current_price=Decimal("100000.00"),
    )
    db_session.add(risky_product)
    db_session.flush()
    db_session.add(
        CostComponent(
            product_id=risky_product.id,
            purchase_cost=Decimal("95000.00"),
        )
    )
    db_session.commit()

    resp = client.post(
        "/api/v1/pricing/run",
        json={
            "skuIds": [str(risky_product.id)],
            "channelId": str(shopee.id),
            "targetMargin": "0.1800",
        },
        headers=auth_headers(analyst),
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["results"] == []
    assert data["noSafePriceSkuCodes"] == ["RISKY-SKU-01"]


def test_ml_preprocessing_helpers() -> None:
    cleaned = clean_price_history(
        [
            {"sku": "SKU-1", "date": "2026-11-01", "price": 150000},
            {"sku": "SKU-2", "date": "2026-11-01", "price": None},
            {"sku": "SKU-3", "date": "2026-11-01", "price": -5000},
            {"sku": "SKU-4", "date": "2026-11-01", "price": 0},
        ]
    )
    assert cleaned == [{"sku": "SKU-1", "date": "2026-11-01", "price": 150000.0}]
    assert compute_pmin(100.0, fee_rate=0.05, margin=0.10) == 117.65
    with pytest.raises(ValueError):
        compute_pmin(100.0, fee_rate=0.6, margin=0.4)
