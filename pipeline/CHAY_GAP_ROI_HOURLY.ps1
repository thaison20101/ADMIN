# ============================================================
# GAP: pull + INBOX-first drain + BAT hourly — CHI MAY A (G: Drive)
# May B / o D: KHONG dung. May A: git pull roi chay script nay.
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_GAP_ROI_HOURLY.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "pkdk_Thuankieu#2026" }

Write-Host ""
Write-Host "############################################################"
Write-Host "#  GAP: INBOX truoc, roi MISSING/ERROR, roi hourly 1 gio   #"
Write-Host "############################################################"

Write-Host "==== 1/3 git pull ===="
if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git fetch origin
  git checkout cursor/drive-hourly-pipeline-df0f
  git pull origin cursor/drive-hourly-pipeline-df0f
}

Write-Host "==== 2/3 drain INBOX first, then MISSING/ERROR (khong full-scan PROCESSED) ===="
& python ".\pipeline\ensure_config.py"
& python ".\pipeline\drive_paths.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"
Write-Host "KHONG click vao cua so (Select-pause lam dung). Co the mat lau."
$cfgOut = & python ".\pipeline\print_drive_dirs.py"
$cfgOut | ForEach-Object { Write-Host $_ }
& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: Drive chua san tren may A. Bat Google Drive Desktop, doi G: hien, roi chay lai."
  exit 2
}
$code = 0
for ($round = 1; $round -le 3; $round++) {
  Write-Host ("----- VONG {0}/3 -----" -f $round)
  # Round 1: chi INBOX (missing-budget=0) de tranh mat thoi gian/IO voi MISSING
  # Round 2-3: rematch MISSING theo cap (may A chi, logs local)
  $mb = 0
  if ($round -ge 2) { $mb = 2500 }

  # Snapshot COUNTS truoc khi chay hour
  $beforeOut = & python ".\pipeline\print_drive_dirs.py"
  $beforeCountsLine = ($beforeOut | Select-Object -Last 1)
  $bParts = @($beforeCountsLine -split "\t")
  $bInbox = [int]($bParts[1] -split "=")[1]
  $bMissing = [int]($bParts[2] -split "=")[1]
  $bError = [int]($bParts[3] -split "=")[1]
  $bProcessed = [int]($bParts[4] -split "=")[1]

  $out = & python ".\pipeline\hourly_sync.py" --missing-budget $mb 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $text = ($out | Out-String)
  if ($text -match "ABORT:") {
    Write-Host "DUNG: G: mat ket noi tren may A. Mo Google Drive Desktop roi chay lai."
    $code = 2
    break
  }
  $statLine = $text | & python ".\pipeline\parse_cycle_stats.py"
  $parts = @($statLine -split "\s+")
  $imported = 0; $queued = 0; $partial = 0; $moved_missing = 0
  if ($parts.Count -ge 4) {
    $imported = [int]$parts[0]
    $queued = [int]$parts[1]
    $partial = [int]$parts[2]
    $moved_missing = [int]$parts[3]
  }
  Write-Host ("Vong {0}: imported={1} partial={2} moved_missing={3} queued={4}" -f $round, $imported, $partial, $moved_missing, $queued)
  
  # Snapshot COUNTS sau khi chay hour → tinh delta
  $afterOut = & python ".\pipeline\print_drive_dirs.py"
  $afterCountsLine = ($afterOut | Select-Object -Last 1)
  $aParts = @($afterCountsLine -split "\t")
  $aInbox = [int]($aParts[1] -split "=")[1]
  $aMissing = [int]($aParts[2] -split "=")[1]
  $aError = [int]($aParts[3] -split "=")[1]
  $aProcessed = [int]($aParts[4] -split "=")[1]

  $dInbox = $aInbox - $bInbox
  $dMissing = $aMissing - $bMissing
  $dError = $aError - $bError
  $dProcessed = $aProcessed - $bProcessed

  Write-Host ("COUNTS delta (after-before): inbox={0} missing={1} error={2} processed={3}" -f $dInbox, $dMissing, $dError, $dProcessed)
  Write-Host ("DONE_FULL(ΔPROCESSED)={0} | DONE_ANY(ΔPROCESSED+ΔERROR)={1}" -f $dProcessed, ($dProcessed + $dError))
  $afterOut | Select-Object -Last 3 | ForEach-Object { Write-Host $_ }
  # Khong stop neu co partial hoặc moved_missing — vi imported chỉ tinh FULL
  if (($imported -le 0) -and ($partial -le 0) -and ($moved_missing -le 0) -and ($queued -le 0) -and $round -ge 2) {
    break
  }
}

Write-Host "==== 3/3 BAT hourly PKDK_Hourly_Sync ===="
if ($code -eq 2) {
  Write-Host "Khong bat hourly vi G: loi. Mo Google Drive Desktop roi chay lai."
  exit 2
}
$TaskName = "PKDK_Hourly_Sync"
try {
  Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
  Write-Host "OK: Enable-ScheduledTask"
} catch {
  schtasks.exe /Change /TN $TaskName /ENABLE | Out-Null
}
if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
}
Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Format-List TaskName, State

Write-Host ""
Write-Host "XONG. Hourly moi 1 gio: INBOX truoc, roi ERROR, roi MISSING (toi da 400 file/gio)."
Write-Host "PDF nam G:\Drive cua toi\PKDK_Thuankieu_Pipeline - log nam C:\Users\thais\ADMIN\pipeline\work\build"
Write-Host "Khop TTHC (rule cu): ho + ten (token cuoi) + nam sinh. SDT/gioi tinh chi ho tro cham diem."
Write-Host "Ky Medinet: 01/07/2026 -> hom nay."
Write-Host "FULL -> PROCESSED | PARTIAL -> ERROR | chua TTHC: INBOX -> MISSING (MISSING giu nguyen)."
Write-Host ("Exit={0}" -f $code)
if ($code -ne 0) { exit $code }
exit 0
