# Install Windows Task Scheduler job: run pipeline every 1 hour.
# Run in PowerShell:
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1

$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $PSScriptRoot "run_hourly.ps1"
$TaskName = "PKDK_Hourly_Sync"
$BuildRoot = "G:\Drive của tôi\build for Supper Data"

if (-not (Test-Path $Runner)) {
  throw "Missing runner: $Runner"
}

# Ensure build output folder exists
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "excel_preview") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot "missing_or_updated") | Out-Null

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" `
  -WorkingDirectory $Repo

# Start in 2 minutes, repeat every 1 hour indefinitely
$start = (Get-Date).AddMinutes(2)
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# Replace if exists
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "OK: Scheduled task created: $TaskName"
Write-Host "Repo: $Repo"
Write-Host "Runner: $Runner"
Write-Host "Build folder: $BuildRoot"
Write-Host "First run around: $start"
Write-Host ""
Write-Host "Check task:"
Write-Host "  Get-ScheduledTask -TaskName $TaskName | Format-List"
Write-Host "Run once now:"
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
