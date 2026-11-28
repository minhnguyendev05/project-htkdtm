"""So sanh Linear Regression va XGBoost, luu ket qua vao bang model_runs."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "model_runs.db"


def init_db() -> None:
    """Khoi tao bang model_runs trong SQLite cuc bo."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS model_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            split TEXT NOT NULL,
            mae REAL NOT NULL,
            rmse REAL NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.commit()
    conn.close()


def evaluate(model, X_train, y_train, X_test, y_test) -> dict[str, float]:
    """Huan luyen va tinh MAE, RMSE tren tap kiem thu."""
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    return {
        "mae": float(mean_absolute_error(y_test, pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred))),
    }


def run_comparison(X, y, split_idx: int) -> dict[str, dict[str, float]]:
    """Chay so sanh LinearRegression va XGBoost theo time-based split."""
    init_db()
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    results: dict[str, dict[str, float]] = {}
    models = {
        "LinearRegression": LinearRegression(),
        "XGBoost": XGBRegressor(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            objective="reg:squarederror",
        ),
    }
    conn = sqlite3.connect(DB_PATH)
    for name, model in models.items():
        metrics = evaluate(model, X_train, y_train, X_test, y_test)
        results[name] = metrics
        conn.execute(
            "INSERT INTO model_runs (model_name, split, mae, rmse, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                name,
                "time_based",
                metrics["mae"],
                metrics["rmse"],
                datetime.now(UTC).isoformat(),
            ),
        )
    conn.commit()
    conn.close()
    return results


if __name__ == "__main__":
    X_demo = np.array([[i] for i in range(1, 21)], dtype=float)
    y_demo = np.array([2 * i + 1 for i in range(1, 21)], dtype=float)
    print(run_comparison(X_demo, y_demo, 15))
