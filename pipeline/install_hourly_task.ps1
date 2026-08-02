# Install Windows Task Scheduler: chay pipeline moi 1 gio.
# Prefer: .\pipeline\CHAY_MOT_LAN.ps1

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

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" `
  -WorkingDirectory $Repo

# Bat dau sau 1 phut, lap lai moi 1 gio
$start = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $start `
  -RepetitionInterval (New-TimeSpan -Hours 1) `
  -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

# Chay ngay 1 lan (khong can doi 1 gio)
try {
  Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  Write-Host "OK: Da Start-ScheduledTask $TaskName (chay ngay)"
} catch {
  Write-Host "WARN: khong Start duoc task ngay: $_"
  Write-Host "Chay thu tay: powershell -ExecutionPolicy Bypass -File `"$Runner`""
}

Write-Host "OK: Task moi 1 gio: $TaskName"
Write-Host "Repo: $Repo"
Write-Host "Runner: $Runner"
Write-Host "Build folder: $BuildRoot"
Write-Host "Lan lap tiep theo khoang: $start"
Write-Host "Kiem tra: Get-ScheduledTask -TaskName $TaskName | Format-List *"
