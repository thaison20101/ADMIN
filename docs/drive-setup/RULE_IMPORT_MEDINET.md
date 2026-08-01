# Rule import Medinet — Khám cận lâm sàng

Tài khoản: dùng biến môi trường `MEDINET_USER` / `MEDINET_PASS` (không commit mật khẩu).

Web: https://quanlyskcd.medinet.org.vn/account/login

## Luồng
1. Đọc PDF trong Drive `INBOX_CLS` → trích kết quả XN
2. Xuất Excel preview để kiểm tra (bắt buộc trước khi import hàng loạt)
3. Đăng nhập Medinet
4. Tìm BN theo năm sinh:
   - Sinh **≤ 1967** → Khám sức khỏe → **Người cao tuổi (M4)**
   - Sinh **≥ 1968** → Khám sức khỏe → **Người từ đủ 18–59 tuổi (M3)**
5. Với M3: phần **Loại khám** chỉ tích **Khám định kỳ** — **KHÔNG** import vào **Khám tuyển**
6. Điền toàn bộ kết quả vào form **Khám cận lâm sàng**
7. Case thiếu TTHC / đã có CLS rồi → ghi Excel riêng để nhập lại / bỏ qua
8. Case đã `IMPORTED` → không chạy lại

## Quy tắc map kết quả
- WBC: một số giá trị trên web đã dịch tiếng Việt → đọc PDF kỹ, map đúng option web
- `Neutrophils #` = Số lượng bạch cầu trung tính (các chỉ số kết thúc bằng `#` là số lượng)
- Nước tiểu: PDF ghi `Âm tính` → trên web điền `Negative`
- Đổi đơn vị cho khớp đơn vị trên web nếu PDF khác đơn vị

## File output (bắt buộc)
Tất cả file tạo ra trong quá trình lưu tại:

`G:\Drive của tôi\build for Supper Data`

Gợi ý cấu trúc:
```text
build for Supper Data/
  excel_preview/          ← Excel kết quả trích từ PDF (để duyệt trước)
  missing_or_updated/     ← thiếu TTHC / đã có CLS cần kiểm tra lại
  logs/                   ← log hourly
  cases_snapshot/         ← bản sao cases.csv theo ngày
```

## Trạng thái case
- `WAITING_ADMIN` — có PDF, chưa có TTHC trên web
- `READY_IMPORT` — đã có TTHC, chờ/đang import CLS
- `IMPORTED` — đã import xong, skip
- `SKIP_ALREADY_CLS` — web đã có CLS, ghi Excel kiểm tra
- `ERROR` — lỗi parse/import
