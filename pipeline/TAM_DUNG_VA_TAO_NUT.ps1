# One command NOW: pause schedule (rules UNCHANGED) + Desktop buttons.
# ASCII-only.
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\TAM_DUNG_VA_TAO_NUT.ps1
#
# Tam dung = chi Disable PKDK_Hourly_Sync.
# Bat lai = cung run_hourly/auto_cycle rule (gap-only, glucose, MCHC/RDW, CCCD).

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

Write-Host "############################################################"
Write-Host "#  TAM DUNG lich quet (GIU rule) + TAO NUT Desktop          #"
Write-Host "############################################################"
Write-Host "Rule van nam trong code: auto_cycle + run_hourly."
Write-Host "Pause chi tat Task Scheduler. Resume = bat lai cung rule."
Write-Host ""

Write-Host "==== 1/3 Cai task HIDDEN (NoStart) ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1" -NoStart
Write-Host ("install exit=" + $LASTEXITCODE)

Write-Host "==== 2/3 Tam dung lich ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\NUT_TAM_DUNG_HOURLY.ps1"

Write-Host "==== 3/3 Tao nut Desktop ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\TAO_NUT_DESKTOP.ps1"

Write-Host ""
Write-Host "XONG."
Write-Host "  - Lich hourly TAT (het chop). Rule quet VAN CON."
Write-Host "  - Desktop 'PKDK - Bat lai khi co INBOX' = mo lai CUNG rule."
Write-Host "  - Desktop 'PKDK - Chay INBOX 1 lan' = 1 lan, lich van TAT."
exit 0
