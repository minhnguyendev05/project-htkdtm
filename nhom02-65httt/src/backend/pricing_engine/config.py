"""Cấu hình trung tâm của Pricing Engine.

Toàn bộ ngưỡng, trọng số và giới hạn nằm ở đây để không hard-code rải rác
trong thuật toán (WORK_SPEC §23.2, §23.3). Mọi con số dưới đây là cấu hình
khởi đầu để kiểm thử, KHÔNG phải trọng số tối ưu đã được chứng minh
(WORK_SPEC §5.3, §9.3).
"""

from __future__ import annotations

ENGINE_VERSION = "1.0.0"

# --- Trọng số mục tiêu theo chiến lược (WORK_SPEC §5.3) -------------------
# profit + revenue + competitive + inventory + risk = 1.0
STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "PROFIT_MAXIMIZATION": {
        "profit": 0.50,
        "revenue": 0.20,
        "competitive": 0.10,
        "inventory": 0.10,
        "risk": 0.10,
    },
    "COMPETITIVE_PRICING": {
        "profit": 0.25,
        "revenue": 0.15,
        "competitive": 0.40,
        "inventory": 0.10,
        "risk": 0.10,
    },
    "INVENTORY_CLEARANCE": {
        "profit": 0.20,
        "revenue": 0.10,
        "competitive": 0.10,
        "inventory": 0.50,
        "risk": 0.10,
    },
    "DEMAND_CAPTURE": {
        "profit": 0.35,
        "revenue": 0.30,
        "competitive": 0.15,
        "inventory": 0.10,
        "risk": 0.10,
    },
    "PREMIUM_PRICING": {
        "profit": 0.40,
        "revenue": 0.25,
        "competitive": 0.15,
        "inventory": 0.10,
        "risk": 0.10,
    },
    "DEFENSIVE_PRICING": {
        "profit": 0.30,
        "revenue": 0.20,
        "competitive": 0.20,
        "inventory": 0.20,
        "risk": 0.10,
    },
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "profit": 0.30,
    "revenue": 0.20,
    "competitive": 0.20,
    "inventory": 0.20,
    "risk": 0.10,
}

# --- Trọng số rủi ro (WORK_SPEC §9.3), tổng = 1.0 -------------------------
RISK_WEIGHTS: dict[str, float] = {
    "MARGIN_BELOW_MIN": 0.30,
    "LOW_DATA_CONFIDENCE": 0.20,
    "HIGH_PRICE_CHANGE": 0.20,
    "FORECAST_UNCERTAINTY": 0.15,
    "MARKET_ANOMALY": 0.10,
    "INVENTORY_HIGH": 0.05,
}

# Điểm quy đổi mức độ nghiêm trọng của một risk factor (0-100).
RISK_SEVERITY_SCORE: dict[str, float] = {
    "LOW": 30.0,
    "MEDIUM": 60.0,
    "HIGH": 85.0,
    "CRITICAL": 100.0,
}

# Ngưỡng phân loại rủi ro (WORK_SPEC §9.4) — duyệt từ cao xuống thấp.
RISK_LEVELS: tuple[tuple[float, str], ...] = (
    (80.0, "CRITICAL"),
    (60.0, "HIGH"),
    (30.0, "MEDIUM"),
    (0.0, "LOW"),
)

# --- Ngưỡng chọn chiến lược (WORK_SPEC §4.4) -----------------------------
CLEARANCE_INVENTORY_DAYS = 90.0
CLEARANCE_MAX_SALES_VELOCITY = 0.3
DEMAND_CAPTURE_MIN_GROWTH = 0.2
COMPETITOR_RELIABLE_CONFIDENCE = 0.8

# Cảnh báo khi biến động giá vượt ngưỡng này (dù còn trong giới hạn cứng).
HIGH_PRICE_CHANGE_WARNING = 0.15

# --- Sinh giá ứng viên (WORK_SPEC §5.2) ----------------------------------
CANDIDATE_PERCENT_STEPS: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10)
DEFAULT_PRICE_STEP = 1000.0

# Hệ số neo giá theo chiến lược (dùng để tạo 1 ứng viên "đề xuất chiến lược").
STRATEGY_ANCHOR_MULTIPLIER: dict[str, float] = {
    "PROFIT_MAXIMIZATION": 1.03,
    "COMPETITIVE_PRICING": 0.98,
    "INVENTORY_CLEARANCE": 0.88,
    "DEMAND_CAPTURE": 1.05,
    "PREMIUM_PRICING": 1.02,
    "DEFENSIVE_PRICING": 0.95,
}

# --- Độ sâu giảm giá khi xả hàng (WORK_SPEC §4.2) ----------------------
# Tồn càng cao/bán càng chậm thì mức giảm mục tiêu càng sâu, tối đa bằng
# giới hạn biến động giá của ngữ cảnh.
CLEARANCE_MIN_MARKDOWN = 0.05
CLEARANCE_EXTRA_MAX_MARKDOWN = 0.15
CLEARANCE_SEVERITY_SPAN_DAYS = 300.0

# --- Dải giá theo chiến lược cạnh tranh (WORK_SPEC §4.2) ----------------
# Định giá cạnh tranh giữ giá quanh giá đối thủ; phòng thủ không vượt đối thủ.
COMPETITIVE_PRICE_BAND = 0.05
DEFENSIVE_MAX_ABOVE_COMPETITOR = 0.02

# --- Dự báo nhu cầu (WORK_SPEC §6) --------------------------------------
MIN_FORECAST_OBSERVATIONS = 3
DEFAULT_FORECAST_HORIZON = 7

# --- Mức tin cậy tối thiểu để dùng dữ liệu đối thủ ----------------------
MIN_COMPETITOR_CONFIDENCE = 0.6


def weights_for(strategy: str) -> dict[str, float]:
    """Trả về trọng số mục tiêu của một chiến lược (fallback mặc định)."""
    return STRATEGY_WEIGHTS.get(strategy, DEFAULT_WEIGHTS)


def risk_level_for(score: float) -> str:
    """Phân loại mức rủi ro theo điểm 0-100 (WORK_SPEC §9.4)."""
    for threshold, level in RISK_LEVELS:
        if score >= threshold:
            return level
    return "LOW"
