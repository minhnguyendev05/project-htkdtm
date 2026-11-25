"""Explainable Pricing AI (WORK_SPEC §11).

Mọi câu giải thích đều lấy từ kết quả tính toán thật (điểm thành phần, rủi ro,
xung đột, ứng viên bị loại) — không hard-code lời giải thích vô căn cứ.
"""

from __future__ import annotations

from ..core.feature_engineering import margin_of, price_change_ratio
from ..schemas.input_schema import MarketInput, PricingContextInput, ProductInput
from ..schemas.output_schema import (
    CandidatePrice,
    ConflictReport,
    Explanation,
    RiskReport,
)

_COMPONENT_LABELS = {
    "profit": "lợi nhuận",
    "revenue": "doanh thu",
    "competitive": "mức cạnh tranh",
    "inventory": "phù hợp tồn kho",
}


def build_explanation(
    *,
    selected: CandidatePrice,
    candidates: list[CandidatePrice],
    product: ProductInput,
    market: MarketInput,
    context: PricingContextInput,
    strategy: str,
    risk: RiskReport,
    conflicts: ConflictReport,
) -> Explanation:
    """Tạo cấu trúc giải thích từ kết quả engine."""
    price = selected.price
    change = price_change_ratio(price, product.current_price)
    margin = margin_of(price, product.cost_price, context.channel_fee_rate)

    direction = "giữ nguyên" if abs(change) < 1e-9 else (
        "tăng" if change > 0 else "giảm"
    )
    summary = (
        f"Đề xuất giá {price:,.0f} VND ({direction} {abs(change):.1%} so với giá "
        f"hiện tại) theo chiến lược {strategy}, biên lợi nhuận dự kiến "
        f"{margin:.1%}."
    )

    positive: list[str] = []
    negative: list[str] = []

    breakdown = selected.breakdown
    if breakdown is not None:
        ranked = sorted(
            _COMPONENT_LABELS.items(),
            key=lambda item: getattr(breakdown, item[0]),
            reverse=True,
        )
        top_key, top_label = ranked[0]
        top_score = getattr(breakdown, top_key)
        if top_score >= 0.5:
            positive.append(
                f"Điểm {top_label} cao nhất trong các mục tiêu ({top_score:.2f})."
            )

    if margin >= context.min_margin:
        positive.append(
            f"Biên lợi nhuận {margin:.1%} vẫn cao hơn mức tối thiểu "
            f"{context.min_margin:.0%}."
        )

    if market.is_usable:
        positive.append("Có giá đối thủ đủ độ tin cậy để tham chiếu.")
    else:
        negative.append("Thiếu dữ liệu đối thủ đủ tin cậy để tham chiếu.")

    if risk.level in {"HIGH", "CRITICAL"}:
        negative.append(f"Mức rủi ro {risk.level} cần người duyệt kiểm tra.")
    if conflicts.has_conflict:
        negative.append(
            f"Phát hiện {len(conflicts.conflicts)} xung đột cần xem xét."
        )

    constraints_applied: list[str] = ["Giá sàn (floor price)"]
    constraints_applied.append(f"Biên tối thiểu {context.min_margin:.0%}")
    constraints_applied.append(
        f"Giới hạn biến động {context.max_price_change_percent:.0%}"
    )

    rejected = [
        {
            "price": round(candidate.price, 2),
            "reason": candidate.rejection_reason or "Không hợp lệ",
        }
        for candidate in candidates
        if not candidate.feasible
    ]

    confidence = max(0.05, min(1.0, 1.0 - risk.score / 100.0))
    confidence = round(confidence * (0.9 + 0.1 * market.confidence_score), 4)

    return Explanation(
        summary=summary,
        strategy=strategy,
        positive_factors=positive,
        negative_factors=negative,
        constraints_applied=constraints_applied,
        rejected_candidates=rejected,
        decision_confidence=confidence,
    )
