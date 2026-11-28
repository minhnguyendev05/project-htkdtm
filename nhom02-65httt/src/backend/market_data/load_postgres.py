"""Import a competitor snapshot or crawl active ERP products into the shared schema."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from app.db.session import SessionLocal
from app.models.erp import Product
from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters import TikiOpenApiAdapter
from .adapters.base import CompetitorSourceAdapter
from .normalize import load_dataset
from .persistence import persist_competitor_prices


def _default_dataset_path(module_file: Path) -> Path:
    module_directory = module_file.resolve().parent
    backend_root = next(
        (parent for parent in module_directory.parents if parent.name == "backend"),
        None,
    )
    project_root = backend_root.parents[1] if backend_root else module_directory.parent
    return project_root / "datasets" / "competitor-prices-vnd.csv"


DEFAULT_DATASET = _default_dataset_path(Path(__file__))

COUNT_FIELDS = (
    "rows_received",
    "rows_created",
    "rows_updated",
    "history_rows_created",
    "history_rows_updated",
)


def import_snapshot(db: Session, csv_path: str | Path) -> dict[str, int]:
    """Normalize and import all rows from a CSV into the canonical ORM tables."""
    records = load_dataset(csv_path)
    return persist_competitor_prices(
        db,
        records,
        adapter_name="dataset_snapshot",
    )


def crawl_active_products(
    db: Session,
    *,
    limit: int = 100,
    min_products: int = 60,
    min_delay: float = 2.0,
    max_delay: float = 4.0,
    adapter_factory: Callable[..., CompetitorSourceAdapter] = TikiOpenApiAdapter,
) -> dict[str, int]:
    """Crawl up to 100 active ERP products using their names as Tiki search terms."""
    if not 1 <= min_products <= limit <= 100:
        raise ValueError("Yêu cầu 1 <= min_products <= limit <= 100.")
    if min_delay < 0 or max_delay < min_delay:
        raise ValueError("Yêu cầu 0 <= min_delay <= max_delay.")

    products = list(
        db.scalars(
            select(Product)
            .where(Product.status == "ACTIVE")
            .order_by(Product.sku_code)
            .limit(limit)
        ).all()
    )
    if len(products) < min_products:
        raise ValueError(
            f"Chỉ tìm thấy {len(products)} sản phẩm ACTIVE trong bảng products; "
            f"cần ít nhất {min_products} SKU trước khi crawl."
        )

    adapter = adapter_factory(min_delay=min_delay, max_delay=max_delay)
    totals = {
        "products_requested": len(products),
        "products_with_results": 0,
        **dict.fromkeys(COUNT_FIELDS, 0),
    }
    try:
        for product in products:
            records = adapter.fetch(keyword=product.name, limit=20)
            if records.empty:
                db.commit()
                continue

            totals["products_with_results"] += 1
            result = persist_competitor_prices(
                db,
                records,
                adapter_name="tiki",
                sku_code=product.sku_code,
            )
            for field in COUNT_FIELDS:
                totals[field] += result[field]
            db.commit()
    finally:
        adapter.session.close()

    return totals


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import normalized competitor CSV rows or crawl 60-100 active ERP "
            "products into competitor_prices and competitor_price_history."
        )
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        help="Normalized or raw competitor snapshot CSV to import.",
    )
    parser.add_argument(
        "--crawl-active-products",
        action="store_true",
        help="Search Tiki using active ERP product names instead of importing CSV.",
    )
    parser.add_argument("--limit", type=int, default=100, help="Maximum active SKUs to crawl.")
    parser.add_argument(
        "--min-products",
        type=int,
        default=60,
        help="Fail unless at least this many active products exist (default: 60).",
    )
    parser.add_argument("--min-delay", type=float, default=2.0)
    parser.add_argument("--max-delay", type=float, default=4.0)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.crawl_active_products:
        if args.csv_path is not None:
            parser.error("Không truyền csv_path cùng --crawl-active-products.")
        if not 1 <= args.min_products <= args.limit <= 100:
            parser.error("Yêu cầu 1 <= --min-products <= --limit <= 100.")
        if args.min_delay < 0 or args.max_delay < args.min_delay:
            parser.error("Yêu cầu 0 <= --min-delay <= --max-delay.")

        with SessionLocal() as db:
            result = crawl_active_products(
                db,
                limit=args.limit,
                min_products=args.min_products,
                min_delay=args.min_delay,
                max_delay=args.max_delay,
            )
    else:
        if args.csv_path is None:
            parser.error("Cần csv_path hoặc --crawl-active-products.")
        if not args.csv_path.is_file():
            parser.error(f"Không tìm thấy CSV: {args.csv_path}")
        with SessionLocal() as db:
            result = import_snapshot(db, args.csv_path)
            db.commit()

    print("Kết quả nạp crawler:")
    for key, value in result.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
