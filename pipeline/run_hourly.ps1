# Windows hourly runner for Drive pipeline
# Schedule this with Task Scheduler every 1 hour.

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

# Optional: activate python if needed
# & "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" ...

$logDir = Join-Path $Repo "pipeline\work"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("hourly-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

Write-Host "Running hourly_sync.py ..."
python ".\pipeline\hourly_sync.py" 2>&1 | Tee-Object -FilePath $log
Write-Host "Log: $log"
