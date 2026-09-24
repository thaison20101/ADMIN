# ============================================================
# 1 LENH: KIEM 1 LAN TOAN BO FOLDER (KHONG cai hourly)
# Alias -> CHAY_KIEM_1_LAN_TOAN_BO.ps1
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_CHECK_TOAN_BO_FOLDER.ps1
# ============================================================

$ErrorActionPreference = "Continue"
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "CHAY_KIEM_1_LAN_TOAN_BO.ps1")
exit $LASTEXITCODE
