# Windows hourly runner for Drive pipeline
# Install once: .\pipeline\install_hourly_task.ps1

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$BuildRoot = "G:\Drive của tôi\build for Supper Data"
$logDir = Join-Path $BuildRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "excel_preview") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "missing_or_updated") | Out-Null

$log = Join-Path $logDir ("hourly-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

Write-Host "Running hourly_sync.py ..."
python ".\pipeline\hourly_sync.py" 2>&1 | Tee-Object -FilePath $log

# Snapshot tracking ledger into Drive build folder
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$snapDir = Join-Path $BuildRoot "cases_snapshot"
New-Item -ItemType Directory -Force -Path $snapDir | Out-Null
Copy-Item ".\tracking\cases.csv" (Join-Path $snapDir "cases-$stamp.csv") -Force

Write-Host "Log: $log"
Write-Host "Snapshot: $snapDir\cases-$stamp.csv"
