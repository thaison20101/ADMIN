# CHAY_LAI_NHU_TRUOC -> FORCE_DIEN_INBOX (pin pass + dien truc tiep)
# ASCII-only.
$ErrorActionPreference = "Continue"
$Main = Join-Path $PSScriptRoot "FORCE_DIEN_INBOX.ps1"
if (-not (Test-Path -LiteralPath $Main)) {
  Write-Host "Thieu FORCE_DIEN_INBOX.ps1 - git reset --hard origin/cursor/hourly-flash-fix-df0f"
  exit 3
}
& powershell -NoProfile -ExecutionPolicy Bypass -File $Main
exit $LASTEXITCODE
