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

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$BuildRoot = "G:\Drive của tôi\build for Supper Data"
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "excel_preview") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "missing_or_updated") | Out-Null

# Ensure local config exists
if (-not (Test-Path ".\pipeline\config.local.json")) {
  Copy-Item ".\pipeline\config.example.json" ".\pipeline\config.local.json" -Force
  Write-Host "Created pipeline\config.local.json from example. Check local_sync_root if needed."
}

# Ensure deps
python -m pip install -q -r .\pipeline\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$env:MEDINET_USER = if ($env:MEDINET_USER) { $env:MEDINET_USER } else { "pkdkthuankieu" }
$env:MEDINET_PASS = if ($env:MEDINET_PASS) { $env:MEDINET_PASS } else { "P@ssw0rd" }

$pyArgs = @(".\pipeline\phase_b_preview.py")
if ($Limit -gt 0) { $pyArgs += @("--limit", "$Limit") }
if ($SkipMedinet) { $pyArgs += "--skip-medinet" }

$log = Join-Path $BuildRoot ("logs\phase_b_preview-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
Write-Host "Running: python $($pyArgs -join ' ')"
Write-Host "Log: $log"

# Capture stdout+stderr without PowerShell treating Python traceback as terminating error
$out = & python @pyArgs 2>&1
$out | Tee-Object -FilePath $log
$code = $LASTEXITCODE
Write-Host "Exit code: $code"
Write-Host "Open Excel in: $BuildRoot\excel_preview"
if ($code -ne 0) { exit $code }
