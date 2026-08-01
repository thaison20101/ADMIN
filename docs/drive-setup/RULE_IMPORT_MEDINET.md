# Rule import Medinet — Khám cận lâm sàng

Tài khoản: dùng biến môi trường `MEDINET_USER` / `MEDINET_PASS` (không commit mật khẩu).

Web: https://quanlyskcd.medinet.org.vn/account/login

## Luồng tự động (hourly)

Điều kiện:
- Laptop **bật**
- Google Drive Desktop sync folder `G:\Drive của tôi\PKDK_Thuankieu_Pipeline`
- Task Scheduler job `PKDK_Hourly_Sync` đã cài (`pipeline\install_hourly_task.ps1`)

Mỗi ~1 giờ job chạy `pipeline\run_hourly.ps1` → `hourly_sync.py`:
1. Quét PDF mới trong `INBOX_CLS`
2. Trích kết quả XN từ PDF
3. Khớp BN trên Medinet (M3/M4 theo năm sinh)
4. Nếu **đã có TTHC** và **chưa có CLS** → import form **Khám cận lâm sàng**
5. Luôn **Khám định kỳ** (`LoaiKham=5152`) — không ghi Khám tuyển / `DHDL_*`
6. `IMPORTED` → chuyển file sang `PROCESSED`
7. Thiếu TTHC → `WAITING_ADMIN` (giữ PDF, chờ giờ sau)
8. Web đã có CLS → `SKIP_ALREADY_CLS` (không ghi đè)

Giới hạn mỗi lần chạy: `import_rules.max_imports_per_run` (mặc định 80). Case còn lại chờ vòng sau.

Output:
```text
G:\Drive của tôi\build for Supper Data\
  excel_preview\CLS_auto_import_*.xlsx
  logs\
  cases_snapshot\
```

Cài / kiểm tra task:
```powershell
cd C:\Users\thais\ADMIN
git pull origin cursor/drive-hourly-pipeline-df0f
powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1
# chạy thử ngay:
powershell -ExecutionPolicy Bypass -File .\pipeline\run_hourly.ps1
```

Trong `pipeline\config.local.json`:
- `drive.local_sync_root` = `G:/Drive của tôi/PKDK_Thuankieu_Pipeline`
- `drive.build_root` = `G:/Drive của tôi/build for Supper Data`
- `medinet.date_from` = ngày bắt đầu tìm BN (vd `01/07/2026`)
- `medinet.date_to` = để trống `""` → lấy **hôm nay**

## Quy tắc map kết quả
- `Neutrophils #` = số lượng bạch cầu trung tính
- Nước tiểu `Âm tính` → `Negative`; Nitrit → option `5120`
- Đổi đơn vị khi cần (g/dL→g/L, %→L/L, mg/dL→mmol/L…)

## Trạng thái case
- `WAITING_ADMIN` — có PDF, chưa có TTHC trên web
- `READY_IMPORT` — đã có TTHC, chờ/đang import CLS
- `IMPORTED` — đã import xong, skip
- `SKIP_ALREADY_CLS` — web đã có CLS
- `ERROR_IMPORT` / `PARSE_ERROR` — lỗi

## Chạy tay (batch cũ / kiểm tra)

Preview Excel:
```powershell
powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_preview.ps1
```

Import từ Excel preview (đã duyệt):
```powershell
powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_import.ps1 -Limit 5
powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_import.ps1
```
