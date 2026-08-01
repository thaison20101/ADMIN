# build for BIG DATA

Thư mục kết quả xử lý PDF xét nghiệm Thuận Kiều → nhập **Khám cận lâm sàng** (Medinet).

Đường dẫn Windows tương ứng: `C:\Users\Administrator\Desktop\BIG DATA PDF\build for BIG DATA`

## Tổng kết import

| Trạng thái | Số lượng |
|---|---:|
| Tổng PDF | 1287 |
| Import thành công | **201** (M3: 120, M4: 81) |
| Đã có kết quả CLS trên web | 886 |
| Không tìm thấy trên web | 199 |
| Thiếu kết quả PDF | 1 |
| Lỗi | 0 |

## File chính

| File | Mô tả |
|------|--------|
| `CLS_ket_qua_tu_PDF_de_kiem_tra.xlsx` | Toàn bộ kết quả lấy từ PDF, đã đổi đơn vị theo web (để kiểm tra) |
| `CLS_can_kiem_tra_lai.xlsx` | Người thiếu thông tin / không tìm thấy / đã có CLS (nhiều sheet) |
| `CLS_import_log.xlsx` | Nhật ký import từng người (+ sheet Thành công) |
| `CLS_import_summary.json` | Tổng kết số liệu |
| `web_list_M3.json` / `web_list_M4.json` | Danh sách bệnh nhân trên web để đối khớp |

## Quy tắc đã áp dụng

- Sinh ≤ 1967 → ưu tiên M4 (Người cao tuổi); sau 1967 → M3 (18-59). Nếu không thấy ở list chính thì thử list còn lại (một số người ≤1967 được đăng ký ở M3 trên web).
- M3/M4: `LoaiKham = 5152` (**Khám Định Kỳ**), **không** nhập Khám Tuyển
- Bạch cầu trung tính = **Neutrophils #** (G/L), không dùng %
- Nước tiểu Âm tính → `Negative` (Nitrit → Id `5120`)
- Đổi đơn vị: HGB g/dL→g/L (×10); HCT %→L/L (÷100); Glucose mg/dL→mmol/L (÷18); Urea mg%→mmol/L (÷6); Creatinine mg/dL→µmol/L (×88.4)

## Tool scripts

Nằm trong repo: `cls-import/` (`extract_pdf_labs.py`, `download_web_lists.py`, `match_and_import_cls.py`).
