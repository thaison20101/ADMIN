# ============================================================
# DON G - quet 5 folder, match TTHC 2 TK, dien CLS, move, dedupe
#
# TRUOC KHI CHAY:
#   1) Tam dung Google Drive sync (Pause syncing)
#   2) cd C:\Users\thais\ADMIN
#
# Dry-run (mac dinh - khong ghi G:):
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DON_G.ps1
#
# Thuc thi + bat lai hourly:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DON_G.ps1 -Apply -ResumeHourly
# ============================================================

param(
  [switch]$Apply,
  [switch]$ResumeHourly,
  [switch]$SkipPull,
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
Write-Host "#  DON G: PROCESSED->MISSING->U18->TK1->TK2               #"
Write-Host "#  Rule: filled_ok>=2 moi PROCESSED | dedupe 1 folder/case #"
Write-Host "############################################################"
Write-Host ""
Write-Host "CANH BAO: Tam dung Google Drive sync truoc khi -Apply!"
Write-Host "  Google Drive tray -> Pause syncing -> Until I resume"
Write-Host ""

if (-not $SkipPull) {
  Write-Host "==== git pull $Branch ===="
  & git pull origin $Branch
  if ($LASTEXITCODE -ne 0) {
    Write-Host "WARN: git pull fail - kiem tra mang / branch"
  }
}

Write-Host "==== TAT hourly + xoa lock ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
if (Test-Path -LiteralPath $LockDir) {
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san."
  exit 2
}

$argsPy = @("-u", ".\pipeline\pdf_check\remediate_g.py")
if ($Apply) { $argsPy += "--apply" }
if ($Limit -gt 0) { $argsPy += @("--limit", "$Limit") }

if (-not $Apply) {
  Write-Host ""
  Write-Host "==== DRY-RUN (khong ghi G:, khong insert CLS) ===="
} else {
  Write-Host ""
  Write-Host "==== APPLY (ghi G: + Medinet + dedupe) ===="
}

Write-Host ("CMD: python " + ($argsPy -join " "))
& python @argsPy
$code = $LASTEXITCODE

Write-Host ""
Write-Host "Excel: pipeline\work\build\excel_preview\REMEDIATE_*.xlsx"
Write-Host "Log:   pipeline\work\build\logs\REMEDIATE_*.txt"

if ($Apply -and $ResumeHourly) {
  Write-Host ""
  Write-Host "==== BAT LAI hourly (sau khi Resume Google Drive sync) ===="
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}

Write-Host ("Exit=$code")
exit $code
