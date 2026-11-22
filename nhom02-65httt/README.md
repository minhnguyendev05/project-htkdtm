# Nhóm 02 - 65HTTT

Đề tài: **Hệ thống ERP Smart Pricing đa kênh tích hợp AI & BI**
(Multi-channel Intelligent ERP & Dynamic Pricing System)

Thư mục mã nguồn, tài liệu và báo cáo của nhóm `nhom02-65httt`.

## Cấu trúc

- `danhsachnhom.md`: thông tin thành viên và phân công.
- `docs/`: đề cương, tài liệu và báo cáo đồ án.
- `src/`: mã nguồn dự án (`backend/`, `frontend/`, `database/`).

## Công nghệ dự kiến

React + Vite + Tailwind, FastAPI, PostgreSQL, Redis, Celery, Scikit-learn/XGBoost, Apache Superset, Docker Compose.

Hướng dẫn cài đặt và khởi chạy sẽ được bổ sung cùng mã nguồn của nhóm.

## Khởi chạy nhanh hạ tầng & Backend

```bash
cp .env.example .env
docker compose up -d --build postgres redis backend celery_worker celery_beat
docker compose exec backend python -m app.scripts.seed_users
```

- Quy trình nhánh, PR và phân vùng thư mục: xem [CONTRIBUTING.md](CONTRIBUTING.md).
- Hướng dẫn chạy local, test và quy ước API: xem [src/backend/README.md](src/backend/README.md).
