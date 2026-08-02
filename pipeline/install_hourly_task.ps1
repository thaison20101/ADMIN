# Install Windows Task Scheduler: chay pipeline moi 1 gio.
# Neu Access denied: mo PowerShell "Run as administrator" roi chay lai file nay.

$ErrorActionPreference = "Continue"

$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$Runner = Join-Path $PSScriptRoot "run_hourly.ps1"
$TaskName = "PKDK_Hourly_Sync"

if (-not (Test-Path $Runner)) {
  throw "Missing runner: $Runner"
}

$buildRootFile = Join-Path $env:TEMP "pkdk_build_root.txt"
& python ".\pipeline\resolve_build_root.py" --out "$buildRootFile" | Out-Null
if (Test-Path -LiteralPath $buildRootFile) {
  $BuildRoot = (Get-Content -LiteralPath $buildRootFile -Encoding UTF8 -Raw).Trim()
} else {
  $BuildRoot = Join-Path $Repo "pipeline\work\build"
}

foreach ($sub in @("logs", "excel_preview", "missing_or_updated", "cases_snapshot")) {
  try { New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot $sub) | Out-Null } catch {}
}

$psArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $Runner + '"'
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs -WorkingDirectory $Repo

$start = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$registered = $false
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

try {
  if ($existing) {
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -ErrorAction Stop | Out-Null
    Write-Host "OK: Updated existing task $TaskName"
  } else {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
    Write-Host "OK: Registered new task $TaskName"
  }
  $registered = $true
} catch {
  Write-Host ("WARN: Register/Set failed: " + $_.Exception.Message)
  Write-Host "Trying schtasks.exe fallback..."
  $trCmd = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $Runner + '"'
  $schArgs = @("/Create", "/F", "/TN", $TaskName, "/TR", $trCmd, "/SC", "HOURLY", "/MO", "1", "/RL", "LIMITED")
  $p = Start-Process -FilePath "schtasks.exe" -ArgumentList $schArgs -Wait -PassThru -NoNewWindow
  if ($p.ExitCode -eq 0) {
    $registered = $true
    Write-Host "OK: schtasks created/updated $TaskName"
  } else {
    Write-Host ("WARN: schtasks exit=" + $p.ExitCode)
  }
}

if (-not $registered) {
  Write-Host ""
  Write-Host "========== LOI QUYEN TASK SCHEDULER =========="
  Write-Host "Access denied: can chay PowerShell Run as administrator."
  Write-Host "  cd C:\Users\thais\ADMIN"
  Write-Host "  powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1"
  Write-Host "Import/repair PDF van OK. Chi thieu lich tu dong moi 1 gio."
  Write-Host ("Chay tay: powershell -ExecutionPolicy Bypass -File " + $Runner)
  Write-Host "=============================================="
  exit 1
}

try {
  Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  Write-Host "OK: Da Start-ScheduledTask $TaskName"
} catch {
  Write-Host ("WARN: khong Start duoc task: " + $_)
  Write-Host ("Chay tay: powershell -ExecutionPolicy Bypass -File " + $Runner)
}

Write-Host ("OK: Task moi 1 gio: " + $TaskName)
Write-Host ("Repo: " + $Repo)
Write-Host ("Runner: " + $Runner)
Write-Host ("Build: " + $BuildRoot)
Write-Host ("Kiem tra: Get-ScheduledTask -TaskName " + $TaskName)
