"""Add market-data review state and shared BI views.

Revision ID: 0003_market_data_bi_views
Revises: 0002_erp_smart_pricing_schema
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_market_data_bi_views"
down_revision: str | Sequence[str] | None = "0002_erp_smart_pricing_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_competitor_prices_match_status_valid"),
        "competitor_prices",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_competitor_prices_match_status_valid"),
        "competitor_prices",
        "match_status IN ('AUTO_MATCHED', 'MANUALLY_MATCHED', 'NEEDS_REVIEW', 'REJECTED')",
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_bi_sales_profitability AS
        SELECT
            sales.order_date,
            product.sku_code,
            product.name AS product_name,
            category.code AS category_code,
            category.name AS category_name,
            channel.code AS channel_code,
            channel.name AS channel_name,
            sales.quantity,
            sales.unit_price,
            sales.gross_revenue,
            sales.unit_cost,
            sales.quantity * sales.unit_cost AS cost_of_goods,
            sales.gross_revenue - (sales.quantity * sales.unit_cost) AS gross_profit,
            sales.net_profit,
            100.0 * sales.net_profit / NULLIF(sales.gross_revenue, 0) AS net_margin_pct,
            recommendation.floor_price AS pmin
        FROM sales_records AS sales
        JOIN products AS product ON product.id = sales.product_id
        JOIN categories AS category ON category.id = product.category_id
        JOIN sales_channels AS channel ON channel.id = sales.channel_id
        LEFT JOIN LATERAL (
            SELECT rec.floor_price
            FROM price_recommendations AS rec
            WHERE rec.product_id = sales.product_id
              AND rec.channel_id = sales.channel_id
              AND rec.created_at < sales.order_date + INTERVAL '1 day'
            ORDER BY rec.created_at DESC, rec.id DESC
            LIMIT 1
        ) AS recommendation ON TRUE
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_bi_competitor_price_history AS
        SELECT
            history.recorded_date,
            listing.id AS competitor_price_id,
            listing.product_id,
            listing.sku_code,
            COALESCE(product.name, listing.product_name) AS product_name,
            product.current_price AS erp_current_price,
            category.code AS category_code,
            category.name AS category_name,
            listing.competitor_name,
            listing.marketplace_code,
            listing.source_type,
            listing.source_name,
            listing.source_url,
            listing.external_item_id,
            listing.raw_title,
            history.price,
            listing.listed_price AS latest_listed_price,
            listing.effective_price AS latest_effective_price,
            listing.sold_count,
            listing.rating,
            listing.confidence,
            listing.match_status,
            listing.fake_sale_warning,
            listing.is_outlier,
            listing.observed_at
        FROM competitor_price_history AS history
        JOIN competitor_prices AS listing
          ON listing.id = history.competitor_price_id
        LEFT JOIN products AS product ON product.id = listing.product_id
        LEFT JOIN categories AS category ON category.id = product.category_id
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_bi_pricing_strategy_performance AS
        SELECT
            recommendation.id AS recommendation_id,
            recommendation.created_at,
            product.sku_code,
            product.name AS product_name,
            category.code AS category_code,
            category.name AS category_name,
            channel.code AS channel_code,
            channel.name AS channel_name,
            COALESCE(rule.rule_type, recommendation.algorithm_type) AS strategy,
            recommendation.algorithm_type,
            recommendation.current_price,
            recommendation.recommended_price,
            recommendation.floor_price,
            recommendation.expected_profit_per_unit,
            recommendation.expected_margin,
            recommendation.predicted_demand,
            recommendation.status AS recommendation_status,
            approval.decision AS latest_approval_decision,
            approval.decided_at AS latest_approval_at,
            sync.status AS latest_sync_status,
            sync.previous_price AS synced_previous_price,
            sync.requested_price AS synced_requested_price,
            sync.updated_at AS latest_sync_at
        FROM price_recommendations AS recommendation
        JOIN products AS product ON product.id = recommendation.product_id
        JOIN categories AS category ON category.id = product.category_id
        JOIN sales_channels AS channel ON channel.id = recommendation.channel_id
        LEFT JOIN pricing_rules AS rule ON rule.id = recommendation.rule_id
        LEFT JOIN LATERAL (
            SELECT decision, decided_at
            FROM price_approvals
            WHERE recommendation_id = recommendation.id
            ORDER BY decided_at DESC, id DESC
            LIMIT 1
        ) AS approval ON TRUE
        LEFT JOIN LATERAL (
            SELECT status, previous_price, requested_price, updated_at
            FROM price_sync_logs
            WHERE recommendation_id = recommendation.id
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
        ) AS sync ON TRUE
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_bi_pricing_strategy_performance")
    op.execute("DROP VIEW IF EXISTS vw_bi_competitor_price_history")
    op.execute("DROP VIEW IF EXISTS vw_bi_sales_profitability")
    op.drop_constraint(
        op.f("ck_competitor_prices_match_status_valid"),
        "competitor_prices",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_competitor_prices_match_status_valid"),
        "competitor_prices",
        "match_status IN ('AUTO_MATCHED', 'NEEDS_REVIEW', 'REJECTED')",
    )
