# ============================================================
# PDF CHECK - quet toan bo PDF, doi chieu TTHC 2 TK + CLS
# KHONG import CLS, KHONG move file, KHONG ghi G:
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_PDF_CHECK.ps1
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_PDF_CHECK.ps1 -SkipCls
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_PDF_CHECK.ps1 -Limit 200
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_PDF_CHECK.ps1 -Folders "PROCESSED,MISSING"
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_PDF_CHECK.ps1 -Hash
# ============================================================

param(
  [switch]$SkipCls,
  [switch]$Hash,
  [int]$Limit = 0,
  [string]$Folders = ""
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
# 2 TK Medinet (cung hardcode pipeline/medinet_creds.py + hourly) - luon dung 2 TK nay
$env:MEDINET_USER = "pkdkthuankieu"
$env:MEDINET_PASS = "P@ssw0rd"
$env:MEDINET_USER_2 = "pkdk_Thuankieu"
$env:MEDINET_PASS_2 = "pkdk_Thuankieu#2026"

Write-Host "############################################################"
Write-Host "#  PDF CHECK: TTHC 2 TK + CLS + DUP (KHONG IMPORT)         #"
Write-Host "############################################################"
Write-Host "TK1: pkdkthuankieu | TK2: pkdk_Thuankieu (hardcoded)"
Write-Host "Rule match = resolve_tthc_matches (ho+ten DAY DU + nam/SDT/CCCD)"
Write-Host "Excel: pipeline\work\build\excel_preview\PDF_CHECK_*.xlsx"

& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san."
  exit 2
}

$argsPy = @("-u", ".\pipeline\pdf_check\run_check.py")
if ($SkipCls) { $argsPy += "--skip-cls" }
if ($Hash) { $argsPy += "--hash" }
if ($Limit -gt 0) { $argsPy += @("--limit", "$Limit") }
if ($Folders -and $Folders.Trim().Length -gt 0) {
  $argsPy += @("--folders", $Folders.Trim())
}

Write-Host ("CMD: python " + ($argsPy -join " "))
& python @argsPy
$code = $LASTEXITCODE
Write-Host ("Exit=$code")
exit $code
