# Phase B - Step 1: parse all INBOX PDFs -> Excel preview on Drive build folder
# Usage:
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\run_phase_b_preview.ps1

param(
  [int]$Limit = 0,
  [switch]$SkipMedinet
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

if (-not (Test-Path ".\pipeline\config.local.json")) {
  Copy-Item ".\pipeline\config.example.json" ".\pipeline\config.local.json" -Force
  Write-Host "Created pipeline\config.local.json from example. Check local_sync_root if needed."
}

$buildRootFile = Join-Path $env:TEMP "pkdk_build_root.txt"
& python ".\pipeline\resolve_build_root.py" --out "$buildRootFile" | Out-Null
if (Test-Path -LiteralPath $buildRootFile) {
  $BuildRoot = (Get-Content -LiteralPath $buildRootFile -Encoding UTF8 -Raw).Trim()
} else {
  $BuildRoot = Join-Path $Repo "pipeline\work\build"
}

function Ensure-Dir([string]$Path) {
  try {
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
    return $true
  } catch {
    Write-Host "WARN: cannot create $Path : $($_.Exception.Message)"
    return $false
  }
}

$LocalLogDir = Join-Path $Repo "pipeline\work\logs"
Ensure-Dir $LocalLogDir | Out-Null
$logDirOk = Ensure-Dir (Join-Path $BuildRoot "logs")
Ensure-Dir (Join-Path $BuildRoot "excel_preview") | Out-Null
Ensure-Dir (Join-Path $BuildRoot "missing_or_updated") | Out-Null
if ($logDirOk) {
  $log = Join-Path $BuildRoot ("logs\phase_b_preview-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
} else {
  $log = Join-Path $LocalLogDir ("phase_b_preview-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
}

python -m pip install -q -r .\pipeline\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$env:MEDINET_USER = if ($env:MEDINET_USER) { $env:MEDINET_USER } else { "pkdk_Thuankieu" }
$env:MEDINET_PASS = if ($env:MEDINET_PASS) { $env:MEDINET_PASS } else { "pkdk_Thuankieu#2026" }

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
