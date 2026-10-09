# ============================================================
# KIEM: hourly BAT/TAT + folder dang quet (theo code tip)
# ASCII-only. Chay tren may A.
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\KIEM_HOURLY_VA_FOLDER.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$TaskName = "PKDK_Hourly_Sync"
$PauseMark = Join-Path $Repo "pipeline\work\build\logs\HOURLY_PAUSE_STATE.txt"
$FlagFull = Join-Path $Repo "pipeline\work\build\FIRST_FULL_SCAN_DONE.txt"
$LocalHb = Join-Path $Repo "pipeline\work\logs\LAST_HOURLY_OK.txt"

Write-Host "############################################################"
Write-Host "#  KIEM HOURLY + FOLDER QUET                                 #"
Write-Host "############################################################"
Write-Host ("Now: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Write-Host ("Repo HEAD: " + (git rev-parse --short HEAD))
Write-Host ""

Write-Host "==== 1) Task Scheduler (co dang BAT?) ===="
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
  Write-Host "Hourly: CHUA CAI task $TaskName"
  Write-Host "  -> Nut Desktop 'Bat lai khi co INBOX' hoac install_hourly_task.ps1"
} else {
  $info = Get-ScheduledTaskInfo -TaskName $TaskName
  Write-Host ("State       : " + $task.State)
  Write-Host ("LastRunTime : " + $info.LastRunTime)
  Write-Host ("NextRunTime : " + $info.NextRunTime)
  Write-Host ("LastResult  : " + $info.LastTaskResult)
  if ($task.State -eq "Disabled") {
    Write-Host "=> Hourly DANG TAT (tam dung). Rule quet van giu trong code."
  } elseif ($task.State -eq "Ready") {
    Write-Host "=> Hourly DANG BAT (cho den NextRunTime)."
  } elseif ($task.State -eq "Running") {
    Write-Host "=> Hourly DANG CHAY bay gio."
  }
}

Write-Host ""
Write-Host "==== 2) Marker tam dung / bat lai ===="
if (Test-Path -LiteralPath $PauseMark) {
  Get-Content -LiteralPath $PauseMark -Encoding utf8
} else {
  Write-Host "(chua co HOURLY_PAUSE_STATE.txt)"
}

Write-Host ""
Write-Host "==== 3) Che do quet (FIRST_FULL_SCAN_DONE?) ===="
if (Test-Path -LiteralPath $FlagFull) {
  Write-Host "FIRST_FULL_SCAN_DONE = CO -> MODE HOURLY NHE:"
  Write-Host "  Bot INBOX  : disk-walk INBOX_CLS"
  Write-Host "  Bot MISSING: rematch CSV MISSING + TK1/TK2 (KHONG list full G: TK)"
  Write-Host "  Khong rglob PROCESSED/ERROR/CCCD moi gio"
} else {
  Write-Host "FIRST_FULL_SCAN_DONE = CHUA -> lan hourly tiep theo = FULL SCAN:"
  Write-Host "  INBOX_CLS + ERROR + MISSING(CSV) + PROCESSED + UNDER 18 + TK1 + TK2 + CCCD"
}

Write-Host ""
Write-Host "==== 4) Folder quet theo MODE (code tip) ===="
Write-Host "HOURLY (sau full lan dau):"
Write-Host "  - INBOX_CLS          : quet file PDF moi tren disk"
Write-Host "  - MISSING            : rematch qua cases.csv (khong rglob G:)"
Write-Host "  - TK1 / TK2          : rematch qua cases.csv (khong list G: moi gio)"
Write-Host "FULL-SCAN / REPAIR (CHAY_MOT_LAN / TONG_HOP):"
Write-Host "  - INBOX_CLS, ERROR, PROCESSED, UNDER 18, TK1, TK2, CCCD (+ MISSING CSV)"
Write-Host ""
Write-Host "==== 5) Heartbeat + counts ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\CHAY_KIEM_HOURLY.ps1"
exit 0
