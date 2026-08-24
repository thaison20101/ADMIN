# ADMIN — Pipeline nhập liệu liên tục (Google Drive)

## Nhanh
1. Tạo folder Drive theo hướng dẫn: [`docs/drive-setup/HUONG_DAN_GOOGLE_DRIVE.md`](docs/drive-setup/HUONG_DAN_GOOGLE_DRIVE.md)
2. Upload file XN vào Drive `INBOX_CLS` (từng phần nhỏ)
3. Chạy thử: `python pipeline/hourly_sync.py --dry-run`
4. Treo hourly (phần A):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1
   ```
5. Rule import Medinet: [`docs/drive-setup/RULE_IMPORT_MEDINET.md`](docs/drive-setup/RULE_IMPORT_MEDINET.md)
6. Mọi file xuất ra lưu tại: `G:\Drive của tôi\build for Supper Data`

## Cấu trúc
- `INBOX_CLS/` — file mới (local mirror của Drive)
- `PROCESSED/` — đã xử lý
- `ERROR/` — lỗi
- `tracking/cases.csv` — sổ trạng thái (skip `IMPORTED`)
- `pipeline/hourly_sync.py` — job mỗi giờ

## Lưu ý
- Rule import lên web **chưa bật** — chờ bạn chốt yêu cầu import.
- Không commit PDF lớn / mật khẩu Medinet lên git.
