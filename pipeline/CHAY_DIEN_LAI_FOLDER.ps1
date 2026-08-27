# ============================================================
# DIEN LAI CLS TU PDF - khong move
# ASCII-only for Windows PowerShell 5.1
#
# Buoc:
#   1) Tat hourly + xoa lock
#   2) Diem du moi ket qua PDF (trong/ngoai khoang)
#   3) Mac dinh: folder 'first' (uu tien, khong move); fallback Binh Tay 165
#   4) -ToanBo: quet PROCESSED/TK1/TK2/U18/ERROR/INBOX
#   5) -ResumeHourly: bat lai hourly
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DIEN_LAI_FOLDER.ps1
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DIEN_LAI_FOLDER.ps1 -Apply
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DIEN_LAI_FOLDER.ps1 -ToanBo -Apply -ResumeHourly
# ============================================================

param(
  [switch]$Apply,
  [switch]$ToanBo,
  [switch]$ResumeHourly,
  [switch]$SkipPull,
  [string]$Folder = "",
  [int]$Limit = 0
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
$env:MEDINET_USER = "pkdkthuankieu"
$env:MEDINET_PASS = "P@ssw0rd"
$env:MEDINET_USER_2 = "pkdk_Thuankieu"
$env:MEDINET_PASS_2 = "pkdk_Thuankieu#2026"

$Branch = "cursor/don-g-remediation-df0f"
$LockDir = Join-Path $Repo "pipeline\work\locks"

Write-Host "############################################################"
Write-Host "#  DIEN LAI CLS - moi ket qua PDF - khong bo ngoai khoang #"
Write-Host "#  KHONG MOVE PDF                                         #"
Write-Host "############################################################"

# ---- Buoc 1: tat hourly ----
Write-Host ""
Write-Host "==== 1) TAT hourly + xoa lock ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
if (Test-Path -LiteralPath $LockDir) {
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
  Write-Host "OK: cleared locks"
}

if (-not $SkipPull) {
  Write-Host "==== git pull $Branch ===="
  & git pull origin $Branch
}

& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san."
  exit 2
}

$argsPy = @("-u", ".\pipeline\refill_cls_inplace.py")
if ($Apply) { $argsPy += "--apply" }
if ($ToanBo) { $argsPy += "--toan-bo" }
if ($Folder -and $Folder.Trim().Length -gt 0) {
  $argsPy += @("--folder", $Folder.Trim())
}
if ($Limit -gt 0) { $argsPy += @("--limit", "$Limit") }

Write-Host ""
if ($ToanBo) {
  Write-Host "==== Quet TOAN BO - dien thieu, khong move ===="
} else {
  Write-Host "==== Quet folder first (uu tien) / fallback 165 - dien, khong move ===="
}
if (-not $Apply) {
  Write-Host "MODE: DRY-RUN - them -Apply de ghi Medinet"
} else {
  Write-Host "MODE: APPLY"
}

Write-Host ("CMD: python " + ($argsPy -join " "))
& python @argsPy
$code = $LASTEXITCODE

Write-Host ""
Write-Host "Log: pipeline\work\build\logs\REFILL_*.txt (khong Excel lan nay)"

if ($Apply -and $ResumeHourly) {
  Write-Host ""
  Write-Host "==== 5) BAT LAI hourly - dien du + move nhu cu ===="
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}

Write-Host ("Exit=$code")
exit $code
