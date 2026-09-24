# One command NOW: stop flashing hourly + create Desktop buttons.
# ASCII-only.
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\TAM_DUNG_VA_TAO_NUT.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

Write-Host "############################################################"
Write-Host "#  TAM DUNG hourly (het chop) + TAO NUT Desktop             #"
Write-Host "############################################################"

# 1) Re-register as HIDDEN so even if someone enables later, no flash
Write-Host "==== 1/3 Cai lai task HIDDEN (khong Start) ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1" -NoStart
Write-Host ("install exit=" + $LASTEXITCODE)

# 2) Force disable + kill leftover
Write-Host "==== 2/3 Tam dung hourly ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\NUT_TAM_DUNG_HOURLY.ps1"

# 3) Desktop buttons
Write-Host "==== 3/3 Tao nut Desktop ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\TAO_NUT_DESKTOP.ps1"

Write-Host ""
Write-Host "XONG."
Write-Host "  - Hourly TAT (khong con chop PowerShell moi gio)."
Write-Host "  - Desktop: 'PKDK - Bat lai khi co INBOX' khi da them PDF."
Write-Host "  - Desktop: 'PKDK - Chay INBOX 1 lan' neu chi muon 1 lan, van de hourly TAT."
exit 0
