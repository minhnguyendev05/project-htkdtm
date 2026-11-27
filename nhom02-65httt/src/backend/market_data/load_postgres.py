from __future__ import annotations

import sys

from app.db.session import SessionLocal

from .adapters import DatasetSnapshotAdapter
from .persistence import persist_competitor_prices


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m market_data.load_postgres <csv-path>")

    records = DatasetSnapshotAdapter(sys.argv[1]).fetch()
    with SessionLocal() as db:
        result = persist_competitor_prices(
            db,
            records,
            adapter_name="dataset_snapshot",
        )
        db.commit()
    print(
        "Đã nạp {rows_received} bản ghi; tạo {rows_created}, "
        "cập nhật {rows_updated}; lịch sử tạo {history_rows_created}, "
        "cập nhật {history_rows_updated}.".format(**result)
    )


if __name__ == "__main__":
    main()
