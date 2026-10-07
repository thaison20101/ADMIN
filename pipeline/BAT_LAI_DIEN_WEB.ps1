# ============================================================
# BAT LAI DIEN WEB -> CHAY_LAI_NHU_TRUOC (hourly luon ON)
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

$Main = Join-Path $PSScriptRoot "CHAY_LAI_NHU_TRUOC.ps1"
if (-not (Test-Path -LiteralPath $Main)) {
  Write-Host "Thieu CHAY_LAI_NHU_TRUOC.ps1 - keo tip:"
  Write-Host "  git fetch origin"
  Write-Host "  git checkout cursor/hourly-flash-fix-df0f"
  Write-Host "  git reset --hard origin/cursor/hourly-flash-fix-df0f"
  exit 3
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $Main
exit $LASTEXITCODE
