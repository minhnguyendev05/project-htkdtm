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
    with op.batch_alter_table("competitor_prices") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_competitor_prices_match_status_valid"),
            type_="check",
        )
        batch_op.create_check_constraint(
            op.f("ck_competitor_prices_match_status_valid"),
            "match_status IN ('AUTO_MATCHED', 'MANUALLY_MATCHED', 'NEEDS_REVIEW', 'REJECTED')",
        )
    op.execute("DROP VIEW IF EXISTS vw_bi_sales_profitability")
    op.execute(
        """
        CREATE VIEW vw_bi_sales_profitability AS
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
            (
                SELECT rec.floor_price
                FROM price_recommendations AS rec
                WHERE rec.product_id = sales.product_id
                  AND rec.channel_id = sales.channel_id
                  AND DATE(rec.created_at) <= sales.order_date
                ORDER BY rec.created_at DESC, rec.id DESC
                LIMIT 1
            ) AS pmin
        FROM sales_records AS sales
        JOIN products AS product ON product.id = sales.product_id
        JOIN categories AS category ON category.id = product.category_id
        JOIN sales_channels AS channel ON channel.id = sales.channel_id
        """
    )
    op.execute("DROP VIEW IF EXISTS vw_bi_competitor_price_history")
    op.execute(
        """
        CREATE VIEW vw_bi_competitor_price_history AS
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
    op.execute("DROP VIEW IF EXISTS vw_bi_pricing_strategy_performance")
    op.execute(
        """
        CREATE VIEW vw_bi_pricing_strategy_performance AS
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
            (
                SELECT approval.decision
                FROM price_approvals AS approval
                WHERE approval.recommendation_id = recommendation.id
                ORDER BY approval.decided_at DESC, approval.id DESC
                LIMIT 1
            ) AS latest_approval_decision,
            (
                SELECT approval.decided_at
                FROM price_approvals AS approval
                WHERE approval.recommendation_id = recommendation.id
                ORDER BY approval.decided_at DESC, approval.id DESC
                LIMIT 1
            ) AS latest_approval_at,
            (
                SELECT sync.status
                FROM price_sync_logs AS sync
                WHERE sync.recommendation_id = recommendation.id
                ORDER BY sync.updated_at DESC, sync.id DESC
                LIMIT 1
            ) AS latest_sync_status,
            (
                SELECT sync.previous_price
                FROM price_sync_logs AS sync
                WHERE sync.recommendation_id = recommendation.id
                ORDER BY sync.updated_at DESC, sync.id DESC
                LIMIT 1
            ) AS synced_previous_price,
            (
                SELECT sync.requested_price
                FROM price_sync_logs AS sync
                WHERE sync.recommendation_id = recommendation.id
                ORDER BY sync.updated_at DESC, sync.id DESC
                LIMIT 1
            ) AS synced_requested_price,
            (
                SELECT sync.updated_at
                FROM price_sync_logs AS sync
                WHERE sync.recommendation_id = recommendation.id
                ORDER BY sync.updated_at DESC, sync.id DESC
                LIMIT 1
            ) AS latest_sync_at
        FROM price_recommendations AS recommendation
        JOIN products AS product ON product.id = recommendation.product_id
        JOIN categories AS category ON category.id = product.category_id
        JOIN sales_channels AS channel ON channel.id = recommendation.channel_id
        LEFT JOIN pricing_rules AS rule ON rule.id = recommendation.rule_id
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_bi_pricing_strategy_performance")
    op.execute("DROP VIEW IF EXISTS vw_bi_competitor_price_history")
    op.execute("DROP VIEW IF EXISTS vw_bi_sales_profitability")
    op.execute(
        """
        UPDATE competitor_prices
        SET match_status = 'AUTO_MATCHED'
        WHERE match_status = 'MANUALLY_MATCHED'
        """
    )
    with op.batch_alter_table("competitor_prices") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_competitor_prices_match_status_valid"),
            type_="check",
        )
        batch_op.create_check_constraint(
            op.f("ck_competitor_prices_match_status_valid"),
            "match_status IN ('AUTO_MATCHED', 'NEEDS_REVIEW', 'REJECTED')",
        )
