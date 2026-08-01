# Hướng dẫn Google Drive + Pipeline nhập liệu liên tục

Mục tiêu: upload file XN máu từng phần lên Drive → laptop/Cursor đọc liên tục → theo dõi case chưa có TTHC → khi có TTHC thì import web → bỏ qua case đã `IMPORTED`.

## 1) Tạo cấu trúc folder trên Google Drive

Vào https://drive.google.com → **Mới → Thư mục mới**:

```text
PKDK_Thuankieu_Pipeline/
  INBOX_CLS/      ← mọi người upload file mới vào đây
  PROCESSED/      ← hệ thống chuyển vào khi import xong
  ERROR/          ← file lỗi cần xem tay
```

## 2) Cài Google Drive for Desktop (Windows)

1. Tải: https://www.google.com/drive/download/
2. Đăng nhập đúng tài khoản Drive dung lượng lớn của bạn
3. Chọn sync kiểu **Mirror files** (khuyến nghị) cho folder `PKDK_Thuankieu_Pipeline`
4. Ghi nhớ đường dẫn local, ví dụ:
   `C:\Users\Administrator\My Drive\PKDK_Thuankieu_Pipeline`
   hoặc
   `G:\My Drive\PKDK_Thuankieu_Pipeline`

## 3) Nối folder Drive với repo ADMIN

Trong repo (PowerShell):

```powershell
cd C:\Users\Administrator\Desktop\ADMIN
copy .\pipeline\config.example.json .\pipeline\config.local.json
notepad .\pipeline\config.local.json
```

Sửa:

```json
"local_sync_root": "C:/Users/Administrator/My Drive/PKDK_Thuankieu_Pipeline"
```

`config.local.json` đã được `.gitignore` — không đẩy credential/path máy lên git nếu không muốn.

## 4) Cách upload từng phần nhỏ

- Chỉ bỏ file mới vào `INBOX_CLS`
- Nên đặt tên file thống nhất, ví dụ:
  `DDMMYY-ID - HO TEN - YYYY - G.pdf`
- Upload theo lô (50–200 file/lần) để dễ đối chiếu
- **Không** sửa/xóa file trong `PROCESSED` trừ khi xử lý tay

## 5) Chạy thử 1 vòng

```powershell
cd C:\Users\Administrator\Desktop\ADMIN
python .\pipeline\hourly_sync.py --dry-run
```

Kết quả:
- File mới → ghi vào `tracking/cases.csv` với status `NEW_LAB` / `WAITING_ADMIN`
- Case `IMPORTED` sẽ bị bỏ qua ở các vòng sau

## 6) Treo chạy mỗi 1 giờ (Windows Task Scheduler)

1. Mở **Task Scheduler** → Create Basic Task
2. Trigger: **Daily** → Advanced → Repeat every **1 hour**
3. Action: Start a program
   - Program: `powershell.exe`
   - Arguments:
     `-ExecutionPolicy Bypass -File "C:\Users\Administrator\Desktop\ADMIN\pipeline\run_hourly.ps1"`
4. Settings: bật “Run whether user is logged on or not” nếu máy treo account

## 7) Trạng thái case (tóm tắt)

- `NEW_LAB` → vừa thấy file XN
- `WAITING_ADMIN` → chưa có TTHC, giờ sau check lại
- `READY_IMPORT` → đã có TTHC, chờ import web
- `IMPORTED` → xong, không chạy lại
- `ERROR` → lỗi, xem folder `ERROR` + cột `notes`

Chi tiết: `tracking/status_rules.md`

## 8) Phần sẽ bổ sung sau khi bạn chốt yêu cầu import web

Hiện tại 2 hàm trong `pipeline/hourly_sync.py` còn stub:
- `check_admin_info()` — tra Medinet đã có TTHC chưa
- `import_lab_to_web()` — import KQ xét nghiệm lên web

Khi bạn gửi rule import (field nào, mẫu M3/M4, điều kiện máu, …) sẽ gắn vào 2 hàm này và bật:

```json
"import_rules": { "enabled": true }
```

## 9) Quyền chia sẻ Drive

- Folder `INBOX_CLS`: cho phép team upload
- Folder `PROCESSED` / `ERROR`: hạn chế sửa nếu cần
- Repo GitHub chỉ giữ code + `tracking/cases.csv`, không chứa PDF lớn
