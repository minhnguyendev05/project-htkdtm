"""Model training, time-based evaluation (MAE/RMSE), and ModelRun ORM persistence."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sqlalchemy import select
from sqlalchemy.orm import Session
from xgboost import XGBRegressor

from app.core.errors import AppError
from app.ml.preprocessing import FEATURE_COLUMNS, build_sales_features
from app.models.market import SalesRecord
from app.models.pricing import ModelRun
from app.services.audit import record_audit_log

_METRIC_QUANT = Decimal("0.0001")


def _metric_decimal(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_METRIC_QUANT, rounding=ROUND_HALF_UP)


def evaluate_model(
    model: object,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> dict[str, float]:
    """Fit a regression model and compute MAE and RMSE on the hold-out test split."""
    model.fit(X_train, y_train)  # type: ignore[attr-defined]
    pred = model.predict(X_test)  # type: ignore[attr-defined]
    return {
        "mae": float(mean_absolute_error(y_test, pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred))),
    }


def run_model_comparison(
    db: Session,
    X: np.ndarray,
    y: np.ndarray,
    *,
    split_idx: int | None = None,
    feature_columns: list[str] | None = None,
    model_version: str = "v1.0.0",
    actor: str | None = None,
) -> list[ModelRun]:
    """Compare LinearRegression vs XGBoost with a chronological split and persist ModelRun rows."""
    n_samples = len(X)
    if n_samples < 5:
        raise AppError(
            code="VALIDATION_ERROR",
            message="Cần tối thiểu 5 mẫu dữ liệu để huấn luyện và đánh giá mô hình.",
            status_code=422,
        )

    if split_idx is None:
        split_idx = max(3, min(n_samples - 2, int(n_samples * 0.8)))
    if not 1 <= split_idx < n_samples:
        raise AppError(
            code="VALIDATION_ERROR",
            message="Chỉ số chia tập train/test (time-based split) không hợp lệ.",
            status_code=422,
        )

    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    cols = list(feature_columns or FEATURE_COLUMNS[: X.shape[1]])

    candidates = [
        (
            "DemandLinearBaseline",
            "LINEAR_REGRESSION",
            LinearRegression(),
        ),
        (
            "DemandXGBoost",
            "XGBOOST",
            XGBRegressor(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                objective="reg:squarederror",
                random_state=42,
            ),
        ),
    ]

    persisted: list[ModelRun] = []
    for model_name, algo_type, estimator in candidates:
        metrics = evaluate_model(estimator, X_train, y_train, X_test, y_test)
        run_row = ModelRun(
            model_name=model_name,
            model_version=model_version,
            algorithm_type=algo_type,
            feature_columns_json=cols,
            train_samples=len(X_train),
            test_samples=len(X_test),
            mae=_metric_decimal(metrics["mae"]),
            rmse=_metric_decimal(metrics["rmse"]),
            artifact_path=None,
        )
        db.add(run_row)
        persisted.append(run_row)

    if actor:
        summary = ", ".join(
            f"{row.model_name}(MAE={row.mae}, RMSE={row.rmse})" for row in persisted
        )
        record_audit_log(
            db,
            actor=actor,
            action="TRAIN_MODEL_COMPARISON",
            resource_type="model_run",
            after_summary=summary,
        )

    db.commit()
    for row in persisted:
        db.refresh(row)
    return persisted


def train_and_log_from_sales_records(
    db: Session,
    *,
    product_id: UUID | None = None,
    channel_id: UUID | None = None,
    split_ratio: float = 0.8,
    actor: str | None = None,
) -> list[ModelRun]:
    """Query SalesRecord history, build chronological features, and log ModelRun comparison."""
    stmt = select(SalesRecord).order_by(SalesRecord.order_date.asc())
    if product_id is not None:
        stmt = stmt.where(SalesRecord.product_id == product_id)
    if channel_id is not None:
        stmt = stmt.where(SalesRecord.channel_id == channel_id)

    records = list(db.scalars(stmt).all())
    if len(records) < 5:
        raise AppError(
            code="VALIDATION_ERROR",
            message=(
                f"Chỉ có {len(records)} bản ghi bán hàng; cần tối thiểu 5 bản ghi "
                "để chạy đánh giá Time-based Split."
            ),
            status_code=422,
        )

    X, y = build_sales_features(records)
    split_idx = max(3, min(len(records) - 2, int(len(records) * split_ratio)))
    return run_model_comparison(
        db,
        X,
        y,
        split_idx=split_idx,
        feature_columns=FEATURE_COLUMNS,
        actor=actor,
    )
