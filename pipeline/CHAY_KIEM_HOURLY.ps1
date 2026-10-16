# ============================================================
# CHAY_KIEM_HOURLY.ps1 - chan doan nhanh vi sao hourly "nhay roi tat"
# ASCII-only Windows PowerShell 5.1
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_KIEM_HOURLY.ps1
#
# Doc ket qua:
#   State=Disabled                 -> da TAT nhieu ngay (BAT_LAI / install)
#   duration_s < 15 + abort=g_drive -> moi gio thoat som (mo Drive)
#   abort=another_instance / lock  -> clear locks + Queue
#   duration_s hang phut + exit=0  -> hourly OK; MISSING dung = no TTHC
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$TaskName = "PKDK_Hourly_Sync"
$LockDir = Join-Path $Repo "pipeline\work\locks"
$LocalHb = Join-Path $Repo "pipeline\work\logs\LAST_HOURLY_OK.txt"
$build = $null

Write-Host "############################################################"
Write-Host "#  KIEM HOURLY - may A                                      #"
Write-Host "############################################################"
Write-Host ("Repo: " + $Repo)
Write-Host ("Now : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Write-Host ""

Write-Host "==== 1) Task Scheduler ===="
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
  Write-Host "FAIL: Task khong ton tai: $TaskName"
  Write-Host "  -> powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1"
} else {
  $info = Get-ScheduledTaskInfo -TaskName $TaskName
  Write-Host ("TaskName        : " + $task.TaskName)
  Write-Host ("State           : " + $task.State)
  Write-Host ("LastRunTime     : " + $info.LastRunTime)
  Write-Host ("NextRunTime     : " + $info.NextRunTime)
  Write-Host ("LastTaskResult  : " + $info.LastTaskResult)
  try {
    Write-Host ("NumberOfMissedRuns: " + $info.NumberOfMissedRuns)
  } catch {}
  if ($task.State -eq "Disabled") {
    Write-Host "!! Hourly DISABLED - day la ly do INBOX/MISSING khong giam nhieu ngay."
    Write-Host "   Fix: powershell -ExecutionPolicy Bypass -File .\pipeline\BAT_LAI_HOURLY.ps1"
  }
}

Write-Host ""
Write-Host "==== 2) assert G: ===="
& python ".\pipeline\assert_g_pipeline.py"
$gCode = $LASTEXITCODE
if ($gCode -ne 0) {
  Write-Host "!! G: abort - moi gio hourly se nhay roi tat (exit=2)."
}

Write-Host ""
Write-Host "==== 3) Counts ===="
& python ".\pipeline\print_counts.py"

Write-Host ""
Write-Host "==== 4) Heartbeat LAST_HOURLY_OK ===="
$hbCandidates = @($LocalHb)
try {
  $br = Join-Path $env:TEMP "pkdk_build_root.txt"
  & python ".\pipeline\resolve_build_root.py" --out "$br" 2>$null | Out-Null
  if (Test-Path -LiteralPath $br) {
    $build = (Get-Content -LiteralPath $br -Encoding UTF8 -Raw).Trim()
    $hbCandidates += (Join-Path $build "logs\LAST_HOURLY_OK.txt")
  }
} catch {}

$foundHb = $false
foreach ($p in $hbCandidates) {
  if (Test-Path -LiteralPath $p) {
    $foundHb = $true
    $item = Get-Item -LiteralPath $p
    Write-Host ("File: " + $p)
    Write-Host ("Age : {0:N1} minutes" -f ((Get-Date) - $item.LastWriteTime).TotalMinutes)
    Get-Content -LiteralPath $p -Encoding UTF8
    Write-Host "---"
  }
}
if (-not $foundHb) {
  Write-Host "Khong thay LAST_HOURLY_OK.txt - hourly co the chua chay hoac ghi heartbeat fail."
}

Write-Host ""
Write-Host "==== 5) Locks / python ===="
if (Test-Path -LiteralPath $LockDir) {
  $locks = @(Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -ErrorAction SilentlyContinue)
  if ($locks.Count -eq 0) {
    Write-Host "Khong co file .lock"
  }
  foreach ($lk in $locks) {
    $ageH = ((Get-Date) - $lk.LastWriteTime).TotalHours
    Write-Host ("LOCK {0} age_h={1:N2} size={2}" -f $lk.Name, $ageH, $lk.Length)
    try { Get-Content -LiteralPath $lk.FullName -TotalCount 3 } catch {}
  }
} else {
  Write-Host "Khong co thu muc locks."
}
Get-Process python -ErrorAction SilentlyContinue |
  Format-Table Id, StartTime, CPU -AutoSize

Write-Host ""
Write-Host "==== 6) Log hourly moi nhat ===="
$logDirs = @((Join-Path $Repo "pipeline\work\logs"))
if ($build) { $logDirs += (Join-Path $build "logs") }
Get-ChildItem -Path $logDirs -Filter "hourly*.log" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 6 FullName, LastWriteTime, Length |
  Format-Table -AutoSize

Write-Host ""
Write-Host "==== GOI Y KHOI PHUC (neu nhay roi tat nhieu ngay) ===="
Write-Host "  0) abort=cases_csv_encoding -> python .\pipeline\repair_cases_encoding.py"
Write-Host "  1) Mo Google Drive Desktop, doi assert_g_pipeline.py = 0"
Write-Host "  2) Stop-Process python -Force  (neu khong co tong hop dang chay)"
Write-Host "  3) Remove-Item .\pipeline\work\locks\*.lock -Force"
Write-Host "  4) powershell -ExecutionPolicy Bypass -File .\pipeline\BAT_LAI_HOURLY.ps1"
Write-Host "  5) powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1"
Write-Host "  6) powershell -ExecutionPolicy Bypass -File .\pipeline\run_hourly.ps1"
Write-Host "     -> duration_s phai hang PHUT, khong phai 1-3 giay"
Write-Host "############################################################"
exit 0
