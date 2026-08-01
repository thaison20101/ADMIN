# build for BIG DATA

Thư mục kết quả xử lý PDF xét nghiệm Thuận Kiều → nhập **Khám cận lâm sàng** (Medinet).

Đường dẫn Windows tương ứng: `C:\Users\Administrator\Desktop\BIG DATA PDF\build for BIG DATA`

## File chính

| File | Mô tả |
|------|--------|
| `CLS_ket_qua_tu_PDF_de_kiem_tra.xlsx` | Toàn bộ kết quả lấy từ PDF, đã đổi đơn vị theo web (để kiểm tra) |
| `CLS_can_kiem_tra_lai.xlsx` | Người thiếu thông tin / không tìm thấy / đã có CLS / lỗi import |
| `CLS_import_log.xlsx` | Nhật ký import từng người |
| `web_list_M3.json` / `web_list_M4.json` | Danh sách bệnh nhân trên web để đối khớp |
| `CLS_import_summary.json` | Tổng kết |

## Quy tắc

- Sinh ≤ 1967 → M4 (Người cao tuổi); sau 1967 → M3 (18-59)
- M3: `LoaiKham = 5152` (Khám Định Kỳ), **không** nhập Khám Tuyển
- Bạch cầu trung tính = **Neutrophils #** (G/L)
- Nước tiểu Âm tính → `Negative` (Nitrit → Id `5120`)
