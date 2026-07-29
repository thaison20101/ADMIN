# Bộ công cụ nhập liệu nhanh — `KSKDK_TTHC` (Thông tin hành chính)

Form đích:

`https://quanlyskcd.medinet.org.vn/nav_group/kskdk_thongtinkham/app/main/dynamicform/viewer/KSKDK_TTHC`

Hệ thống là Angular + DevExtreme Dynamic Form (Hinnova/ABP). Form code: **`KSKDK_TTHC`**, form id: **`1000092`**, tên: **Thông tin hành chính**.

## Cách dùng nhanh (khuyến nghị)

### 1) Userscript phím tắt (Tampermonkey / Violentmonkey)

1. Cài [Tampermonkey](https://www.tampermonkey.net/) trên Chrome/Edge.
2. Tạo script mới, dán nội dung file `userscript-kskdk-tthc.user.js`.
3. Đăng nhập hệ thống bằng **tài khoản của bạn**, mở đúng link form trên.
4. Panel góc phải hiện ra → dùng phím tắt bên dưới.

| Phím | Chức năng |
|------|-----------|
| `Ctrl + S` | Bấm **Lưu** |
| `Ctrl + Enter` | Lưu rồi chuẩn bị bản ghi mới (nếu có nút Thêm/Làm trống) |
| `Ctrl + Shift + E` | Xuất schema + CSV mẫu theo đúng field đang mở |
| `Ctrl + Shift + V` | Dán 1 dòng Excel (TSV) vào form theo thứ tự cột đã export |
| `Alt + →` / `Alt + ←` | Nhảy field kế / trước |
| `F2` | Focus field đầu tiên có thể nhập |
| `?` (khi không gõ trong ô) | Hiện/ẩn hướng dẫn phím tắt |

### 2) File Excel/CSV nhập hàng loạt

1. Mở form khi đã đăng nhập → `Ctrl + Shift + E` → tải `KSKDK_TTHC_mau.csv`.
2. Điền nhiều dòng trong Excel (giữ nguyên dòng tiêu đề = `dataField`).
3. Lưu CSV UTF-8.
4. Chạy:

```bash
python3 bulk_submit.py \
  --csv ./du_lieu.csv \
  --token "PASTE_ACCESS_TOKEN" \
  --site-id "PORTAL_SESSIONSITEID_CUA_BAN"
```

Cách lấy token / site id khi đã đăng nhập (F12 → Console):

```js
// Token đang dùng (đã giải mã qua app) — hoặc copy từ Network → Authorization
copy(JSON.parse(localStorage.getItem('1_keys')||'{}'))

// Site đang chọn
copy(sessionStorage.getItem('PORTAL_SESSIONSITEID'))
```

Hoặc dùng panel userscript → nút **Sao chép token/site** rồi dán vào lệnh.

### 3) Helper HTML (không cần cài extension)

Mở `helper.html` bằng trình duyệt, dán schema JSON đã export (`Ctrl+Shift+E`), dán dữ liệu Excel, sinh payload JSON để gửi.

## API đã phân tích (backend)

Base API: `https://be-qlskcd.medinet.org.vn`

| Mục đích | Endpoint |
|----------|----------|
| Lấy form id theo code | `GET /api/services/app/FormViewer/GetFormIdByFormCode?code=KSKDK_TTHC` |
| Lấy cấu trúc form | `GET /api/services/app/FormViewer/GetFormVersion?formId=...&sessionSiteId=...&LatestVersion=1&displayMode=0` |
| Thêm bản ghi | `POST /api/services/app/FormViewer/FormToDatabaseInsert?form_id=...&UrlPage=...&ispopup=false&istab=false` |
| Cập nhật bản ghi | `POST /api/services/app/FormViewer/FormToDataBaseUpdate?form_id=...&tab_id=...&record_id=...&...` |
| Lưu form data | `POST /api/services/app/FormViewer/PostFormData?form_id=...&record_id=...&SessionSiteId=...` |

Header bắt buộc khi gọi API:

- `Authorization: Bearer <accessToken>`
- `SessionSiteId: <PORTAL_SESSIONSITEID>`
- `displaymode: 0`

## Lưu ý

- Công cụ chỉ dùng **phiên đăng nhập của bạn**; không bypass phân quyền.
- Schema field phụ thuộc đơn vị (`SessionSiteId`) nên luôn export từ form đang mở.
- Kiểm tra vài bản ghi thử trước khi nhập hàng loạt.
- Không commit token / mật khẩu vào git.
