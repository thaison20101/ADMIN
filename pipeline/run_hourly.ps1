# Windows hourly runner for Drive pipeline
# Install once: .\pipeline\install_hourly_task.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

if (-not (Test-Path ".\pipeline\config.local.json")) {
  Copy-Item ".\pipeline\config.example.json" ".\pipeline\config.local.json" -Force
}

$BuildRoot = & python -c "import json; from pathlib import Path; p=Path('pipeline/config.local.json'); p=p if p.exists() else Path('pipeline/config.example.json'); print(json.loads(p.read_text(encoding='utf-8-sig')).get('drive',{}).get('build_root') or r'G:\Drive cua toi\build for Supper Data')"
$BuildRoot = ($BuildRoot | Out-String).Trim()
if (-not $BuildRoot) { $BuildRoot = Join-Path $Repo "pipeline\work\build" }

function Ensure-Dir([string]$Path) {
  try { New-Item -ItemType Directory -Force -Path $Path | Out-Null; return $true }
  catch { Write-Host "WARN: cannot create $Path"; return $false }
}

$LocalLogDir = Join-Path $Repo "pipeline\work\logs"
Ensure-Dir $LocalLogDir | Out-Null
$logDirOk = Ensure-Dir (Join-Path $BuildRoot "logs")
Ensure-Dir (Join-Path $BuildRoot "excel_preview") | Out-Null
Ensure-Dir (Join-Path $BuildRoot "missing_or_updated") | Out-Null
Ensure-Dir (Join-Path $BuildRoot "cases_snapshot") | Out-Null

if ($logDirOk) {
  $log = Join-Path $BuildRoot ("logs\hourly-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
} else {
  $log = Join-Path $LocalLogDir ("hourly-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
}

Write-Host "BuildRoot: $BuildRoot"
Write-Host "Running hourly_sync.py ..."
$out = & python ".\pipeline\hourly_sync.py" 2>&1
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host $_ }
try { $out | Out-File -FilePath $log -Encoding utf8 } catch {
  $fallback = Join-Path $LocalLogDir ("hourly-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
  try { $out | Out-File -FilePath $fallback -Encoding utf8 } catch {}
  Write-Host "WARN: log fallback -> $fallback"
}

# Snapshot tracking ledger into Drive build folder
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$snapDir = Join-Path $BuildRoot "cases_snapshot"
if (Ensure-Dir $snapDir) {
  Copy-Item ".\tracking\cases.csv" (Join-Path $snapDir "cases-$stamp.csv") -Force
}

Write-Host "Log: $log"
Write-Host "Exit code: $code"
if ($code -ne 0) { exit $code }
