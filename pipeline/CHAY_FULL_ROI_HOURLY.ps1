# ============================================================
# 1 VONG FULL ngay -> BAT hourly (may A, G: offline mirror OK)
# Rule: khop CHINH XAC ho+ten+nam sinh | DIEN CLS tu PDF
# FULL -> PROCESSED/UNDER18 | PARTIAL -> ERROR | no TTHC -> MISSING
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_FULL_ROI_HOURLY.ps1
# ============================================================

param(
  [switch]$SkipPull
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "pkdk_Thuankieu#2026" }

$TaskName = "PKDK_Hourly_Sync"
$Branch = "cursor/drive-hourly-pipeline-df0f"
$FlagFull = Join-Path $Repo "pipeline\work\build\FIRST_FULL_SCAN_DONE.txt"
$LockDir = Join-Path $Repo "pipeline\work\locks"

function Get-Counts {
  $lines = @(& python ".\pipeline\print_counts.py" 2>$null)
  $counts = ($lines | Select-Object -Last 1)
  $parts = @($counts -split "\t")
  $o = @{ inbox = 0; missing = 0; error = 0; processed = 0; under18 = 0; raw = $counts }
  foreach ($p in $parts) {
    if ($p -match "^inbox=(\d+)$") { $o.inbox = [int]$Matches[1] }
    if ($p -match "^missing=(\d+)$") { $o.missing = [int]$Matches[1] }
    if ($p -match "^error=(\d+)$") { $o.error = [int]$Matches[1] }
    if ($p -match "^processed=(\d+)$") { $o.processed = [int]$Matches[1] }
    if ($p -match "^under18=(\d+)$") { $o.under18 = [int]$Matches[1] }
  }
  return $o
}

function Clear-Locks {
  if (-not (Test-Path -LiteralPath $LockDir)) { return }
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  FULL 1 VONG (2 BOT SONG SONG) -> BAT HOURLY NGAY       #"
Write-Host "############################################################"

Write-Host "==== 1/5 TAT hourly ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
Clear-Locks

if (-not $SkipPull) {
  Write-Host "==== 2/5 git pull ($Branch) ===="
  if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
    git fetch origin
    git checkout $Branch
    git pull origin $Branch
  }
}

& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"
& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san."
  exit 2
}

if (Test-Path -LiteralPath $FlagFull) {
  Remove-Item -LiteralPath $FlagFull -Force -ErrorAction SilentlyContinue
}

Write-Host ("COUNTS truoc: {0}" -f (Get-Counts).raw)

Write-Host "==== 3/5 FULL SCAN - 2 BOT SONG SONG (INBOX + MISSING) ===="
$botInbox = Start-Process -FilePath "python" -ArgumentList @(
  "-u", ".\pipeline\hourly_sync.py", "--full-scan", "--repair", "--bot", "inbox"
) -WorkingDirectory $Repo -PassThru -NoNewWindow
$botMissing = Start-Process -FilePath "python" -ArgumentList @(
  "-u", ".\pipeline\hourly_sync.py", "--full-scan", "--repair", "--bot", "missing", "--missing-budget", "2500"
) -WorkingDirectory $Repo -PassThru -NoNewWindow

Write-Host "Bot INBOX  PID=$($botInbox.Id) | Bot MISSING PID=$($botMissing.Id)"
Wait-Process -Id $botInbox.Id, $botMissing.Id -ErrorAction SilentlyContinue
$code = [Math]::Max($botInbox.ExitCode, $botMissing.ExitCode)
if ($null -eq $code) { $code = 0 }

Write-Host ("COUNTS sau full: {0}" -f (Get-Counts).raw)

Write-Host "==== 4/5 BO SUNG Urea/field thieu ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_BO_SUNG_THIEU.ps1"

try {
  $fd = Split-Path -Parent $FlagFull
  if (-not (Test-Path -LiteralPath $fd)) {
    New-Item -ItemType Directory -Force -Path $fd | Out-Null
  }
  Set-Content -LiteralPath $FlagFull -Value ("done=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -Encoding utf8
} catch {}

Write-Host "==== 5/5 BAT HOURLY NGAY ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
try {
  Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
} catch {
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}

& powershell -ExecutionPolicy Bypass -File ".\pipeline\CAP_NHAT_TIEN_DO_SUPER_DATA.ps1"

$final = Get-Counts
Write-Host ""
Write-Host "========== XONG =========="
Write-Host ("COUNTS: {0}" -f $final.raw)
Write-Host "Hourly: INBOX_CLS + MISSING | TTHC chinh xac | DIEN CLS tu PDF"
if ($code -ne 0) { exit $code }
exit 0
