# KSKDK_TTHC — Nhập Excel & Import lên web

Form: **Thông tin hành chính** (`KSKDK_TTHC`)  
URL: https://quanlyskcd.medinet.org.vn/nav_group/kskdk_thongtinkham/app/main/dynamicform/viewer/KSKDK_TTHC

Web **không có nút Import file**. Bộ công cụ này tạo Excel đúng cột form và gửi dữ liệu qua API `FormToDatabaseInsert` bằng tài khoản của bạn.

## File chính

| File | Mục đích |
|------|----------|
| `KSKDK_TTHC_mau_nhap.xlsx` | File Excel để nhập liệu (sheet `NhapLieu` + danh mục `DM_*`) |
| `import_excel.py` | Import Excel lên hệ thống |
| `generate_excel_template.py` | Tạo lại Excel + danh mục mới nhất từ API |
| `userscript-kskdk-tthc.user.js` | Phím tắt khi nhập tay trên web (`Ctrl+S` lưu...) |

## Cách dùng nhanh

### 1) Điền Excel

1. Mở `KSKDK_TTHC_mau_nhap.xlsx`
2. Vào sheet **NhapLieu**
3. Xóa/sửa dòng mẫu, thêm mỗi người 1 dòng
4. Các cột danh mục: chọn từ dropdown hoặc gõ đúng **Name** trong sheet `DM_*`
5. Ngày: `dd/MM/yyyy` (ví dụ `29/07/2026`)
6. Giới tính: `Nam` / `Nữ`

### 2) Import lên web

```bash
cd kskdk-tthc-nhap-lieu
pip install openpyxl

# Thử 1 dòng, chưa ghi DB
python3 import_excel.py \
  --excel KSKDK_TTHC_mau_nhap.xlsx \
  --user YOUR_USER \
  --password 'YOUR_PASSWORD' \
  --dry-run --limit 1 --skip-sample

# Import thật
python3 import_excel.py \
  --excel KSKDK_TTHC_mau_nhap.xlsx \
  --user YOUR_USER \
  --password 'YOUR_PASSWORD' \
  --skip-sample
```

Kết quả từng dòng nằm trong `import_result.jsonl`.

### 3) Tạo lại Excel (khi danh mục đổi)

```bash
python3 generate_excel_template.py \
  --user YOUR_USER \
  --password 'YOUR_PASSWORD' \
  --site-id 130 \
  --out KSKDK_TTHC_mau_nhap.xlsx
```

## Cột nhập (NhapLieu)

- NgayKham, DoiTuong, DiaDiemKham, HinhThucChiTra, HinhThucKham, NguonKhac_GhiRo
- CCCD, HoTen, NgaySinh, GioiTinh, DanToc, NhomMau, YeuToNhomMau, BHYT, SDT
- NoiOHienTai, TinhThanh, XaPhuong
- NgheNghiepId, NgheNghiep, NoiCongTac, XaPhuongCongTac, LyDoKham

## Kỹ thuật (đã xác minh với tài khoản đơn vị)

- FormId: `1000092`, FormVersionId: `1000095`
- SessionSiteId form: `130`
- Store ghi: `KSKDK_TTHC_Set`
- API ghi: `POST /api/services/app/FormViewer/FormToDatabaseInsert`

## Bảo mật

- **Không** commit mật khẩu vào git
- Nên đổi mật khẩu nếu đã gửi qua chat
- Chỉ import trên tài khoản/đơn vị được cấp quyền
