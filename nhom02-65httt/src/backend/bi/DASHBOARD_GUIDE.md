# Apache Superset – dashboards thành viên 3

## Nguồn dữ liệu

Chạy migration chuẩn trước khi kết nối Superset:

```powershell
cd nhom02-65httt\src\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Migration `0003_market_data_bi_views.py` tạo ba view đọc trên schema chuẩn, không
thêm bảng nghiệp vụ mới:

| Dataset Superset | Grain | Nội dung |
|---|---|---|
| `vw_bi_sales_profitability` | Một dòng bán hàng/ngày theo SKU và kênh | Doanh thu, giá vốn, gross profit, net profit, margin và Pmin gần nhất tại thời điểm bán |
| `vw_bi_competitor_price_history` | Một listing đối thủ theo ngày ghi nhận | Giá lịch sử, giá hiện tại, marketplace, SKU, match state và cờ cảnh báo |
| `vw_bi_pricing_strategy_performance` | Một đề xuất giá | Chiến lược, giá đề xuất, margin dự kiến, quyết định duyệt gần nhất và trạng thái đồng bộ gần nhất |

Kết nối Superset tới PostgreSQL của ứng dụng và tạo dataset từ các view trên.
Các tỷ lệ và giá trị hiển thị phải dùng đúng grain của dataset; không join trực
tiếp fact sales với price history vì sẽ nhân bản doanh thu.

## Dashboard 1 – Profitability

Dataset: `vw_bi_sales_profitability`.

1. Big Number: `SUM(gross_revenue)`, `SUM(gross_profit)`, `SUM(net_profit)`.
2. Big Number: net margin tính lại bằng
   `100 * SUM(net_profit) / NULLIF(SUM(gross_revenue), 0)`.
3. Time-series theo `order_date`: doanh thu, gross profit và net profit.
4. Bar: gross profit/net profit theo `category_name` hoặc `channel_name`.
5. Table SKU sát sàn giá: `sku_code`, `product_name`, `unit_price`, `pmin`,
   `net_margin_pct`; lọc `pmin IS NOT NULL AND unit_price <= pmin * 1.05`.

`pmin` là floor price từ đề xuất mới nhất tạo trước ngày bán. Đây là tham chiếu
cho rà soát, không phải lịch sử Pmin chính thức nếu nhóm thay đổi quy tắc giá.

## Dashboard 2 – Competitor & Price History

Dataset: `vw_bi_competitor_price_history`.

1. Big Number: số listing đối thủ, số marketplace, thời điểm crawl mới nhất.
2. Bar: số listing và giá trung bình theo `marketplace_code`.
3. Time-series theo `recorded_date`: giá thấp nhất/trung bình/cao nhất, lọc
   theo SKU và marketplace.
4. Table: SKU, `product_name`, marketplace, `raw_title`, `price`,
   `latest_listed_price`, `sold_count`, `rating`, `match_status`,
   `fake_sale_warning`, `observed_at`.
5. Price index có thể tính là
   `100 * erp_current_price / NULLIF(price, 0)` sau khi lọc chỉ match
   `AUTO_MATCHED` hoặc `MANUALLY_MATCHED`. Đây là giá ERP hiện tại so với mức
   đối thủ ở ngày được chọn, không phải so sánh hai mức giá lịch sử đồng thời.

`fake_sale_warning` hiện là cờ rà soát cho mức giảm từ giá gốc hợp lệ từ 50%;
không xem cờ này là kết luận listing gian lận. Giá gốc/discount chưa được lưu
thành chuỗi lịch sử riêng nên không tính fake-sale rate quá khứ từ cờ hiện tại.

## Dashboard 3 – Pricing Strategy Performance

Dataset: `vw_bi_pricing_strategy_performance`.

1. Bar: số đề xuất theo `strategy` và `recommendation_status`.
2. Funnel: `recommendation_status` → `latest_approval_decision` →
   `latest_sync_status`.
3. Big Number: approval rate = đề xuất có quyết định APPROVED / đề xuất có
   quyết định; sync success rate = đồng bộ SUCCEEDED / lượt đồng bộ có trạng thái.
4. Table: strategy, SKU, current/recommended/floor price, expected margin,
   predicted demand, approval gần nhất và sync gần nhất.

Schema hiện không liên kết một dòng sales với recommendation/strategy đã áp
dụng. Vì vậy không suy diễn doanh thu tăng/giảm hoặc “before/after uplift” theo
chiến lược từ các view này. Muốn đo tác động cần event/attribution model do nhóm
Database và Pricing thống nhất.

## Bộ lọc chung và giới hạn

Dùng date range, category, channel, marketplace, SKU, strategy và status theo
dataset tương ứng. Không gắn nhãn “90 ngày” nếu dữ liệu chưa đủ 90 ngày. View
đối thủ giữ listing chưa được match; view pricing giữ đề xuất chưa được duyệt
hoặc đồng bộ. Dashboard nên hiển thị rõ trạng thái dữ liệu thay vì loại bỏ âm
thầm.
