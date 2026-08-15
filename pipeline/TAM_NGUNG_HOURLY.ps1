# ============================================================
# TAM NGUNG hourly PKDK_Hourly_Sync (may A)
#
# Dung khi dang sua code / test o may B — tranh 2 may import trung.
#
#   powershell -ExecutionPolicy Bypass -File .\pipeline\TAM_NGUNG_HOURLY.ps1
#
# Bat lai sau:
#   powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1
#   (hoac) .\pipeline\BAT_LAI_HOURLY.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$TaskName = "PKDK_Hourly_Sync"

Write-Host "==== TAM NGUNG $TaskName ===="

# Stop neu dang chay
try {
  $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
  Write-Host ("Truoc: State / LastTaskResult xem ben duoi")
  Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
  Get-ScheduledTaskInfo -TaskName $TaskName | Format-List LastRunTime, NextRunTime, LastTaskResult
} catch {
  Write-Host "Task chua cai hoac khong thay: $TaskName"
  Write-Host $_
  exit 0
}

try {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Write-Host "OK: Stop-ScheduledTask (neu dang chay)"
} catch {}

try {
  Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
  Write-Host "OK: Disable-ScheduledTask — hourly DA TAM NGUNG"
} catch {
  Write-Host ("WARN Disable-ScheduledTask: " + $_.Exception.Message)
  Write-Host "Thu schtasks /Change /DISABLE ..."
  $p = Start-Process -FilePath "schtasks.exe" -ArgumentList @("/Change", "/TN", $TaskName, "/DISABLE") -Wait -PassThru -NoNewWindow
  if ($p.ExitCode -eq 0) {
    Write-Host "OK: schtasks DISABLED"
  } else {
    Write-Host "FAIL: can PowerShell Run as Administrator"
    exit 1
  }
}

Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
Write-Host ""
Write-Host "Hourly dang TAT. Sua code o may B an toan (khong bi may A import trung)."
Write-Host "Bat lai: powershell -ExecutionPolicy Bypass -File .\pipeline\BAT_LAI_HOURLY.ps1"
exit 0
