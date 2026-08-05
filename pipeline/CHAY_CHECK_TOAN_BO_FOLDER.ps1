# ============================================================
# 1 LENH: CHECK TOAN BO FOLDER + BAT HOURLY MOI 1 GIO
# (alias cua CHAY_QUET_LAN_DAU.ps1 — quet MOI folder ke ca PROCESSED)
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_CHECK_TOAN_BO_FOLDER.ps1
#
# PowerShell Admin. KHONG click vao cua so khi dang chay.
# ============================================================

$ErrorActionPreference = "Continue"
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "CHAY_QUET_LAN_DAU.ps1")
exit $LASTEXITCODE
