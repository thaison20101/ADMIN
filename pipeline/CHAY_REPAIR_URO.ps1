# ============================================================
# REPAIR UROBILINOGEN (khong phai hourly_sync)
# Doi 0.2 mg/dL -> ~3.39 umol/L, ghi lai cac ca PROCESSED thieu/sai.
#
#   cd C:\Users\thais\ADMIN
#   git pull origin cursor/drive-hourly-pipeline-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_REPAIR_URO.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }

Write-Host ""
Write-Host "############################################################"
Write-Host "#  DAY LA REPAIR UROBILINOGEN (khong phai Auto cycle)     #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/3 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f

Write-Host "==== 2/3 repair_urobilinogen.py --all ===="
& python ".\pipeline\ensure_config.py"
& python ".\pipeline\repair_urobilinogen.py" --all
$code = $LASTEXITCODE

Write-Host "==== 3/3 check lai PROCESSED ===="
& python ".\pipeline\check_urobilinogen.py" --folder PROCESSED

Write-Host ""
Write-Host "Neu thay dong '========== REPAIR UROBILINOGEN ==========' o tren = da chay dung."
Write-Host "Neu thay 'Auto cycle stats' = ban dang nhin log hourly cu, khong phai script nay."
Write-Host "Xong. Exit=$code"
if ($code -ne 0) { exit $code }
