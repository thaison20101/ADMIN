# Phase B - Step 1: parse all INBOX PDFs → Excel preview on Drive build folder
# Usage:
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_preview.ps1
# Optional test first 20 files:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_preview.ps1 -Limit 20

param(
  [int]$Limit = 0,
  [switch]$SkipMedinet
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$BuildRoot = "G:\Drive của tôi\build for Supper Data"
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "logs") | Out-Null

# Ensure deps
python -m pip install -q -r .\pipeline\requirements.txt

$env:MEDINET_USER = if ($env:MEDINET_USER) { $env:MEDINET_USER } else { "pkdkthuankieu" }
$env:MEDINET_PASS = if ($env:MEDINET_PASS) { $env:MEDINET_PASS } else { "P@ssw0rd" }

$argsList = @()
if ($Limit -gt 0) { $argsList += @("--limit", "$Limit") }
if ($SkipMedinet) { $argsList += "--skip-medinet" }

$log = Join-Path $BuildRoot ("logs\phase_b_preview-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
Write-Host "Running phase_b_preview.py ..."
python .\pipeline\phase_b_preview.py @argsList 2>&1 | Tee-Object -FilePath $log
Write-Host "Log: $log"
Write-Host "Open Excel in: $BuildRoot\excel_preview"
