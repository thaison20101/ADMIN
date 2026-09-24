# Desktop button: TAM DUNG hourly (no more PowerShell flash every hour)
# ASCII-only. Window stays open (-NoExit from shortcut).
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\NUT_TAM_DUNG_HOURLY.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

Write-Host "============================================================"
Write-Host " PKDK - TAM DUNG HOURLY"
Write-Host "============================================================"

& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
$code = $LASTEXITCODE

# Also kill any leftover python from a mid-run (safe: only after disable)
Get-Process -Name python*, py* -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host ("  stop leftover PID=" + $_.Id)
  Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

Write-Host ""
if ($code -eq 0) {
  Write-Host "OK: Hourly DA TAM DUNG. Khong con chay moi gio / khong chop tat."
} else {
  Write-Host "WARN: Tam dung co loi (thu Run as Administrator)."
}
Write-Host "Khi co them PDF trong INBOX_CLS: double-click nut 'PKDK - Bat lai khi co INBOX'."
Write-Host "============================================================"
exit $code
