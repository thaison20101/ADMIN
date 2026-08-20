# Windows hourly runner for Drive pipeline
# Installed by: .\pipeline\install_hourly_task.ps1  or  .\pipeline\CHAY_MOT_LAN.ps1

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

if (-not (Test-Path ".\pipeline\config.local.json")) {
  Copy-Item ".\pipeline\config.example.json" ".\pipeline\config.local.json" -Force
}

& python ".\pipeline\ensure_config.py" | Out-Null

# Load Medinet login: env -> config.local.json -> defaults
try {
  $credLines = @(& python ".\pipeline\medinet_creds.py" 2>$null)
  if ($credLines.Count -ge 2) {
    $env:MEDINET_USER = [string]$credLines[0]
    $env:MEDINET_PASS = [string]$credLines[1]
  }
} catch {}
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "pkdk_Thuankieu#2026" }

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

if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "pkdk_Thuankieu#2026" }

Write-Host "BuildRoot: $BuildRoot"
Write-Host "Hourly: INBOX_CLS + ERROR; MISSING rematch from CSV (khong list 10k G:)"
Write-Host "  FULL -> PROCESSED | PARTIAL -> ERROR (nhap phan co) | no TTHC -> MISSING"
Write-Host "Ngay kham index: 01/07/2026 -> hom nay (rolling)"
Write-Host "Khop TTHC (rule cu): ho + ten (token cuoi) + nam sinh"
$started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
& python -u ".\pipeline\hourly_sync.py" 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE

# Heartbeat o 2 cho: Drive build + local (de biet task co fire khi G:\ loi)
$ended = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$hb = "started=$started`nended=$ended`nexit=$code`nlog=$log`n"
try {
  $hbPath = Join-Path $BuildRoot "logs\LAST_HOURLY_OK.txt"
  Ensure-Dir (Join-Path $BuildRoot "logs") | Out-Null
  Set-Content -LiteralPath $hbPath -Value $hb -Encoding utf8
} catch {}
try {
  Set-Content -LiteralPath (Join-Path $LocalLogDir "LAST_HOURLY_OK.txt") -Value $hb -Encoding utf8
} catch {}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$snapDir = Join-Path $BuildRoot "cases_snapshot"
if (Ensure-Dir $snapDir) {
  Copy-Item ".\tracking\cases.csv" (Join-Path $snapDir "cases-$stamp.csv") -Force -ErrorAction SilentlyContinue
}

Write-Host "Log: $log"
Write-Host "Exit code: $code"
if ($code -ne 0) { exit $code }
