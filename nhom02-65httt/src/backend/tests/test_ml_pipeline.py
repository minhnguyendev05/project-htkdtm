"""Unit and API integration tests for app.ml (DemandBaseline, XGBoost, ModelRun, guardrails)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
from app.core.rbac import Role
from app.ml.demand_baseline import DemandBaseline
from app.ml.model_runs import run_model_comparison
from app.models.erp import Category, CostComponent, Inventory, Product
from app.models.market import SalesChannel, SalesRecord
from app.models.pricing import ModelRun, PricingRule
from app.services.channels import seed_default_channels
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _seed_sales_history(
    db_session: Session,
    *,
    days: int = 14,
) -> tuple[SalesChannel, Category, Product]:
    seed_default_channels(db_session)
    shopee = db_session.query(SalesChannel).filter_by(code="SHOPEE").one()

    category = Category(code="ML-ACC", name="Phụ kiện ML")
    db_session.add(category)
    db_session.flush()

    product = Product(
        sku_code="KB-K380",
        name="Bàn phím Logitech K380",
        category_id=category.id,
        current_price=Decimal("650000.00"),
    )
    db_session.add(product)
    db_session.flush()

    db_session.add_all(
        [
            CostComponent(
                product_id=product.id,
                purchase_cost=Decimal("420000.00"),
                inbound_cost=Decimal("15000.00"),
                packaging_cost=Decimal("5000.00"),
            ),
            Inventory(
                product_id=product.id,
                warehouse_name="Kho HN",
                on_hand_qty=80,
                reserved_qty=5,
                reorder_point=15,
                days_of_supply=35,
            ),
        ]
    )

    now = datetime.now(UTC)
    for idx in range(days):
        qty = 6 + (idx % 4) + (idx // 5)
        unit_price = Decimal("650000.00") if idx % 2 == 0 else Decimal("635000.00")
        db_session.add(
            SalesRecord(
                product_id=product.id,
                channel_id=shopee.id,
                order_date=(now - timedelta(days=days - idx)).date(),
                quantity=qty,
                unit_price=unit_price,
                gross_revenue=unit_price * qty,
                unit_cost=Decimal("440000.00"),
                channel_fee_amount=(unit_price * Decimal("0.08")) * qty,
                net_profit=((unit_price * Decimal("0.92")) - Decimal("440000.00")) * qty,
            )
        )
    db_session.commit()
    return shopee, category, product


def test_demand_baseline_out_of_sample_prediction() -> None:
    X_train = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]], dtype=float)
    y_train = np.array([2.0, 4.0, 6.0, 8.0, 10.0], dtype=float)

    model = DemandBaseline().fit(X_train, y_train)
    pred = model.predict(np.array([[6.0], [7.0]], dtype=float))

    assert np.allclose(pred, np.array([12.0, 14.0]), atol=1e-6)


def test_run_model_comparison_persists_mae_rmse_to_model_runs_table(
    db_session: Session,
) -> None:
    X = np.array([[float(i), 100.0 + i, 1.0, float(i), float(i % 7)] for i in range(1, 21)])
    y = np.array([2.0 * i + 5.0 for i in range(1, 21)], dtype=float)

    runs = run_model_comparison(db_session, X, y, split_idx=15, actor="Lê Minh Tú")
    assert len(runs) == 2
    assert {r.algorithm_type for r in runs} == {"LINEAR_REGRESSION", "XGBOOST"}

    stored = db_session.query(ModelRun).all()
    assert len(stored) == 2
    for row in stored:
        assert row.train_samples == 15
        assert row.test_samples == 5
        assert row.mae >= Decimal("0")
        assert row.rmse >= row.mae


def test_model_runs_train_and_list_endpoints_with_rbac(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    shopee, _, product = _seed_sales_history(db_session, days=14)
    viewer = make_user("viewer-ml@erp.demo", role=Role.VIEWER)
    analyst = make_user("analyst-ml@erp.demo", role=Role.PRICING_ANALYST, full_name="Lê Minh Tú")

    # VIEWER cannot trigger training
    denied = client.post(
        "/api/v1/pricing/model-runs/train",
        json={"productId": str(product.id), "channelId": str(shopee.id)},
        headers=auth_headers(viewer),
    )
    assert denied.status_code == 403

    # PRICING_ANALYST trains & persists LinearRegression vs XGBoost
    trained = client.post(
        "/api/v1/pricing/model-runs/train",
        json={"productId": str(product.id), "channelId": str(shopee.id), "splitRatio": 0.75},
        headers=auth_headers(analyst),
    )
    assert trained.status_code == 201
    data = trained.json()["data"]
    assert len(data) == 2
    assert {item["algorithmType"] for item in data} == {"LINEAR_REGRESSION", "XGBOOST"}
    assert all(Decimal(item["mae"]) >= 0 for item in data)

    # VIEWER can read persisted model runs
    listed = client.get("/api/v1/pricing/model-runs", headers=auth_headers(viewer))
    assert listed.status_code == 200
    assert listed.json()["meta"]["total"] == 2


def test_ml_assisted_run_enforces_margin_guard_and_reports_rule_conflicts(
    client: TestClient,
    db_session: Session,
    make_user,
    auth_headers,
) -> None:
    shopee, category, product = _seed_sales_history(db_session, days=14)
    analyst = make_user("analyst-guard@erp.demo", role=Role.PRICING_ANALYST)
    now = datetime.now(UTC)

    # Add system-wide MARGIN_GUARD requiring higher min_margin (0.22) + two conflicting rules
    guard = PricingRule(
        name="Margin Guard 22%",
        rule_type="MARGIN_GUARD",
        priority=1,
        scope_label="Toàn hệ thống",
        category_id=None,
        channel_id=None,
        min_margin=Decimal("0.2200"),
        max_price_change_pct=Decimal("0.2000"),
        approval_required=True,
        status="ACTIVE",
        starts_at=now - timedelta(days=1),
    )
    rule_a = PricingRule(
        name="Chiến dịch A",
        rule_type="COMPETITOR_MATCH",
        priority=10,
        scope_label="Phụ kiện ML / Shopee",
        category_id=category.id,
        channel_id=shopee.id,
        min_margin=Decimal("0.1500"),
        max_price_change_pct=Decimal("0.2000"),
        approval_required=True,
        status="ACTIVE",
        starts_at=now - timedelta(days=1),
    )
    rule_b = PricingRule(
        name="Chiến dịch B",
        rule_type="SKIMMING",
        priority=10,
        scope_label="Phụ kiện ML / Shopee",
        category_id=category.id,
        channel_id=shopee.id,
        min_margin=Decimal("0.1800"),
        max_price_change_pct=Decimal("0.2000"),
        approval_required=True,
        status="ACTIVE",
        starts_at=now - timedelta(days=1),
    )
    db_session.add_all([guard, rule_a, rule_b])
    db_session.commit()

    resp = client.post(
        "/api/v1/pricing/run",
        json={
            "skuIds": [str(product.id)],
            "channelId": str(shopee.id),
            "objective": "PROFIT",
            "targetMargin": "0.1200",
            "mode": "ML_ASSISTED",
        },
        headers=auth_headers(analyst),
    )
    assert resp.status_code == 201
    rec = resp.json()["data"]["results"][0]

    # MARGIN_GUARD raised effective targetMargin to 0.2200
    assert Decimal(rec["targetMargin"]) == Decimal("0.2200")
    assert Decimal(rec["recommendedPrice"]) >= Decimal(rec["floorPrice"])

    # ML_ASSISTED used real XGBoost forecast (>=12 sales records)
    engine_meta = rec["explanation"]["engine"]
    assert engine_meta["mlModelUsed"] == "XGBoost"
    assert engine_meta["mlPredictedDemand"] is not None
    assert len(engine_meta["ruleConflicts"]) == 1
    assert engine_meta["ruleConflicts"][0]["code"] == "RULE_PRIORITY_CONFLICT"
