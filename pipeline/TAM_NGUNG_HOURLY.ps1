# ============================================================
# TAM NGUNG hourly PKDK_Hourly_Sync (may A)
# ASCII-only for Windows PowerShell 5.1
# ============================================================

$ErrorActionPreference = "Continue"
$TaskName = "PKDK_Hourly_Sync"

Write-Host "==== TAM NGUNG $TaskName ===="

try {
  Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
  Get-ScheduledTaskInfo -TaskName $TaskName | Format-List LastRunTime, NextRunTime, LastTaskResult
} catch {
  Write-Host "Task chua cai hoac khong thay: $TaskName"
  exit 0
}

try {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Write-Host "OK: Stop-ScheduledTask"
} catch {}

$ok = $false
try {
  Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
  Write-Host "OK: Disable-ScheduledTask"
  $ok = $true
} catch {
  Write-Host ("WARN Disable: " + $_.Exception.Message)
}

if (-not $ok) {
  $p = Start-Process -FilePath "schtasks.exe" -ArgumentList @("/Change", "/TN", $TaskName, "/DISABLE") -Wait -PassThru -NoNewWindow
  if ($p.ExitCode -eq 0) {
    Write-Host "OK: schtasks DISABLED"
    $ok = $true
  } else {
    Write-Host "FAIL: can PowerShell Run as Administrator"
    exit 1
  }
}

Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
Write-Host "Hourly dang TAT."
exit 0
