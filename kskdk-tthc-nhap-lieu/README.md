# KSKDK_TTHC — Nhập Excel & Import lên web

Form: **Thông tin hành chính** (`KSKDK_TTHC`)  
URL: https://quanlyskcd.medinet.org.vn/nav_group/kskdk_thongtinkham/app/main/dynamicform/viewer/KSKDK_TTHC

Web **không có nút Import file**. Bộ công cụ này tạo Excel đúng cột form và gửi dữ liệu qua API `FormToDatabaseInsert` bằng tài khoản của bạn.

## File chính

| File | Mục đích |
|------|----------|
| `KSKDK_TTHC_mau_nhap.xlsx` | File Excel để nhập liệu (sheet `NhapLieu` + danh mục `DM_*` + `TimKiem` + `DaImport`) |
| `import_excel.py` | Import Excel lên hệ thống |
| `search_fill.py` | Tìm một phần theo CCCD / họ tên / SĐT trong Excel |
| `excel_autocomplete.py` | Thêm cột GoiY_* gợi ý danh mục khi gõ một phần |
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

# Import thật (bỏ qua nếu trùng cùng ngày)
python3 import_excel.py \
  --excel KSKDK_TTHC_mau_nhap.xlsx \
  --user YOUR_USER \
  --password 'YOUR_PASSWORD' \
  --on-duplicate skip
```

Kết quả từng dòng nằm trong `import_result.jsonl`. Script ghi lại cột **MaBanGhi**, **TrangThai**, **GhiChu** trên sheet `NhapLieu`.

### 3) Tìm kiếm một phần (trong Excel)

1. Mở sheet **TimKiem**, nhập một phần CCCD / họ tên / SĐT (ví dụ `00236`, `dung`, `mai`)
2. Chạy:

```bash
python3 search_fill.py --excel KSKDK_TTHC_mau_nhap.xlsx
# hoặc trực tiếp:
python3 search_fill.py --excel KSKDK_TTHC_mau_nhap.xlsx --cccd 00236
python3 search_fill.py --excel KSKDK_TTHC_mau_nhap.xlsx --hoten dung --fill-nhaplieu
```

Tìm trong sheet **DaImport** (đã import) và **NhapLieu** (đang nhập). `--fill-nhaplieu` chép kết quả tốt nhất sang dòng trống `NhapLieu`.

### 4) Gợi ý danh mục khi gõ một phần (xã/phường, tỉnh...)

Trên sheet **NhapLieu**, mỗi cột danh mục có cột **GoiY_*** bên cạnh (nền vàng):

| Bạn gõ (cột XaPhuong) | Excel gợi ý (cột GoiY_XaPhuong) |
|-----------------------|----------------------------------|
| `MINH PHUNG` | `Phường Minh Phụng` |
| `BINH THOI` | `Phường Bình Thới` |

- Gõ **một phần**, **không dấu cũng được** (vd. `MINH PHUNG`)
- Cột **GoiY_*** tự hiện tên đầy đủ — copy sang cột nhập nếu cần
- Script import **tự dùng GoiY_*** nếu cột nhập chỉ gõ một phần

Sheet **TraCuuDM**: tra nhiều gợi ý cùng lúc (chọn loại danh mục + từ khóa).

Cập nhật file Excel cũ:

```bash
python3 excel_autocomplete.py --excel KSKDK_TTHC_mau_nhap.xlsx
```

### 5) Tạo lại Excel (khi danh mục đổi)

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
- **MaBanGhi**, **TrangThai**, **GhiChu** — script ghi sau khi import

## Người đã có trên hệ thống (trùng)

Nếu công dân **đã khám cùng ngày**, cùng hình thức chi trả và đơn vị, API trả lỗi dạng:

> Công dân đã khám bằng 'Ngân sách nhà nước' tại Phòng khám ... vào ngày dd/MM/yyyy

Script đánh dấu **TrangThai = TRUNG**, **không tạo bản ghi mới** (mặc định `--on-duplicate skip`). Dòng vẫn được ghi vào sheet `DaImport` để tra cứu sau.

| TrangThai | Ý nghĩa |
|-----------|---------|
| THANH_CONG | Lưu mới thành công, có MaBanGhi |
| TRUNG | Đã khám cùng ngày / trùng trên hệ thống |
| LOI | Lỗi (SĐT không hợp lệ, CCCD không khớp ngày sinh, thiếu nghề nghiệp...) |

**Lưu ý SĐT:** phải đủ 10 số, bắt đầu bằng `0`, và hệ thống kiểm tra đầu số nhà mạng thật (số giả như `0987654321` thường bị từ chối).

**Lưu ý CCCD:** phải đúng định dạng và khớp ngày sinh / giới tính.

## Kỹ thuật (đã xác minh với tài khoản đơn vị)

- FormId: `1000092`, FormVersionId: `1000095`
- SessionSiteId form: `130`
- Store ghi: `KSKDK_TTHC_Set`
- API ghi: `POST /api/services/app/FormViewer/FormToDatabaseInsert`

## Bảo mật

- **Không** commit mật khẩu vào git
- Nên đổi mật khẩu nếu đã gửi qua chat
- Chỉ import trên tài khoản/đơn vị được cấp quyền
