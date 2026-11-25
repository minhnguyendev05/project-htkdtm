"""Đánh giá rủi ro và phát hiện xung đột."""

from .conflict_detector import detect_conflicts
from .risk_engine import assess_risk

__all__ = ["assess_risk", "detect_conflicts"]
