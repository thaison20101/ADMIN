# EP_DIEN_INBOX_NGAY -> QUET_GAP_VA_BAT_HOURLY
# ASCII-only.
$ErrorActionPreference = "Continue"
$Main = Join-Path $PSScriptRoot "QUET_GAP_VA_BAT_HOURLY.ps1"
if (-not (Test-Path -LiteralPath $Main)) {
  Write-Host "Thieu QUET_GAP_VA_BAT_HOURLY.ps1 - git reset --hard origin/cursor/hourly-flash-fix-df0f"
  exit 3
}
& powershell -NoProfile -ExecutionPolicy Bypass -File $Main
exit $LASTEXITCODE
