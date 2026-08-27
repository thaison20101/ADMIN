# ============================================================
# DIEN LAI CLS - CHI folder "first" (1 lan) - khong move
# ASCII-only for Windows PowerShell 5.1
#
# Dung toan bo rule moi: parse 10^N / Ghi chu / urine + force Set + verify
# TTHC da day du → chay 1 lan cho folder first.
#
# LENH 1 DONG:
#
#   cd C:\Users\thais\ADMIN; git pull origin cursor/don-g-remediation-df0f; powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DIEN_LAI_FIRST.ps1 -Apply -ResumeHourly
#
# Dry-run:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DIEN_LAI_FIRST.ps1
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
$FolderName = "first"

Write-Host "############################################################"
Write-Host "#  DIEN LAI CLS - CHI folder first - KHONG MOVE           #"
Write-Host "#  Rule moi: 10^N / Ghi chu / urine + Set verify          #"
Write-Host "############################################################"

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

$argsPy = @("-u", ".\pipeline\refill_cls_inplace.py", "--folder", $FolderName)
if ($Apply) { $argsPy += "--apply" }
if ($Limit -gt 0) { $argsPy += @("--limit", "$Limit") }

Write-Host ""
Write-Host "==== Quet CHI folder first - dien CLS, khong move ===="
if (-not $Apply) {
  Write-Host "MODE: DRY-RUN - them -Apply de ghi Medinet"
} else {
  Write-Host "MODE: APPLY"
}

Write-Host ("CMD: python " + ($argsPy -join " "))
& python @argsPy
$code = $LASTEXITCODE
if ($null -eq $code) { $code = -1 }

Write-Host ""
Write-Host "Log: pipeline\work\build\logs\REFILL_*.txt (khong Excel lan nay)"

if ($code -ne 0) {
  Write-Host ""
  Write-Host "!!!! Python Exit=$code - CHUA XONG folder first."
  Write-Host "!!!! Exit=-1 thuong la crash/kill/OOM."
}

if ($Apply -and $ResumeHourly -and $code -eq 0) {
  Write-Host ""
  Write-Host "==== BAT LAI hourly ===="
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
} elseif ($Apply -and $ResumeHourly -and $code -ne 0) {
  Write-Host ""
  Write-Host "==== BO QUA bat hourly vi refill Exit=$code ===="
}

Write-Host ("Exit=$code")
exit $code
