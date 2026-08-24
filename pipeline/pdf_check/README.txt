# PDF CHECK — kiem tra toan bo PDF (KHONG import CLS)
# ============================================================
# Folder code: pipeline/pdf_check/
# Runner:      pipeline/CHAY_PDF_CHECK.ps1
#
# Excel the hien:
#   - TTHC o TK1 / TK2 / ca 2 / khong
#   - PDF trung ten (hoac hash) giua cac folder
#   - Co TTHC + PDF nhung chua CLS / da CLS (tung TK)
#
# Rule match = rule import: resolve_tthc_matches
#   (ho+ten DAY DU + nam/ngay sinh/SDT/CCCD)
#
# LENH MAY A
# ----------
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_PDF_CHECK.ps1
#
# Nhanh (khong goi CLS web):
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_PDF_CHECK.ps1 -SkipCls
#
# Gioi han:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_PDF_CHECK.ps1 -Limit 200
#
# Chi 1 so folder:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_PDF_CHECK.ps1 -Folders "PROCESSED,MISSING"
#
# Ket qua: pipeline\work\build\excel_preview\PDF_CHECK_*.xlsx
# KHONG ghi G:, KHONG insert_cls, KHONG move file.
