# Desktop button: chay INBOX 1 lan, KHONG bat hourly (tam dung van giu)
# ASCII-only.
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\NUT_CHAY_INBOX_1_LAN.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:MEDINET_SSL_VERIFY = "0"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

Write-Host "============================================================"
Write-Host " PKDK - CHAY INBOX 1 LAN (hourly van TAT neu dang dung)"
Write-Host "============================================================"

# Ensure hourly stays off if user paused
$TaskName = "PKDK_Hourly_Sync"
$st = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($st -and $st.State -ne "Disabled") {
  Write-Host "NOTE: Hourly dang BAT. Chi chay 1 lan; khong Disable."
} else {
  Write-Host "Hourly dang TAT / chua cai - chi chay 1 lan tay."
}

& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\run_hourly.ps1"
$code = $LASTEXITCODE
Write-Host ("run_hourly exit=" + $code)
Write-Host "XONG 1 lan. Hourly state khong doi."
Write-Host "============================================================"
exit $code
