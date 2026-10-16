# BAT_LAI_DIEN_WEB -> QUET_GAP_VA_BAT_HOURLY (quet gap TTHC + bat hourly)
# ASCII-only.
$ErrorActionPreference = "Continue"
$Main = Join-Path $PSScriptRoot "QUET_GAP_VA_BAT_HOURLY.ps1"
if (-not (Test-Path -LiteralPath $Main)) {
  Write-Host "Thieu QUET_GAP_VA_BAT_HOURLY.ps1 - git reset --hard origin/cursor/hourly-flash-fix-df0f"
  exit 3
}
& powershell -NoProfile -ExecutionPolicy Bypass -File $Main
exit $LASTEXITCODE
