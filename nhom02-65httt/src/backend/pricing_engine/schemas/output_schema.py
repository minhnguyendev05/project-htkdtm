"""Output contract của Pricing Engine (WORK_SPEC §16.2).

Engine chỉ trả đề xuất, rủi ro, ràng buộc và giải thích — không tự thực thi
giá (WORK_SPEC §17, §23.6).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ObjectiveBreakdown:
    """Điểm từng thành phần mục tiêu, đã chuẩn hóa 0..1."""

    profit: float
    revenue: float
    competitive: float
    inventory: float
    risk: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class CandidatePrice:
    """Một mức giá ứng viên và kết quả chấm điểm."""

    price: float
    score: float = 0.0
    breakdown: ObjectiveBreakdown | None = None
    feasible: bool = True
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "price": round(self.price, 2),
            "score": round(self.score, 4),
            "feasible": self.feasible,
        }
        if self.breakdown is not None:
            data["breakdown"] = {
                key: round(value, 4) for key, value in self.breakdown.to_dict().items()
            }
        if self.rejection_reason:
            data["rejection_reason"] = self.rejection_reason
        return data


@dataclass
class StrategySelection:
    """Chiến lược được chọn và lý do (WORK_SPEC §4.6)."""

    strategy: str
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "strategy_reason": list(self.reasons),
            "confidence": round(self.confidence, 4),
        }


@dataclass
class RiskReport:
    """Kết quả Pricing Risk Engine (WORK_SPEC §9.5)."""

    score: float = 0.0
    level: str = "LOW"
    factors: list[dict[str, str]] = field(default_factory=list)
    requires_review: bool = False
    execution_allowed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "level": self.level,
            "factors": self.factors,
            "requires_review": self.requires_review,
            "execution_allowed": self.execution_allowed,
        }


@dataclass
class ConflictReport:
    """Kết quả Pricing Conflict Detection (WORK_SPEC §10.3)."""

    has_conflict: bool = False
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    resolution: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_conflict": self.has_conflict,
            "conflicts": self.conflicts,
            "resolution": self.resolution,
        }


@dataclass
class Explanation:
    """Giải thích quyết định định giá (WORK_SPEC §11.2)."""

    summary: str = ""
    strategy: str = ""
    positive_factors: list[str] = field(default_factory=list)
    negative_factors: list[str] = field(default_factory=list)
    constraints_applied: list[str] = field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)
    decision_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PricingResult:
    """Kết quả cuối cùng trả về cho backend/BI/frontend."""

    product_id: str
    current_price: float
    recommended_price: float | None
    price_change_percent: float
    strategy: str
    strategy_reason: list[str] = field(default_factory=list)
    strategy_confidence: float = 0.0
    recommendation_status: str = "READY"
    confidence: float = 0.0

    risk: RiskReport = field(default_factory=RiskReport)
    conflicts: ConflictReport = field(default_factory=ConflictReport)
    explanation: Explanation = field(default_factory=Explanation)

    floor_price: float | None = None
    min_margin_satisfied: bool = False
    max_price_change_satisfied: bool = True
    best_score: float = 0.0
    candidates: list[CandidatePrice] = field(default_factory=list)
    forecast: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "current_price": round(self.current_price, 2),
            "recommended_price": (
                None if self.recommended_price is None else round(self.recommended_price, 2)
            ),
            "price_change_percent": round(self.price_change_percent, 2),
            "strategy": self.strategy,
            "strategy_reason": list(self.strategy_reason),
            "strategy_confidence": round(self.strategy_confidence, 4),
            "recommendation_status": self.recommendation_status,
            "confidence": round(self.confidence, 4),
            "risk": self.risk.to_dict(),
            "conflicts": self.conflicts.to_dict(),
            "constraints": {
                "floor_price": (
                    None if self.floor_price is None else round(self.floor_price, 2)
                ),
                "min_margin_satisfied": self.min_margin_satisfied,
                "max_price_change_satisfied": self.max_price_change_satisfied,
            },
            "optimization": {
                "best_score": round(self.best_score, 4),
                "candidates_evaluated": len(self.candidates),
                "candidates": [candidate.to_dict() for candidate in self.candidates],
            },
            "forecast": self.forecast,
            "explanation": self.explanation.to_dict(),
            "metadata": dict(self.metadata),
        }
