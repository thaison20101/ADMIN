# ============================================================
# 2 BOT SONG SONG: INBOX_CLS + MISSING (web chiu duoc)
# Tat hourly luc chay; MAC DINH bat lai hourly khi xong
# (tranh treo nhieu ngay chi nhay Running roi tat).
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_2_BOT_SONG_SONG.ps1
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_2_BOT_SONG_SONG.ps1 -KeepHourlyOff
# ============================================================

param(
  [switch]$KeepHourlyOff
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }
if (-not $env:MEDINET_USER_2) { $env:MEDINET_USER_2 = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS_2) { $env:MEDINET_PASS_2 = "pkdk_Thuankieu#2026" }

$LockDir = Join-Path $Repo "pipeline\work\locks"

Write-Host "==== TAT hourly + xoa lock cu ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
if (Test-Path -LiteralPath $LockDir) {
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "G: fail - van BAT LAI hourly neu khong -KeepHourlyOff"
  if (-not $KeepHourlyOff) {
    & powershell -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
  }
  exit 2
}

Write-Host "==== START 2 BOT ===="
$botInbox = Start-Process -FilePath "python" -ArgumentList @(
  "-u", ".\pipeline\hourly_sync.py", "--bot", "inbox", "--missing-budget", "0"
) -WorkingDirectory $Repo -PassThru -NoNewWindow
$botMissing = Start-Process -FilePath "python" -ArgumentList @(
  "-u", ".\pipeline\hourly_sync.py", "--bot", "missing", "--missing-budget", "2500"
) -WorkingDirectory $Repo -PassThru -NoNewWindow

Write-Host "INBOX  PID=$($botInbox.Id)"
Write-Host "MISSING PID=$($botMissing.Id)"
Wait-Process -Id $botInbox.Id, $botMissing.Id -ErrorAction SilentlyContinue
$code = [Math]::Max($botInbox.ExitCode, $botMissing.ExitCode)
if ($null -eq $code) { $code = 0 }
& python ".\pipeline\print_counts.py"

Write-Host ""
if ($KeepHourlyOff) {
  Write-Host "==== KeepHourlyOff: hourly van TAT - nho chay BAT_LAI_HOURLY.ps1 ===="
} else {
  Write-Host "==== BAT LAI hourly (tranh nhieu ngay khong quet) ===="
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}

exit $code
