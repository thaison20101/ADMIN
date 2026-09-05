# ============================================================
# BAT LAI hourly PKDK_Hourly_Sync
# ASCII-only for Windows PowerShell 5.1
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\BAT_LAI_HOURLY.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$TaskName = "PKDK_Hourly_Sync"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

Write-Host "==== BAT LAI $TaskName ===="

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $existing) {
  Write-Host "Task chua co - cai moi..."
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install_hourly_task.ps1")
  exit $LASTEXITCODE
}

$ok = $false
try {
  Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
  Write-Host "OK: Enable-ScheduledTask"
  $ok = $true
} catch {
  Write-Host ("WARN Enable: " + $_.Exception.Message)
}

if (-not $ok) {
  $p = Start-Process -FilePath "schtasks.exe" -ArgumentList @("/Change", "/TN", $TaskName, "/ENABLE") -Wait -PassThru -NoNewWindow
  if ($p.ExitCode -eq 0) {
    Write-Host "OK: schtasks ENABLE"
    $ok = $true
  }
}

if (-not $ok) {
  Write-Host "Enable fail - cai lai task..."
  & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install_hourly_task.ps1")
  exit $LASTEXITCODE
}

Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
Get-ScheduledTaskInfo -TaskName $TaskName | Format-List NextRunTime, LastRunTime
Write-Host "OK: Hourly DA BAT LAI (chi may A nen chay hourly)."
exit 0
