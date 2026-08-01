# Phase B - Step 2: import READY_IMPORT rows into Medinet CLS
# Run ONLY after you approved Preview Excel.
#
# Usage:
#   cd C:\Users\thais\ADMIN
#   git pull origin cursor/drive-hourly-pipeline-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_import.ps1
#
# Dry-run first 5:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_import.ps1 -Limit 5 -DryRun
#
# Real import first 5:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_import.ps1 -Limit 5
#
# Full 369 READY_IMPORT:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_import.ps1

param(
  [int]$Limit = 0,
  [switch]$DryRun,
  [switch]$Force,
  [string]$Preview = ""
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$BuildRoot = "G:\Drive của tôi\build for Supper Data"
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "excel_preview") | Out-Null

if (-not (Test-Path ".\pipeline\config.local.json")) {
  Copy-Item ".\pipeline\config.example.json" ".\pipeline\config.local.json" -Force
}

python -m pip install -q -r .\pipeline\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$env:MEDINET_USER = if ($env:MEDINET_USER) { $env:MEDINET_USER } else { "pkdkthuankieu" }
$env:MEDINET_PASS = if ($env:MEDINET_PASS) { $env:MEDINET_PASS } else { "P@ssw0rd" }

$pyArgs = @(".\pipeline\phase_b_import.py")
if ($Limit -gt 0) { $pyArgs += @("--limit", "$Limit") }
if ($DryRun) { $pyArgs += "--dry-run" }
if ($Force) { $pyArgs += "--force" }
if ($Preview -ne "") { $pyArgs += @("--preview", $Preview) }

$log = Join-Path $BuildRoot ("logs\phase_b_import-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
Write-Host "Running: python $($pyArgs -join ' ')"
Write-Host "Log: $log"

$out = & python @pyArgs 2>&1
$out | Tee-Object -FilePath $log
$code = $LASTEXITCODE
Write-Host "Exit code: $code"
Write-Host "Result Excel in: $BuildRoot\excel_preview\CLS_import_result_*.xlsx"
if ($code -ne 0) { exit $code }
