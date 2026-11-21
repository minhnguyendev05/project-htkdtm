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

## Chạy frontend ở chế độ Empty State

Yêu cầu: Node.js 20 trở lên.

```powershell
cd src/frontend
npm ci
npm run dev
```

Frontend mặc định chạy ở `http://localhost:5173` với `VITE_EMPTY_DEMO=true`; clone mới không cần database, API hay file dữ liệu riêng.

Tài khoản demo:

- Email: `admin@erp.demo`
- Mật khẩu: `demo1234`

Các tài khoản demo khác có thể xem trong màn hình đăng nhập.
