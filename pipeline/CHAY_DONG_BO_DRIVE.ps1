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
Get-PSDrive -PSProvider FileSystem | Format-Table Name,Root -AutoSize
Write-Host ""
Write-Host "Thu My Drive / Drive cua toi:"
@(
  "G:\My Drive",
  "G:\Drive của tôi",
  "G:\Drive cua toi",
  "$env:USERPROFILE\Google Drive\My Drive",
  "$env:USERPROFILE\GoogleDrive\My Drive"
) | ForEach-Object {
  if (Test-Path -LiteralPath $_) {
    Write-Host ("  FOUND: " + $_)
    Get-ChildItem -LiteralPath $_ -Directory -ErrorAction SilentlyContinue |
      Select-Object -First 15 Name |
      ForEach-Object { Write-Host ("    - " + $_.Name) }
  } else {
    Write-Host ("  miss : " + $_)
  }
}
Write-Host ""
Write-Host "Can thay folder: PKDK_Thuankieu_Pipeline  va  build for Supper Data"
Write-Host "Neu chua thay: mo G:\ -> My Drive, doi Google Drive sync xong, chay lai."
Write-Host ""

Write-Host ""
Write-Host "==== Cap nhat config.local.json + login ===="
& python ".\pipeline\ensure_config.py"

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "Hai may (cung Google Drive) se thay cung folder INBOX/MISSING/ERROR/PROCESSED."
Write-Host "Chi chay HOURLY tren 1 may de tranh import trung."
Write-Host "=========================="
exit $code
