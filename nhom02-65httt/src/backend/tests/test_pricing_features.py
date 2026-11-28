"""Tests for Digital Twin simulator, Closed-loop evaluation, and ModelRun summary endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.rbac import Role
from app.models.erp import Category, CostComponent, Inventory, Product
from app.models.market import CompetitorPrice, SalesChannel, SalesRecord
from app.models.pricing import PriceRecommendation
from app.services.channels import seed_default_channels
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _seed_feature_fixture(db_session: Session) -> tuple[SalesChannel, Product]:
    seed_default_channels(db_session)
    shopee = db_session.query(SalesChannel).filter_by(code="SHOPEE").one()

    category = Category(code="SIM-CAT", name="Thiết bị thông minh")
    db_session.add(category)
    db_session.flush()

    product = Product(
        sku_code="CAM-C200",
        name="Camera WiFi Tapo C200",
        category_id=category.id,
        current_price=Decimal("550000.00"),
    )
    db_session.add(product)
    db_session.flush()

    db_session.add_all(
        [
            CostComponent(
                product_id=product.id,
                purchase_cost=Decimal("350000.00"),
                inbound_cost=Decimal("10000.00"),
                packaging_cost=Decimal("5000.00"),
            ),
            Inventory(
                product_id=product.id,
                warehouse_name="Kho tổng",
                on_hand_qty=100,
                reserved_qty=10,
                reorder_point=15,
                days_of_supply=30,
            ),
            CompetitorPrice(
                product_id=product.id,
                sku_code=product.sku_code,
                product_name=product.name,
                competitor_name="Shop C",
                marketplace_code="SHOPEE",
                source_type="API",
                source_name="shopee-crawler",
                listed_price=Decimal("540000.00"),
                effective_price=Decimal("540000.00"),
                confidence=Decimal("0.90"),
                match_status="AUTO_MATCHED",
                observed_at=datetime.now(UTC) - timedelta(hours=1),
            ),
        ]
    )

    now = datetime.now(UTC)
    for idx in range(14):
        qty = 8 + (idx % 3)
        db_session.add(
            SalesRecord(
                product_id=product.id,
                channel_id=shopee.id,
                order_date=(now - timedelta(days=14 - idx)).date(),
                quantity=qty,
                unit_price=Decimal("550000.00"),
                gross_revenue=Decimal("550000.00") * qty,
                unit_cost=Decimal("365000.00"),
                channel_fee_amount=Decimal("44000.00") * qty,
                net_profit=Decimal("141000.00") * qty,
            )
        )
    db_session.commit()
    return shopee, product


def test_digital_twin_simulate_endpoint(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    shopee, product = _seed_feature_fixture(db_session)
    viewer = make_user("viewer-sim@erp.demo", role=Role.VIEWER)

    resp = client.post(
        "/api/v1/pricing/simulate",
        json={
            "skuId": str(product.id),
            "channelId": str(shopee.id),
            "targetMargin": "0.1800",
            "elasticity": -1.2,
            "candidatePrices": ["450000.00", "520000.00", "550000.00", "600000.00"],
        },
        headers=auth_headers(viewer),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["skuCode"] == "CAM-C200"
    assert len(data["points"]) == 4
    assert data["optimalPrice"] is not None
    assert Decimal(data["optimalPrice"]) >= Decimal(data["floorPrice"])
    # Below-floor candidate (450k) must be marked aboveFloor=False
    first_pt = data["points"][0]
    assert Decimal(first_pt["price"]) == Decimal("450000.00")
    assert first_pt["aboveFloor"] is False


def test_closed_loop_evaluations_and_model_runs_summary(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    shopee, product = _seed_feature_fixture(db_session)
    analyst = make_user("analyst-feat@erp.demo", role=Role.PRICING_ANALYST)
    viewer = make_user("viewer-feat@erp.demo", role=Role.VIEWER)

    # 1) Train models and query summary
    train_resp = client.post(
        "/api/v1/pricing/model-runs/train",
        json={"productId": str(product.id), "channelId": str(shopee.id)},
        headers=auth_headers(analyst),
    )
    assert train_resp.status_code == 201

    summary_resp = client.get(
        "/api/v1/pricing/model-runs/summary",
        headers=auth_headers(viewer),
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()["data"]
    assert summary["bestModelName"] in {"DemandLinearBaseline", "DemandXGBoost"}
    assert len(summary["latestRuns"]) == 2
    assert summary["rmseImprovementPct"] is not None

    # 2) Insert an EXECUTED recommendation created 7 days ago to evaluate against SalesRecord
    now = datetime.now(UTC)
    rec = PriceRecommendation(
        product_id=product.id,
        channel_id=shopee.id,
        status="EXECUTED",
        current_price=Decimal("550000.00"),
        floor_price=Decimal("500000.00"),
        recommended_price=Decimal("540000.00"),
        expected_profit_per_unit=Decimal("130000.00"),
        expected_margin=Decimal("0.2400"),
        unit_cost=Decimal("365000.00"),
        channel_fee_rate=Decimal("0.0800"),
        target_margin=Decimal("0.1800"),
        predicted_demand=Decimal("9.00"),
        data_quality="HIGH",
        algorithm_type="ML_ASSISTED",
        algorithm_version="pricing-engine-1.0.0",
        explanation_json={"summary": "executed"},
        created_by="Lê Minh Tú",
        created_at=now - timedelta(days=7),
        expires_at=now - timedelta(days=6),
    )
    db_session.add(rec)
    db_session.commit()

    eval_resp = client.get(
        "/api/v1/pricing/evaluations?windowDays=14",
        headers=auth_headers(viewer),
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()["data"]
    assert eval_data["evaluatedCount"] == 1
    assert len(eval_data["items"]) == 1
    assert eval_data["items"][0]["skuCode"] == "CAM-C200"
    assert eval_data["items"][0]["salesDaysObserved"] >= 1
    assert Decimal(eval_data["mae"]) >= Decimal("0")
