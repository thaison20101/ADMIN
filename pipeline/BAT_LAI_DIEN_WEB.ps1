# ============================================================
# BAT LAI DIEN WEB = goi EP_DIEN_INBOX_NGAY (1 lenh day du)
# ASCII-only.
#
#   cd C:\Users\thais\ADMIN
#   git fetch origin
#   git reset --hard origin/cursor/hourly-flash-fix-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\BAT_LAI_DIEN_WEB.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Ep = Join-Path $PSScriptRoot "EP_DIEN_INBOX_NGAY.ps1"
if (-not (Test-Path -LiteralPath $Ep)) {
  Write-Host "Thieu EP_DIEN_INBOX_NGAY.ps1 - keo tip truoc:"
  Write-Host "  git fetch origin"
  Write-Host "  git checkout cursor/hourly-flash-fix-df0f"
  Write-Host "  git reset --hard origin/cursor/hourly-flash-fix-df0f"
  exit 3
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $Ep
exit $LASTEXITCODE
