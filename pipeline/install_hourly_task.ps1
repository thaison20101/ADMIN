# Install Windows Task Scheduler: PKDK_Hourly_Sync moi 1 gio.
# ASCII-only. NO console flash: runs via wscript + run_hourly_hidden.vbs
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1
#   powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1 -NoStart
#
# Can: laptop BAT + da dang nhap Windows + Google Drive sync G:\

param(
  [switch]$NoStart
)

$ErrorActionPreference = "Continue"

$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$RunnerPs1 = Join-Path $PSScriptRoot "run_hourly.ps1"
$RunnerVbs = Join-Path $PSScriptRoot "run_hourly_hidden.vbs"
$TaskName = "PKDK_Hourly_Sync"

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python

if (-not (Test-Path -LiteralPath $RunnerPs1)) {
  throw "Missing runner: $RunnerPs1"
}
if (-not (Test-Path -LiteralPath $RunnerVbs)) {
  throw "Missing hidden wrapper: $RunnerVbs"
}

$buildRootFile = Join-Path $env:TEMP "pkdk_build_root.txt"
& $Python ".\pipeline\resolve_build_root.py" --out "$buildRootFile" | Out-Null
if (Test-Path -LiteralPath $buildRootFile) {
  $BuildRoot = (Get-Content -LiteralPath $buildRootFile -Encoding UTF8 -Raw).Trim()
} else {
  $BuildRoot = Join-Path $Repo "pipeline\work\build"
}

foreach ($sub in @("logs", "excel_preview", "missing_or_updated", "cases_snapshot")) {
  try { New-Item -ItemType Directory -Force -Path (Join-Path $BuildRoot $sub) | Out-Null } catch {}
}

$envFile = Join-Path $Repo "pipeline\work\pkdk_python.txt"
try {
  $wd = Split-Path -Parent $envFile
  if (-not (Test-Path -LiteralPath $wd)) { New-Item -ItemType Directory -Force -Path $wd | Out-Null }
  Set-Content -LiteralPath $envFile -Value $Python -Encoding utf8
} catch {}

# Hidden: wscript //B runs VBS which launches powershell -WindowStyle Hidden
$wscript = Join-Path $env:SystemRoot "System32\wscript.exe"
$vbsArgs = '//B //Nologo "' + $RunnerVbs + '"'
$action = New-ScheduledTaskAction -Execute $wscript -Argument $vbsArgs -WorkingDirectory $Repo

$nextHour = (Get-Date).Date.AddHours((Get-Date).Hour).AddHours(1)
$trigger = New-ScheduledTaskTrigger -Daily -At $nextHour
try {
  $rep = (New-ScheduledTaskTrigger -Once -At $nextHour -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
  $trigger.Repetition = $rep
} catch {
  Write-Host "WARN: set Repetition failed, fallback Once trigger"
  $trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
}

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -WakeToRun `
  -MultipleInstances Queue `
  -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
  -RestartCount 2 `
  -RestartInterval (New-TimeSpan -Minutes 5)

# Hidden UI: do not flash a console when the task fires
try {
  $settings.Hidden = $true
} catch {}

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

$registered = $false
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

try {
  if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  }
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
  Write-Host "OK: Registered $TaskName (hidden wscript, no PowerShell flash)"
  $registered = $true
} catch {
  Write-Host ("WARN: Register failed: " + $_.Exception.Message)
  Write-Host "Trying schtasks.exe fallback (hidden powershell)..."
  $trCmd = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $RunnerPs1 + '"'
  $schArgs = @("/Create", "/F", "/TN", $TaskName, "/TR", $trCmd, "/SC", "HOURLY", "/MO", "1", "/RL", "HIGHEST")
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
  Write-Host "=============================================="
  exit 1
}

if ($NoStart) {
  try {
    Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
    Write-Host "OK: Task registered but DISABLED (-NoStart). Use desktop button to start later."
  } catch {
    schtasks.exe /Change /TN $TaskName /DISABLE | Out-Null
    Write-Host "OK: Task DISABLED via schtasks (-NoStart)"
  }
} else {
  try {
    Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    Write-Host "OK: Start-ScheduledTask $TaskName (hidden, no flash)"
  } catch {
    Write-Host ("WARN: khong Start duoc task: " + $_)
  }
}

Write-Host ("OK: Task: " + $TaskName)
Write-Host ("Repo: " + $Repo)
Write-Host ("Hidden runner: " + $RunnerVbs)
Write-Host ("Python: " + $Python)
Write-Host "Desktop buttons: powershell -File .\pipeline\TAO_NUT_DESKTOP.ps1"
Write-Host "Pause: .\pipeline\TAM_NGUNG_HOURLY.ps1 | Resume: .\pipeline\NUT_BAT_LAI_KHI_CO_INBOX.ps1"
