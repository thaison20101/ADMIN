# EP_DIEN_INBOX_NGAY -> CHAY_LAI_NHU_TRUOC (hourly ON, nhu truoc tam dung)
# ASCII-only.
$ErrorActionPreference = "Continue"
$Main = Join-Path $PSScriptRoot "CHAY_LAI_NHU_TRUOC.ps1"
if (-not (Test-Path -LiteralPath $Main)) {
  Write-Host "Thieu CHAY_LAI_NHU_TRUOC.ps1 - git reset --hard origin/cursor/hourly-flash-fix-df0f"
  exit 3
}
& powershell -NoProfile -ExecutionPolicy Bypass -File $Main
exit $LASTEXITCODE
