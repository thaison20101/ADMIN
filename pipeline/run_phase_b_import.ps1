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
# Full READY_IMPORT:
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

if (-not (Test-Path ".\pipeline\config.local.json")) {
  Copy-Item ".\pipeline\config.example.json" ".\pipeline\config.local.json" -Force
}

# Read build_root from JSON via Python (avoids PowerShell encoding issues with Vietnamese paths)
$BuildRoot = & python -c "import json; from pathlib import Path; p=Path('pipeline/config.local.json'); p=p if p.exists() else Path('pipeline/config.example.json'); print(json.loads(p.read_text(encoding='utf-8-sig')).get('drive',{}).get('build_root') or r'G:\Drive cua toi\build for Supper Data')"
if (-not $BuildRoot) {
  $BuildRoot = Join-Path $Repo "pipeline\work\build"
}
$BuildRoot = $BuildRoot.Trim()

function Ensure-Dir([string]$Path) {
  try {
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
    return $true
  } catch {
    Write-Host "WARN: cannot create $Path : $($_.Exception.Message)"
    return $false
  }
}

$logDirOk = Ensure-Dir (Join-Path $BuildRoot "logs")
Ensure-Dir (Join-Path $BuildRoot "excel_preview") | Out-Null

# Fallback local log dir if Drive path is broken/encoding-mismatched
$LocalLogDir = Join-Path $Repo "pipeline\work\logs"
Ensure-Dir $LocalLogDir | Out-Null
if ($logDirOk) {
  $log = Join-Path $BuildRoot ("logs\phase_b_import-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
} else {
  $log = Join-Path $LocalLogDir ("phase_b_import-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
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

Write-Host "BuildRoot: $BuildRoot"
Write-Host "Running: python $($pyArgs -join ' ')"
Write-Host "Log: $log"

$out = & python @pyArgs 2>&1
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host $_ }
try {
  $out | Out-File -FilePath $log -Encoding utf8
} catch {
  $fallback = Join-Path $LocalLogDir ("phase_b_import-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
  Write-Host "WARN: cannot write log to $log ; fallback $fallback"
  try { $out | Out-File -FilePath $fallback -Encoding utf8 } catch {}
}

Write-Host "Exit code: $code"
Write-Host "Result Excel in: $BuildRoot\excel_preview\CLS_import_result_*.xlsx"
if ($code -ne 0) { exit $code }
