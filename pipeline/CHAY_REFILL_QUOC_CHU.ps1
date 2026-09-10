# Force refill form VONG QUOC CHU (MCHC/RDW) — may A
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_REFILL_QUOC_CHU.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:MEDINET_SSL_VERIFY = "0"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython

Write-Host "=== REFILL QUOC CHU ==="
& $Python ".\pipeline\refill_one_patient.py" @args
exit $LASTEXITCODE
