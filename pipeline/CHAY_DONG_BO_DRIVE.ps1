# ============================================================
# DONG BO GOOGLE DRIVE FOLDERS (giong nhau tren moi may)
#
# Tao / kiem tra:
#   PKDK_Thuankieu_Pipeline\INBOX_CLS
#   PKDK_Thuankieu_Pipeline\MISSING
#   PKDK_Thuankieu_Pipeline\ERROR
#   PKDK_Thuankieu_Pipeline\PROCESSED
#   build for Supper Data\logs, excel_preview, ...
# Va ghi duong dan that vao pipeline\config.local.json
#
#   cd C:\Users\Administrator\ADMIN   (hoac thu muc ADMIN cua may)
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DONG_BO_DRIVE.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host ""
Write-Host "############################################################"
Write-Host "#  DONG BO GOOGLE DRIVE (PIPELINE + BUILD)                 #"
Write-Host "############################################################"
Write-Host ""

if (-not (Test-Path ".\pipeline\drive_paths.py")) {
  Write-Host "ERROR: chua co pipeline\drive_paths.py"
  Write-Host "Can code moi (git pull / giai ZIP branch cursor/drive-hourly-pipeline-df0f)"
  exit 1
}

Write-Host "==== Tim Drive + tao folder chuan ===="
& python ".\pipeline\drive_paths.py"
$code = $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
  Write-Host "WARN: drive_paths exit=$LASTEXITCODE"
}

Write-Host ""
Write-Host "==== Kiem tra o dia / Google Drive ===="
Get-PSDrive -PSProvider FileSystem | Format-Table Name,Root,Used,Free -AutoSize
Write-Host "Neu khong thay G: (hoac H:) -> cai Google Drive Desktop + dang nhap dung tai khoan."
Write-Host "Sau khi sync xong, chay lai script nay."

Write-Host ""
Write-Host "==== Cap nhat config.local.json + login ===="
& python ".\pipeline\ensure_config.py"

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "Hai may (cung Google Drive) se thay cung folder INBOX/MISSING/ERROR/PROCESSED."
Write-Host "Chi chay HOURLY tren 1 may de tranh import trung."
Write-Host "=========================="
exit $code
