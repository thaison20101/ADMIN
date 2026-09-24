# Desktop button: BAT LAI hourly after more PDFs are in INBOX_CLS
# ASCII-only. Re-installs hidden (no flash) task, enables, runs 1 pass.
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\NUT_BAT_LAI_KHI_CO_INBOX.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:MEDINET_SSL_VERIFY = "0"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

Write-Host "============================================================"
Write-Host " PKDK - BAT LAI KHI CO INBOX"
Write-Host "============================================================"
Write-Host "1) Cai lai task HIDDEN (khong chop PowerShell)"
Write-Host "2) Bat hourly"
Write-Host "3) Chay 1 lan INBOX + rematch ngay"
Write-Host ""

# Re-register with hidden VBS (fixes old flashing task), then enable+start
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$inst = $LASTEXITCODE
Write-Host ("install_hourly_task exit=" + $inst)

if ($inst -ne 0) {
  Write-Host "WARN install fail - thu Enable task cu..."
  & powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}

Write-Host ""
Write-Host "Chay 1 lan run_hourly (cua so nay - de xem log; task gio se an)..."
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\run_hourly.ps1"
$run = $LASTEXITCODE
Write-Host ("run_hourly exit=" + $run)

Write-Host ""
Write-Host "OK: Hourly DA BAT. Task chay an (khong chop). PDF moi -> INBOX_CLS."
Write-Host "Tam dung lai: nut 'PKDK - Tam dung hourly'."
Write-Host "============================================================"
exit $run
