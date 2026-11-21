# Báo Cáo Thống Kê Tình Hình Commit Của Các Nhóm Fork

- **Kho lưu trữ gốc:** `oanhcuongdo/project-htkdtm`
- **Nhánh gốc đối chiếu:** `main` (5 commit, mới nhất `d6eec6b` lúc `2026-11-11 18:52:09 UTC+7`)
- **Thời điểm thu thập dữ liệu:** `2026-11-21 09:10:31 (UTC+7)`
- **Phương pháp thống kê:** Truy vấn GitHub REST API đối với toàn bộ 14 kho fork, 10 Pull Request trên kho gốc và đối chiếu danh sách thành viên trong tệp `danhsachnhom.md` của từng nhóm. Chỉ tính các commit mới so với `upstream/main` (`ahead commits`).

---

## 1. Tổng Quan Chỉ Số Toàn Lớp

| Chỉ tiêu | Giá trị | Tỷ lệ / Ghi chú |
| :--- | :---: | :--- |
| Tổng số kho fork đang hoạt động | 14 | Tương ứng từ Nhóm 01 đến Nhóm 14; không có sub-fork |
| Tổng số commit mới trên toàn bộ các fork | 67 | 66 commit do tài khoản sinh viên thực hiện; 1 commit mang định danh công cụ cục bộ (`Codex`) tại Nhóm 07 |
| Số nhóm đã có ít nhất 1 commit | 14 / 14 | 100% |
| Số nhóm ít commit (1 đến 2 commit) | 7 / 14 | 50,0% (gồm 1 nhóm có 1 commit; 6 nhóm có 2 commit) |
| Tổng số thành viên được kê khai trong `danhsachnhom.md` | 65 | Tổng hợp từ bảng thành viên của cả 14 nhóm |
| Số cá nhân đã thực hiện commit | 14 / 65 | 21,5% (mỗi fork mới chỉ có duy nhất 1 cá nhân commit) |
| Số cá nhân chưa có commit | 51 / 65 | 78,5% (tất cả thành viên còn lại ngoài chủ kho fork) |
| Tổng số Pull Request gửi về kho gốc | 10 | 6 PR `open` (Nhóm 02, 08, 09, 11, 13, 14), 4 PR `closed` chưa merge (PR #1, #3, #6, #10) |

---

## 2. Thống Kê Tình Hình Commit Theo Từng Nhóm Fork

*(Múi giờ hiển thị là `UTC+7`. Số tệp ngoài base là số tệp thuộc thư mục nhóm hoặc do nhóm thêm mới so với kho gốc.)*

| Nhóm | Tài khoản Fork | Nhánh làm việc chính | Số commit mới | Cá nhân đã commit (số commit) | Thành viên chưa commit | Push gần nhất (UTC+7) | Số tệp ngoài base | PR trên kho gốc |
| :--- | :--- | :--- | :---: | :--- | :---: | :--- | :---: | :--- |
| Nhóm 01 | `aanhthaoo` | `nhom01-65httt` | 2 | Trương Thảo Anh (2) | 4 / 5 | `2026-11-18 16:50:20` | 6 | Chưa có |
| Nhóm 02 | `minhnguyendev05` | `nhom02-65httt` | 2 | Nguyễn Anh Minh (2) | 4 / 5 | `2026-11-18 17:12:37` | 6 | #4 (`open`) |
| Nhóm 03 | `thanhtung111205` | `nhom03-65httt` | 3 | Giang Thanh Tùng (3) | 4 / 5 | `2026-11-12 14:03:44` | 3 | Chưa có |
| Nhóm 04 | `Haithinh32` | `nhom04-65httt` | 5 | Ngô Hải Thịnh (5) | 2 / 3 | `2026-11-21 07:58:21` | 6 | Chưa có |
| Nhóm 05 | `DiemQuynh05` | `nhom05-65httt` | 1 | Nguyễn Thị Diễm Quỳnh (1) | 3 / 4 | `2026-11-18 09:25:23` | 3 | Chưa có |
| Nhóm 06 | `maingocanh2003` | `nhom06-65httt` | 2 | Trần Mai Ngọc Anh (2) | 3 / 4 | `2026-11-18 20:29:02` | 2 | Chưa có |
| Nhóm 07 | `codecuatai` | `dev` *(nhánh `nhom07-65httt` có 2 commit)* | 28 | Trần Văn Tài (27); `Codex <codex@localhost>` (1) | 4 / 5 | `2026-11-19 01:24:48` | 508 *(trên `dev`)* | Chưa có |
| Nhóm 08 | `DangHuy1302` | `nhom08-65httt` | 4 | Bùi Đăng Huy (4) | 4 / 5 | `2026-11-18 18:38:13` | 6 | #2 (`open`) |
| Nhóm 09 | `NgNgocAnh09` | `nhom09-65httt` | 2 | Nguyễn Thị Ngọc Ánh (2) | 4 / 5 | `2026-11-18 09:58:32` | 2 | #8 (`open`) |
| Nhóm 10 | `tamz11` | `nhom10-65httt` | 2 | Phan Văn Tâm (2) | 4 / 5 | `2026-11-18 09:36:12` | 3 | #10 (`closed`) |
| Nhóm 11 | `HieuNguyen243` | `nhom11-65httt` | 2 | Nguyễn Ngọc Hiếu (2) | 3 / 4 | `2026-11-18 10:00:56` | 2 | #7 (`open`), #6 (`closed`) |
| Nhóm 12 | `pvT111` | `nhom12-65httt` | 3 | Phạm Văn Tài (3) | 4 / 5 | `2026-11-20 23:15:41` | 25 | #3 (`closed`) |
| Nhóm 13 | `thieuquanggiabao` | `nhom13-65httt` | 4 | Thiều Quang Gia Bảo (4) | 4 / 5 | `2026-11-18 19:12:23` | 3 | #9 (`open`) |
| Nhóm 14 | `DucEvil` | `nhom14-65httt` | 7 | Đỗ Đình Đức (7) | 4 / 5 | `2026-11-11 23:06:47` | 6 | #5 (`open`), #1 (`closed`) |

---

## 3. Phân Nhóm Theo Mức Độ Commit Và Tần Suất Cập Nhật

### 3.1. Các nhóm ít commit (1 đến 2 commit)

Có **7/14 nhóm** mới dừng ở mức 1 hoặc 2 commit kể từ khi fork kho lưu trữ, chủ yếu mới nộp tệp `danhsachnhom.md` và đề cương:

1. **Nhóm ít commit nhất (1 commit) — 1 nhóm:**
   - **Nhóm 05 (`DiemQuynh05`):** Chỉ có duy nhất 1 commit (`f808bf6`) tạo từ `2026-11-12 18:50:02`. Lần push ngày `2026-11-18 09:25:23` chỉ là thao tác đổi tên nhánh sang `nhom05-65httt` trên cùng commit cũ; thư mục bên trong vẫn giữ tên `nhom05_65httt/`.
2. **Nhóm có 2 commit — 6 nhóm:**
   - **Nhóm 01 (`aanhthaoo`):** 2 commit (`2026-11-11` và `2026-11-18`), chưa mở PR.
   - **Nhóm 02 (`minhnguyendev05`):** 2 commit (`2026-11-12` và `2026-11-18`), đã mở PR #4 (`open`).
   - **Nhóm 06 (`maingocanh2003`):** 2 commit (`2026-11-17` và `2026-11-18`), chưa mở PR.
   - **Nhóm 09 (`NgNgocAnh09`):** 2 commit (`2026-11-13` và `2026-11-18`), đã mở PR #8 (`open`).
   - **Nhóm 10 (`tamz11`):** 2 commit (cả 2 đều thực hiện trong sáng `2026-11-18` cách nhau 3 phút), PR #10 hiện `closed`.
   - **Nhóm 11 (`HieuNguyen243`):** 2 commit (`2026-11-12` và `2026-11-18`), đã mở PR #7 (`open`).

### 3.2. Các nhóm có mức commit trung bình (3 đến 5 commit)

Có **5/14 nhóm** đạt từ 3 đến 5 commit:

- **Nhóm 03 (`thanhtung111205`):** 3 commit (`2026-11-11` đến `2026-11-12`).
- **Nhóm 12 (`pvT111`):** 3 commit (`2026-11-11` đến `2026-11-20`), đã bắt đầu đẩy 25 tệp mã nguồn backend (`src/backend/`). Lưu ý PR #3 đang ở trạng thái `closed`.
- **Nhóm 08 (`DangHuy1302`):** 4 commit (`2026-11-12` đến `2026-11-18`), đã mở PR #2 (`open`).
- **Nhóm 13 (`thieuquanggiabao`):** 4 commit (tập trung trong ngày `2026-11-18`), đã mở PR #9 (`open`).
- **Nhóm 04 (`Haithinh32`):** 5 commit (`2026-11-11` đến `2026-11-21 07:58:21`), cập nhật đều từ đề cương đến chuẩn hóa nhánh/thư mục nhưng chưa mở PR.

### 3.3. Các nhóm có nhiều commit (trên 5 commit)

Có **2/14 nhóm** đạt trên 5 commit:

- **Nhóm 14 (`DucEvil`):** 7 commit (toàn bộ thực hiện trong tối `2026-11-11`), đã mở PR #5 (`open`).
- **Nhóm 07 (`codecuatai`):** 28 commit (`2026-11-11` đến `2026-11-19 01:24:48`) với 508 tệp mã nguồn và tài liệu kỹ thuật. Tuy nhiên, 26/28 commit đang nằm trên nhánh `dev` (nhánh mặc định của fork) thay vì nhánh quy định `nhom07-65httt`, đồng thời nhóm tạo thêm 2 tệp ngoài thư mục nhóm tại `.github/workflows/` và chưa mở PR về kho gốc.

### 3.4. Nhóm không có hoạt động mới trong tuần gần nhất (trước 2026-11-13)

- **Nhóm 14 (`DucEvil`):** Không có thêm commit mới kể từ `2026-11-11 23:06:47` (10 ngày).
- **Nhóm 03 (`thanhtung111205`):** Không có thêm commit mới kể từ `2026-11-12 14:03:44` (9 ngày).

---

## 4. Thống Kê Cá Nhân Chưa Thực Hiện Commit (51 / 65 Sinh Viên)

Tính đến `2026-11-21 09:10`, toàn bộ 14 kho fork đều chưa ghi nhận commit của thành viên thứ hai (không có dữ liệu tác giả thứ hai trong `author`, `committer` hay `Co-authored-by`). Tổng cộng có **51 sinh viên chưa có bất kỳ commit nào**, danh sách chi tiết theo từng nhóm như sau:

| Nhóm | Tổng TV | Đã commit (1 TV/nhóm) | Danh sách cá nhân chưa có commit (MSV - Vai trò) |
| :--- | :---: | :--- | :--- |
| Nhóm 01 | 5 | Trương Thảo Anh (`aanhthaoo`) | 1. Phạm Hoàng Vũ (`2351160566` - Thành viên)<br>2. Nguyễn Văn Quang (`2351160542` - Thành viên)<br>3. Vũ Văn Quảng (`2351160543` - Thành viên)<br>4. Phan Thị Sông Thương (`2351160557` - Thành viên) |
| Nhóm 02 | 5 | Nguyễn Anh Minh (`minhnguyendev05`) | 1. Lê Minh Tú (`2351160562` - Thành viên)<br>2. Nghiêm Xuân Trường (`2351160561` - Thành viên)<br>3. Trần Đức Trung (`2251162191` - Thành viên)<br>4. Nguyễn Thị Yên (`2351160567` - Thành viên) |
| Nhóm 03 | 5 | Giang Thanh Tùng (`thanhtung111205`) | 1. Tạ Thị Ngọc Anh (`2351160503` - Thành viên)<br>2. Nguyễn Thái Anh (`2351160502` - Thành viên)<br>3. Nguyễn Hoàng Anh (`2251161939` - Thành viên)<br>4. Hoàng Hữu Hưng (`2351160525` - Thành viên) |
| Nhóm 04 | 3 | Ngô Hải Thịnh (`Haithinh32`) | 1. Nguyễn Văn Hiếu (`2351160520` - Thành viên)<br>2. Đặng Thành Lộc (`2351160534` - Thành viên) |
| Nhóm 05 | 4 | Nguyễn Thị Diễm Quỳnh (`DiemQuynh05`) | 1. Đinh Thị Lan Anh (`2351160500` - Thành viên)<br>2. Nguyễn Quang Đức (`2351160512` - Thành viên)<br>3. Nguyễn Anh Quân (`2351160541` - Thành viên) |
| Nhóm 06 | 4 | Trần Mai Ngọc Anh (`maingocanh2003`) | 1. Trần Thị Thùy Dương (`2351160513` - Thành viên)<br>2. Nguyễn Thế Nguyên (`2351160539` - Thành viên)<br>3. Hồ Sỹ Trung (`2351160560` - Thành viên) |
| Nhóm 07 | 5 | Trần Văn Tài (`codecuatai`) | 1. Nguyễn Việt Hoàng (`2351160522` - Thành viên)<br>2. Phạm Quang Huy (`2351160529` - Thành viên)<br>3. Triệu Thị Tuyết Mai (`2351160535` - Thành viên)<br>4. Nguyễn Văn Tiến (`2351160558` - Thành viên) |
| Nhóm 08 | 5 | Bùi Đăng Huy (`DangHuy1302`) | 1. Bùi Gia Hiếu (`2351160518` - Thành viên)<br>2. Vũ Tuấn Hiệp (`2351160517` - Thành viên)<br>3. Dương Quỳnh Trang (`2351160559` - Thành viên)<br>4. Lưu Tuấn Minh (`2251162072` - Thành viên) |
| Nhóm 09 | 5 | Nguyễn Thị Ngọc Ánh (`NgNgocAnh09`) | 1. Đặng Thị Thu Hương (`2351160527` - Thành viên)<br>2. Lê Duy Khánh (`2351160532` - Thành viên)<br>3. Nguyễn Minh Phú (`2351160540` - Thành viên)<br>4. Trần Quang Thịnh (`2351160555` - Thành viên) |
| Nhóm 10 | 5 | Phan Văn Tâm (`tamz11`) | 1. Trịnh Thị Vân *(chưa điền MSV)* - Thành viên<br>2. Bùi Ngọc Tùng Sơn *(chưa điền MSV)* - Thành viên<br>3. Nguyễn Tuấn Kiệt *(chưa điền MSV)* - Thành viên<br>4. Đỗ Quang Nam Anh *(chưa điền MSV)* - Thành viên |
| Nhóm 11 | 4 | Nguyễn Ngọc Hiếu (`HieuNguyen243`) | 1. Hoàng Phương Thảo (`2351160553` - Thành viên)<br>2. Trần Thị Minh Thư (`2351160556` - Thành viên)<br>3. Trịnh Khắc Hưng *(tệp nhóm đang ghi nhầm MSV `2351160519` trùng với Nguyễn Ngọc Hiếu)* - Thành viên |
| Nhóm 12 | 5 | Phạm Văn Tài (`pvT111`) | 1. Vũ Thị Hồng (`2351160524` - Thành viên)<br>2. Nguyễn Quang Khải (`2351160530` - Thành viên)<br>3. Nguyễn Tài Tân (`2351160550` - Thành viên)<br>4. Phạm Đình Việt (`2351160565` - Thành viên) |
| Nhóm 13 | 5 | Thiều Quang Gia Bảo (`thieuquanggiabao`) | 1. Trần Minh Giang *(tệp nhóm không có cột MSV)* - Thành viên<br>2. Nguyễn Thu Giang *(tệp nhóm không có cột MSV)* - Thành viên<br>3. Trương Quốc Thái *(tệp nhóm không có cột MSV)* - Thành viên<br>4. Nguyễn Thị Khanh *(tệp nhóm không có cột MSV)* - Thành viên |
| Nhóm 14 | 5 | Đỗ Đình Đức (`DucEvil` - Thành viên) | 1. **Đinh Văn Mạnh (`2351106536` - Nhóm trưởng)**<br>2. Phạm Hồng Thái (`2351160551` - Thành viên)<br>3. Nguyễn Mạnh Đức (`2351106511` - Thành viên)<br>4. Phạm Trọng Sang (`2351106545` - Thành viên) |

---

## 5. Ghi Nhận Kỹ Thuật Và Khuyến Nghị Quản Lý

1. **Tình trạng thiếu cộng tác thực tế trên GitHub (100% fork chỉ có 1 người commit):**
   - Toàn bộ 14 nhóm mới chỉ có một tài khoản duy nhất (13/14 nhóm là nhóm trưởng; riêng Nhóm 14 là thành viên Đỗ Đình Đức, còn nhóm trưởng Đinh Văn Mạnh chưa commit) thực hiện thao tác trên GitHub. Cần yêu cầu các nhóm trưởng thêm đầy đủ thành viên làm Collaborator trên kho fork (theo mục 2.3 trong [README.md](README.md)) để đánh giá được đóng góp cá nhân qua lịch sử commit.
2. **Định danh Git cục bộ chưa chuẩn tại một số cá nhân:**
   - **Nhóm 11 (`HieuNguyen243`):** Commit đầu tiên (`b533959`) dùng email `learningacc448@gmail.com` chưa liên kết tài khoản GitHub; commit thứ hai (`10b2cd9`) đã đổi sang `hieunguyen0816470@gmail.com` khớp tài khoản.
   - **Nhóm 12 (`pvT111`):** Toàn bộ 3 commit để `git config user.name` là `unknown` (tuy nhiên email khớp GitHub `pvT111`).
   - **Nhóm 07 (`codecuatai`):** Commit `4cbe718` mang tác giả `Codex <codex@localhost>` (tài khoản công cụ AI cục bộ), không phải tài khoản GitHub cá nhân của sinh viên.
3. **Sai sót dữ liệu trong `danhsachnhom.md` và trạng thái PR cần nhắc nhở:**
   - **Nhóm 10 (`tamz11`):** Bỏ trống cột Mã sinh viên và Email trong `danhsachnhom.md`; PR #10 đã đóng (`closed`).
   - **Nhóm 11 (`HieuNguyen243`):** Ghi lặp STT `3` và ghi nhầm MSV/email của thành viên Trịnh Khắc Hưng trùng với Nguyễn Ngọc Hiếu (`2351160519`); mục 4 vẫn giữ nguyên mẫu.
   - **Nhóm 13 (`thieuquanggiabao`):** Bảng thành viên tự đổi cấu trúc, thiếu cột Mã sinh viên, Lớp sinh hoạt, Tỷ lệ đóng góp (%) và Email theo quy định mục 3 của [README.md](README.md).
   - **Nhóm 12 (`pvT111`):** Đã cập nhật thêm mã nguồn backend (`290c5d0`) nhưng PR #3 trước đó đang ở trạng thái `closed`, cần mở PR mới khi nộp.
   - **Nhóm 01, 03, 04, 05, 06, 07:** Chưa mở PR về kho gốc (Nhóm 05 cần đổi tên thư mục `nhom05_65httt/` thành `nhom05-65httt/`; Nhóm 07 cần đưa mã nguồn về nhánh `nhom07-65httt` và gỡ `.github/workflows/` ở gốc repo).
