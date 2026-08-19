# ============================================================
# GAP: pull + INBOX-first drain + BAT hourly
# ASCII-only. KHONG rematch PROCESSED. KHONG --repair (repair quet 11k MISSING truoc).
# Logs: C:\Users\thais\ADMIN\pipeline\work\build  (khong ghi G: - G: bi unmount)
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
  Write-Host "DUNG: G: Drive chua san. Bat Google Drive Desktop, doi G: hien, roi chay lai."
  Write-Host "KHONG dung D:\PKDK_Thuankieu_Pipeline (mirror rong)."
  exit 2
}
$code = 0
for ($round = 1; $round -le 3; $round++) {
  Write-Host ("----- VONG {0}/3 -----" -f $round)
  $out = & python ".\pipeline\hourly_sync.py" --missing-budget 2500 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $text = ($out | Out-String)
  if ($text -match "ABORT:") {
    Write-Host "DUNG: G: mat ket noi. Mo Google Drive Desktop roi chay lai. KHONG dung D:."
    $code = 2
    break
  }
  $statLine = $text | & python ".\pipeline\parse_cycle_stats.py"
  $parts = @($statLine -split "\s+")
  $imported = 0; $queued = 0
  if ($parts.Count -ge 2) {
    $imported = [int]$parts[0]
    $queued = [int]$parts[1]
  }
  Write-Host ("Vong {0}: imported={1} queued={2}" -f $round, $imported, $queued)
  & python ".\pipeline\print_drive_dirs.py" | Select-Object -Last 3 | ForEach-Object { Write-Host $_ }
  if (($imported -le 0) -and ($queued -le 0) -and $round -ge 2) { break }
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
