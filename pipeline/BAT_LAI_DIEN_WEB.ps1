# ============================================================
# 1 LENH MAY A: BAT LAI hourly + dien web (INBOX + rematch)
# ASCII-only. Hidden task (khong chop PowerShell).
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\BAT_LAI_DIEN_WEB.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Branch = "cursor/hourly-flash-fix-df0f"
$env:MEDINET_SSL_VERIFY = "0"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python

Write-Host "############################################################"
Write-Host "#  BAT LAI DIEN WEB - hourly ON + chay 1 lan ngay           #"
Write-Host "############################################################"
Write-Host "TK1: pkdkthuankieu / Qlskcd@2026"
Write-Host "TK2: pkdk_Thuankieu (khong doi)"
Write-Host ""

Write-Host "==== 1/5 Keo tip ===="
git fetch origin
git checkout $Branch
git reset --hard ("origin/" + $Branch)
git clean -fd --exclude=pipeline/config.local.json --exclude=pipeline/work --exclude=tracking
$sha = (git rev-parse --short HEAD)
Write-Host ("HEAD=" + $sha)

Write-Host "==== 2/5 SSL + config (pass TK1 moi) ===="
& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_ssl.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: SSL/auth FAIL - kiem tra mang / mat khau Medinet"
  exit 2
}
& $Python ".\pipeline\drive_paths.py"
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san - mo Google Drive Desktop, Available offline"
  exit 2
}

Write-Host "==== 3/5 Cai task HIDDEN + BAT lich ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$inst = $LASTEXITCODE
Write-Host ("install_hourly_task exit=" + $inst)
if ($inst -ne 0) {
  Write-Host "WARN install - thu Enable..."
  & powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}

Write-Host "==== 4/5 Chay 1 lan run_hourly (dien INBOX + rematch MISSING) ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\run_hourly.ps1"
$run = $LASTEXITCODE
Write-Host ("run_hourly exit=" + $run)

Write-Host "==== 5/5 Nut Desktop (tam dung / bat lai sau nay) ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\TAO_NUT_DESKTOP.ps1"

$markDir = Join-Path $Repo "pipeline\work\build\logs"
if (-not (Test-Path -LiteralPath $markDir)) {
  New-Item -ItemType Directory -Force -Path $markDir | Out-Null
}
$mark = @(
  "state=HOURLY_ON"
  ("at=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
  ("head=" + $sha)
  "rules=auto_cycle+run_hourly"
  "action=BAT_LAI_DIEN_WEB"
) -join "`n"
Set-Content -LiteralPath (Join-Path $markDir "HOURLY_PAUSE_STATE.txt") -Value $mark -Encoding utf8

Write-Host ""
Write-Host "############################################################"
Write-Host " XONG. Hourly DANG BAT (an, khong chop)."
Write-Host " INBOX_CLS se duoc dien roi chuyen folder neu co TTHC."
Write-Host " Kiem: powershell -File .\pipeline\KIEM_HOURLY_VA_FOLDER.ps1"
Write-Host "############################################################"
exit $run
