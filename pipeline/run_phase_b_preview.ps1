# Phase B - Step 1: parse all INBOX PDFs -> Excel preview on Drive build folder
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

if (-not (Test-Path ".\pipeline\config.local.json")) {
  Copy-Item ".\pipeline\config.example.json" ".\pipeline\config.local.json" -Force
  Write-Host "Created pipeline\config.local.json from example. Check local_sync_root if needed."
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
Ensure-Dir (Join-Path $BuildRoot "missing_or_updated") | Out-Null

$LocalLogDir = Join-Path $Repo "pipeline\work\logs"
Ensure-Dir $LocalLogDir | Out-Null
if ($logDirOk) {
  $log = Join-Path $BuildRoot ("logs\phase_b_preview-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
} else {
  $log = Join-Path $LocalLogDir ("phase_b_preview-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
}

python -m pip install -q -r .\pipeline\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$env:MEDINET_USER = if ($env:MEDINET_USER) { $env:MEDINET_USER } else { "pkdkthuankieu" }
$env:MEDINET_PASS = if ($env:MEDINET_PASS) { $env:MEDINET_PASS } else { "P@ssw0rd" }

$pyArgs = @(".\pipeline\phase_b_preview.py")
if ($Limit -gt 0) { $pyArgs += @("--limit", "$Limit") }
if ($SkipMedinet) { $pyArgs += "--skip-medinet" }

Write-Host "BuildRoot: $BuildRoot"
Write-Host "Running: python $($pyArgs -join ' ')"
Write-Host "Log: $log"

$out = & python @pyArgs 2>&1
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host $_ }
try {
  $out | Out-File -FilePath $log -Encoding utf8
} catch {
  $fallback = Join-Path $LocalLogDir ("phase_b_preview-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
  Write-Host "WARN: cannot write log to $log ; fallback $fallback"
  try { $out | Out-File -FilePath $fallback -Encoding utf8 } catch {}
}

Write-Host "Exit code: $code"
Write-Host "Open Excel in: $BuildRoot\excel_preview"
if ($code -ne 0) { exit $code }
