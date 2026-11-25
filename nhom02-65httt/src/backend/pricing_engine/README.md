# AI Pricing Engine — Lê Minh Tú

Lõi định giá của **ERP Smart Pricing AI & BI V2**. Engine nhận dữ liệu sản phẩm,
tồn kho, chi phí, lịch sử bán hàng và dữ liệu thị trường; chọn chiến lược; sinh và
chấm điểm nhiều mức giá; kiểm tra ràng buộc, rủi ro, xung đột; rồi trả
recommendation **có giải thích**.

Engine chạy độc lập, **không** truy cập database, **không** gọi API sàn và
**không** tự thực thi giá (WORK_SPEC §17, §23.6). Quy trình duyệt/thực thi thuộc
backend workflow.

## Chạy thử

Yêu cầu: Python 3.10+ (chỉ dùng thư viện chuẩn, không cần cài thêm gì).
Chạy từ thư mục `nhom02-65httt/src/backend`:

```bash
python -m unittest discover -s pricing_engine/tests -t . -v   # 37 test
python pricing_engine/examples/example_run.py                  # demo 3 sản phẩm
```

Kết quả demo hiện tại (dữ liệu DEMO, không phải giá thực tế):

| Sản phẩm | Trạng thái | Chiến lược | Giá hiện tại → đề xuất |
|---|---|---|---|
| A — nhu cầu cao, tồn thấp | `READY` | `DEMAND_CAPTURE` | 100.000 → 110.000 (+10%) |
| B — tồn cao, bán chậm | `READY` | `INVENTORY_CLEARANCE` | 100.000 → 86.000 (−14%) |
| C — áp lực đối thủ | `READY` | `COMPETITIVE_PRICING` | 200.000 → 182.000 (−9%) |

## Dùng trong code

```python
from pricing_engine import PricingRequest, run_pricing

payload = {
    "product": {
        "product_id": "SKU001",
        "current_price": 100000,
        "cost_price": 65000,
        "inventory_quantity": 120,
        "inventory_days": 20,
        "sales_velocity": 1.0,
        "safety_stock": 50,
        "demand_growth": 0.0,
    },
    "market": {"competitor_price": 98000, "confidence_score": 0.9, "freshness_hours": 2},
    "sales": {"historical_sales": [10, 11, 12, 12, 13, 14, 13], "period_days": 7},
    "pricing_context": {
        "channel_fee_rate": 0.05,
        "min_margin": 0.15,
        "max_price_change_percent": 0.2,
        "price_step": 1000,
    },
    "simulation": False,
}

result = run_pricing(PricingRequest.from_dict(payload))
print(result.to_dict())
```

Kết quả gồm: `recommended_price`, `strategy` + lý do, `risk` (score/level/factors),
`conflicts`, `optimization.candidates` (kèm breakdown điểm), `forecast`,
`explanation` và `metadata` (`evaluation_type`: `DEMO` / `SIMULATED`).

## Cấu trúc

```
pricing_engine/
├── config.py                    # toàn bộ ngưỡng/trọng số (không hard-code)
├── schemas/
│   ├── input_schema.py          # contract đầu vào + validation
│   └── output_schema.py         # contract đầu ra (§16.2)
├── core/
│   ├── feature_engineering.py   # giá sàn, margin, biến động giá
│   ├── candidate_generator.py   # sinh giá ứng viên (§5.2)
│   └── pricing_pipeline.py      # điều phối toàn bộ luồng
├── strategies/
│   ├── base.py                  # 6 chiến lược
│   └── selector.py              # chọn chiến lược thích ứng (§4.4)
├── optimization/
│   ├── scoring.py               # hàm mục tiêu đa mục tiêu (§5.3)
│   └── constraints.py           # ràng buộc cứng (§5.4)
├── intelligence/
│   ├── risk_engine.py           # RiskScore có trọng số (§9)
│   └── conflict_detector.py     # phát hiện xung đột (§10)
├── explainability/
│   └── explanation_engine.py    # giải thích từ kết quả thật (§11)
├── forecasting/
│   └── demand_forecaster.py     # baseline trung bình trượt + MAE/RMSE (§6)
├── examples/example_run.py      # demo 3 sản phẩm (§22)
└── tests/                       # TC01–TC08, TC10, TC12 (§20)
```

## Hành vi từng chiến lược

| Chiến lược | Điều kiện chọn | Ràng buộc ứng viên |
|---|---|---|
| `INVENTORY_CLEARANCE` | tồn ≥ 90 ngày và tốc độ bán < 0.3 | chỉ giá thấp hơn hiện tại; độ sâu giảm giá tăng theo tuổi tồn, tối đa bằng `max_price_change_percent`; nếu giá sàn chặn thì đi sát giá sàn |
| `DEMAND_CAPTURE` | nhu cầu tăng ≥ 20% và tồn < mức an toàn | không cắt giá |
| `DEFENSIVE_PRICING` | giá đối thủ ≤ 90% giá hiện tại, dữ liệu đủ tin cậy | không vượt đối thủ quá 2% |
| `COMPETITIVE_PRICING` | độ tin cậy dữ liệu đối thủ ≥ 0.8 | trong dải ±5% quanh giá đối thủ |
| `PREMIUM_PRICING` | sản phẩm định vị premium | không cắt giá |
| `PROFIT_MAXIMIZATION` | mặc định | không giới hạn thêm |

Nếu dải giá của chiến lược không còn ứng viên nào, engine giữ danh sách đầy đủ
để vẫn trả được giá trong giới hạn cứng.

## Ràng buộc cứng (không được scoring vượt qua)

- Giá ≥ giá sàn: `cost_price / (1 - channel_fee_rate - min_margin)`.
- Biên lợi nhuận ≥ `min_margin`.
- `|Δgiá| ≤ max_price_change_percent`.

Vi phạm ⇒ ứng viên bị đánh dấu `feasible=false` kèm lý do và xuất hiện trong
`explanation.rejected_candidates`. Nếu không còn ứng viên hợp lệ, kết quả là
`NO_SAFE_PRICE` với `recommended_price = null` — engine không bịa giá.

## Chấm điểm

```
Score(p) = w_profit·Profit + w_revenue·Revenue + w_competitive·Competitive
         + w_inventory·Inventory − w_risk·Risk
```

Các thành phần chuẩn hóa min-max về 0..1 trên tập ứng viên. Trọng số theo chiến
lược nằm trong `config.STRATEGY_WEIGHTS` (đúng bảng §5.3).

## Giới hạn đã biết

1. **Chưa có Price Elasticity** (§7 — P1): nhu cầu dùng từ dự báo và không phản
   ứng theo giá. Vì vậy trong nội bộ một chiến lược, giá cao thường có lợi hơn;
   dải giá theo chiến lược ở trên bù lại phần nào. Khi thêm elasticity, truyền
   `PricingPipeline(default_elasticity=...)`.
2. **Trọng số là cấu hình khởi đầu**, chưa tối ưu trên dữ liệu thật (§5.3, §9.3).
3. **Dự báo mới là baseline trung bình trượt**; chưa so sánh với Random
   Forest/XGBoost (§6.3 — P2).
4. **Chưa nối FastAPI/DB/BI**: cần thống nhất contract với backend lead (§15, §17).
5. Mọi số liệu trong demo là **DEMO**, không dùng để tuyên bố hiệu quả thực tế.

## Bước tiếp theo

- P0 còn lại: nối endpoint `POST /api/ai/pricing/recommend` + `batch` khi backend
  lead chốt route; thêm `batch_pricing` chạy nhiều sản phẩm.
- P1: Adaptive Strategy Switching (cooldown/hysteresis), Digital Twin,
  Sensitivity Analysis, Experiment Lab, Closed-loop Evaluation.
