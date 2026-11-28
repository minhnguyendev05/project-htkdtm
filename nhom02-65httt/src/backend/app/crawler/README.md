# Bộ Công Cụ Crawler Đa Nền Tảng (`app/crawler`)

Thư mục này chứa bộ mã nguồn thu thập dữ liệu thị trường thật từ **Shopee, Lazada, TikTok Shop, Tiki và các chuỗi bán lẻ**, được đưa vào dự án từ bộ kiểm chứng PoC để phục vụ phát triển tiếp Module 2 (Crawler Pipeline & Entity Resolution).

## 1. Cài đặt thư viện bổ sung

- Các thư viện cho **Mode A & Mode B** (`httpx`, `beautifulsoup4`) đã có sẵn trong `requirements.txt`.
- Để dùng **Entity Resolution (`rapidfuzz`)** hoặc chạy **Mode C (`playwright`)** trên máy cục bộ, cài thêm:

```powershell
cd nhom02-65httt\src\backend
.venv\Scripts\pip install -r requirements-crawler.txt
```

## 2. Kiến trúc 3 Chế độ (3-Mode Hybrid Crawling)

1. **Mode A & Mode B (`multi_platform_crawler.py`) — Chạy nền tự động (không cần trình duyệt):**
   - **Lazada Direct PDP:** Crawl `lazada.vn/products/*.html`, bóc tách `pdpTrackingData`, `JSON-LD` và `__moduleData__`.
   - **Shopee Keyword Discovery + Price History (32–56+ điểm quá khứ):** Truy vấn `lichsugia.com/api/similar-products.php`, `lichsugia.net/backend-api/api/public/products/platform/{shop_id}/{item_id}` và `lichsugia.com/api/price-history.php`.
   - **Tiki Open API v2:** Truy vấn `https://tiki.vn/api/v2/products`.
   - **GiaReVN & Retail Benchmarks:** Bóc tách biểu đồ giá `giarevn.com`, giá chính hãng `cellphones.com.vn` và `websosanh.vn`.

   Chạy thử từ `nhom02-65httt/src/backend/`:
   ```powershell
   python -m app.crawler.multi_platform_crawler
   ```
   Kết quả mẫu được lưu tại `app/crawler/samples/verified_crawl_output.json`.

2. **Mode C (`chrome_cdp_collector.py` + `start_chrome_cdp.bat`) — Chrome Headful CDP (có cửa sổ thật):**
   - Khởi chạy Chrome ở cổng debug `9222` với profile riêng (`%LOCALAPPDATA%\ERP_SmartPricing_ChromeProfile`), không ảnh hưởng trình duyệt cá nhân.
   - Chạy từ `nhom02-65httt/src/backend/`:
     ```powershell
     python -m app.crawler.chrome_cdp_collector --open-login
     python -m app.crawler.chrome_cdp_collector --diagnose
     python -m app.crawler.chrome_cdp_collector --auto-crawl --source all --max-items 3
     python -m app.crawler.chrome_cdp_collector --listen 60
     ```
   - Lưu ý: Output tạm `cdp_captured_payloads.json` đã được đưa vào `.gitignore`, không commit lên Git.

## 3. Adapter, Celery và lưu trữ dữ liệu

Bộ adapter chuẩn hóa đang nằm trong `market_data/adapters/`; task
`market_data.tasks.crawl_and_store_task` được đăng ký trên Celery chung
`app.worker.celery_app`. API `POST /api/v1/crawler/run` yêu cầu quyền
`COMPETITOR_WRITE`; API `GET /api/v1/competitor-prices` và
`GET /api/v1/competitor-prices/{id}/history` yêu cầu `COMPETITOR_READ`. Task lưu
listing và lịch sử hằng ngày vào hai bảng ORM chuẩn `competitor_prices` và
`competitor_price_history`, không dùng schema crawler riêng.

API `POST /api/v1/crawler/ingest-cdp` nhận `structuredRecords` do Mode C
collector trả về. Để gửi trực tiếp sau khi crawl, đặt
`CRAWLER_CDP_INGEST_URL`, `CRAWLER_CDP_INGEST_TOKEN` (JWT có quyền
`COMPETITOR_WRITE`) rồi chạy collector với `--url` hoặc `--listen`. API không
truy cập các URL trong payload; nó chỉ nhận dữ liệu đã thu thập, chuẩn hóa và
ghi vào các bảng ORM chuẩn. Payload được giới hạn tối đa 100 record mỗi request.

Các bản ghi `NEEDS_REVIEW` có thể được lọc ở `GET /api/v1/competitor-prices`
với `matchStatus=NEEDS_REVIEW`, rồi xử lý bằng
`POST /api/v1/competitor-prices/{id}/review`. Duyệt sẽ gắn SKU ACTIVE và đặt
trạng thái `MANUALLY_MATCHED`; từ chối sẽ đặt `REJECTED`. Cả hai quyết định đều
cần lý do và được ghi vào `audit_logs`.

Celery Beat chạy bulk crawl Tiki mỗi ngày lúc 02:00 theo múi giờ
`Asia/Ho_Chi_Minh`; lệnh đòi hỏi tối thiểu 60 sản phẩm ERP ACTIVE, crawl tối đa
100 sản phẩm và giữ khoảng nghỉ 2–4 giây giữa các lượt tìm kiếm. Cờ
`fake_sale_warning` được bật khi giá niêm yết thấp hơn giá gốc hợp lệ ít nhất
50%; đây là ngưỡng rà soát, không phải kết luận một listing gian lận.

Các adapter hiện có: `tiki`, `lazada`, `retail_html`, `giarevn`,
`price_history` và `dataset_snapshot`. Ví dụ gọi API:

```http
POST /api/v1/crawler/run
Authorization: Bearer <access-token>
Content-Type: application/json

{"adapterName":"tiki","keyword":"AirPods","limit":5,"skuCode":"ERP-AIRPODS-4"}
```

Schema được tạo/cập nhật bằng Alembic chuẩn của backend. URL gửi tới các adapter
trang bán lẻ phải dùng HTTPS và đúng domain được cho phép; chuyển hướng bị từ
chối.
