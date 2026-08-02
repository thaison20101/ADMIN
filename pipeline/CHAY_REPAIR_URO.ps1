# Repair Urobilinogen thieu tren web (doi mg/dL -> umol/L roi import lai)
#
#   cd C:\Users\thais\ADMIN
#   git pull origin cursor/drive-hourly-pipeline-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_REPAIR_URO.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }

Write-Host "==== git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f

Write-Host "==== repair Urobilinogen (doi don vi + ghi web) ===="
& python ".\pipeline\ensure_config.py"
& python ".\pipeline\repair_urobilinogen.py"
$code = $LASTEXITCODE

Write-Host "==== kiem tra lai ===="
& python ".\pipeline\check_urobilinogen.py" --folder PROCESSED

Write-Host "Xong. Exit=$code"
if ($code -ne 0) { exit $code }
