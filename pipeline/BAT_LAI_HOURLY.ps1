# ============================================================
# BAT LAI hourly PKDK_Hourly_Sync (sau khi sua xong o may B)
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\BAT_LAI_HOURLY.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$TaskName = "PKDK_Hourly_Sync"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

Write-Host "==== BAT LAI $TaskName ===="

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
  try {
    Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
    Write-Host "OK: Enable-ScheduledTask"
  } catch {
    Write-Host ("WARN Enable: " + $_.Exception.Message)
    $p = Start-Process -FilePath "schtasks.exe" -ArgumentList @("/Change", "/TN", $TaskName, "/ENABLE") -Wait -PassThru -NoNewWindow
    if ($p.ExitCode -ne 0) {
      Write-Host "Enable fail — cai lai task..."
      & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install_hourly_task.ps1")
      exit $LASTEXITCODE
    }
  }
  Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
  Get-ScheduledTaskInfo -TaskName $TaskName | Format-List NextRunTime, LastRunTime
  Write-Host "OK: Hourly DA BAT LAI (chi may A nen chay hourly)."
  exit 0
}

Write-Host "Task chua co — cai moi..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "install_hourly_task.ps1")
exit $LASTEXITCODE
