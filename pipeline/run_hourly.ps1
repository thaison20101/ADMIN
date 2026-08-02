# Windows hourly runner for Drive pipeline
# Installed by: .\pipeline\install_hourly_task.ps1  or  .\pipeline\CHAY_MOT_LAN.ps1

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
}

& python ".\pipeline\ensure_config.py" | Out-Null

$buildRootFile = Join-Path $env:TEMP "pkdk_build_root.txt"
& python ".\pipeline\resolve_build_root.py" --out "$buildRootFile" | Out-Null
if (Test-Path -LiteralPath $buildRootFile) {
  $BuildRoot = (Get-Content -LiteralPath $buildRootFile -Encoding UTF8 -Raw).Trim()
} else {
  $BuildRoot = Join-Path $Repo "pipeline\work\build"
}

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

if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }

Write-Host "BuildRoot: $BuildRoot"
Write-Host "Running hourly_sync.py (UU TIEN INBOX / PDF moi co TTHC) ..."
# Khong --repair full: tranh ton slot vao hang nghin case incomplete
# Van tu bo sung thieu neu notes goi y incomplete (gioi han so luong)
$out = & python ".\pipeline\hourly_sync.py" 2>&1
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host $_ }
try { $out | Out-File -FilePath $log -Encoding utf8 } catch {
  $fallback = Join-Path $LocalLogDir ("hourly-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
  try { $out | Out-File -FilePath $fallback -Encoding utf8 } catch {}
  Write-Host "WARN: log fallback -> $fallback"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$snapDir = Join-Path $BuildRoot "cases_snapshot"
if (Ensure-Dir $snapDir) {
  Copy-Item ".\tracking\cases.csv" (Join-Path $snapDir "cases-$stamp.csv") -Force -ErrorAction SilentlyContinue
}

Write-Host "Log: $log"
Write-Host "Exit code: $code"
if ($code -ne 0) { exit $code }
