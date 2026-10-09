# Quy tắc trạng thái case

| status | Nghĩa | Hành động job hourly |
|--------|------|----------------------|
| `NEW_LAB` | Có file xét nghiệm mới, chưa kiểm tra TTHC | Check Medinet TTHC |
| `WAITING_ADMIN` | Có XN, chưa có thông tin hành chính | Mỗi giờ check lại TTHC |
| `READY_IMPORT` | Đã có TTHC, sẵn sàng import KQ lên web | Import theo rule sẽ bổ sung |
| `IMPORTED` | Đã import thành công | **BỎ QUA mãi** |
| `ERROR` | Lỗi khi xử lý | Retry tối đa N lần, rồi giữ để xem tay |

## Khóa case (`case_key`)
Ưu tiên theo thứ tự:
1. `ma_phieu` nếu có
2. `cccd` + `ngay_kham` + `mau_kham`
3. `file_hash` của file nguồn

## Nguyên tắc
- Case `IMPORTED` không chạy lại (tránh mất thời gian / import trùng).
- Case `WAITING_ADMIN` được quét lại mỗi giờ.
- File nguồn upload liên tục vào Google Drive `INBOX_CLS`.
- Sau khi xử lý xong (IMPORTED) → chuyển file sang `PROCESSED`.
- Lỗi cứng → chuyển sang `ERROR` + ghi `notes`.
