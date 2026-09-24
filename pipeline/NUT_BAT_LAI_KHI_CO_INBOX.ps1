# Desktop button: BAT LAI hourly - CUNG rule quet/dien nhu truoc khi tam dung.
# Chi bat lai lich; KHONG doi parse / gap-only / glucose / match / route.
# ASCII-only.
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\NUT_BAT_LAI_KHI_CO_INBOX.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$Branch = "cursor/hourly-flash-fix-df0f"
$env:MEDINET_SSL_VERIFY = "0"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

Write-Host "============================================================"
Write-Host " PKDK - BAT LAI KHI CO INBOX"
Write-Host " Rule quet/dien GIU NGUYEN (giong luc truoc khi tam dung):"
Write-Host "   - Parse MCHC/RDW + gap-only"
Write-Host "   - Duong mau bat ky / luc doi dung o"
Write-Host "   - Match ho+ten + nam/SDT/CCCD; CCCD+ten lech -> CCCD/"
Write-Host "   - LoaiKham dinh ky; verify; INBOX + rematch MISSING/TK"
Write-Host "============================================================"

# Keo tip de chac rule moi van con tren may A
Write-Host "==== Keo code tip (cung branch rule) ===="
git fetch origin
git checkout $Branch
git reset --hard ("origin/" + $Branch)
$sha = (git rev-parse --short HEAD)
Write-Host ("HEAD=" + $sha)

Write-Host ""
Write-Host "==== Cai task HIDDEN + BAT lich (khong chop) ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$inst = $LASTEXITCODE
Write-Host ("install_hourly_task exit=" + $inst)

if ($inst -ne 0) {
  Write-Host "WARN install fail - thu Enable task cu..."
  & powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}

Write-Host ""
Write-Host "==== Chay 1 lan run_hourly (cung auto_cycle rule) ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\run_hourly.ps1"
$run = $LASTEXITCODE
Write-Host ("run_hourly exit=" + $run)

# Ghi marker de biet dang BAT + rule tip
$markDir = Join-Path $Repo "pipeline\work\build\logs"
if (-not (Test-Path -LiteralPath $markDir)) {
  New-Item -ItemType Directory -Force -Path $markDir | Out-Null
}
$mark = @(
  "state=HOURLY_ON"
  ("at=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
  ("head=" + $sha)
  "rules=auto_cycle+run_hourly (gap-only, glucose bat ky, MCHC/RDW, CCCD folder)"
  "note=tam dung chi Disable task; bat lai khong doi rule"
) -join "`n"
Set-Content -LiteralPath (Join-Path $markDir "HOURLY_PAUSE_STATE.txt") -Value $mark -Encoding utf8

Write-Host ""
Write-Host "OK: Hourly DA BAT LAI - cung rule quet nhu cu."
Write-Host "PDF moi -> INBOX_CLS. Task chay an (khong chop)."
Write-Host "Tam dung: nut 'PKDK - Tam dung hourly'."
Write-Host "============================================================"
exit $run
