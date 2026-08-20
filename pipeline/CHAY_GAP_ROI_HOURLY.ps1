# ============================================================
# GAP may A: INBOX -> rematch MISSING theo vong -> bo sung Ure -> BAT hourly
# ASCII-only. PDF: G:\Drive cua toi\PKDK_Thuankieu_Pipeline
# Log: C:\Users\thais\ADMIN\pipeline\work\build
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
$env:PYTHONUNBUFFERED = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "pkdk_Thuankieu#2026" }

function Get-Counts {
  $lines = @(& python ".\pipeline\print_counts.py" 2>$null)
  $counts = ($lines | Select-Object -Last 1)
  $parts = @($counts -split "\t")
  $o = @{ inbox = 0; missing = 0; error = 0; processed = 0; raw = $counts }
  try {
    $o.inbox = [int](($parts[1] -split "=")[1])
    $o.missing = [int](($parts[2] -split "=")[1])
    $o.error = [int](($parts[3] -split "=")[1])
    $o.processed = [int](($parts[4] -split "=")[1])
  } catch {}
  return $o
}

function Invoke-PythonLive {
  param([string[]]$PyArgs)
  $script:LastPyLines = New-Object System.Collections.Generic.List[string]
  & python -u @PyArgs 2>&1 | ForEach-Object {
    Write-Host $_
    [void]$script:LastPyLines.Add("$_")
  }
  return $LASTEXITCODE
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  GAP may A: INBOX + MISSING rematch + Ure + hourly       #"
Write-Host "############################################################"

Write-Host "==== 1/4 git pull ===="
if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git fetch origin
  git checkout cursor/drive-hourly-pipeline-df0f
  git pull origin cursor/drive-hourly-pipeline-df0f
}

Write-Host "==== 2/4 assert G: + config ===="
& python ".\pipeline\ensure_config.py"
& python ".\pipeline\drive_paths.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"
Write-Host "KHONG click vao cua so (Select-pause lam dung). Log Python in lien tuc."
Write-Host "COUNTS tu tracking CSV (inbox/missing/error/processed) in tren cua so."
& python ".\pipeline\print_counts.py" | ForEach-Object { Write-Host $_ }
& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san. Mo Google Drive Desktop roi chay lai. KHONG bat hourly."
  exit 2
}

$code = 0

Write-Host "==== 3/4 drain INBOX roi rematch MISSING (nhieu vong, G: song) ===="
# Round 1: INBOX only. Round 2+: MISSING budget 2000/vong (tranh G: chet)
for ($round = 1; $round -le 6; $round++) {
  Write-Host ("----- VONG {0}/6 -----" -f $round)
  & python ".\pipeline\assert_g_pipeline.py"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "DUNG: G: mat ket noi. Mo Drive, chay lai. KHONG bat hourly."
    exit 2
  }
  $before = Get-Counts
  Write-Host ("COUNTS before: {0}" -f $before.raw)
  $mb = 0
  if ($round -ge 2) { $mb = 2500 }
  Write-Host ("hourly_sync --missing-budget {0} (0=INBOX only; log live)" -f $mb)
  $code = Invoke-PythonLive @(".\pipeline\hourly_sync.py", "--missing-budget", "$mb")
  $text = ($script:LastPyLines -join "`n")
  if ($text -match "ABORT:") {
    Write-Host "DUNG: ABORT G:. KHONG bat hourly."
    exit 2
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
  $after = Get-Counts
  $dInbox = $after.inbox - $before.inbox
  $dMissing = $after.missing - $before.missing
  $dError = $after.error - $before.error
  $dProcessed = $after.processed - $before.processed
  Write-Host ("Vong {0}: imported={1} partial={2} moved_missing={3} queued={4}" -f $round, $imported, $partial, $moved_missing, $queued)
  Write-Host ("COUNTS before: {0}" -f $before.raw)
  Write-Host ("COUNTS after : {0}" -f $after.raw)
  Write-Host ("COUNTS delta : inbox={0} missing={1} error={2} processed={3}" -f $dInbox, $dMissing, $dError, $dProcessed)
  Write-Host ("DONE_FULL(DELTA_PROCESSED)={0} | DONE_ANY(DELTA_PROCESSED+DELTA_ERROR)={1}" -f $dProcessed, ($dProcessed + $dError))
  # Round 1 xong INBOX; round 2+ dung khi khong con tien do
  if ($round -ge 3 -and ($imported -le 0) -and ($partial -le 0) -and ($moved_missing -le 0) -and ($queued -le 0) -and ($dProcessed -eq 0) -and ($dError -eq 0)) {
    break
  }
}

Write-Host "==== 4/4 BO SUNG Ure (INBOX+ERROR+PROCESSED) roi BAT hourly ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_BO_SUNG_THIEU.ps1"
$bs = $LASTEXITCODE
if ($bs -ne 0) {
  Write-Host "BO SUNG that bai / G: loi. KHONG bat hourly. Exit=$bs"
  exit $bs
}

Write-Host "==== BAT hourly PKDK_Hourly_Sync ===="
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

$final = Get-Counts
Write-Host ""
Write-Host "XONG. COUNTS cuoi: $($final.raw)"
Write-Host "MISSING cao? Chay them: powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_REMATCH_MISSING.ps1"
Write-Host "MISSING chi giam khi Medinet da co TTHC (ho+ten+nam sinh)."
Write-Host "FULL -> PROCESSED | PARTIAL -> ERROR | chua TTHC: INBOX -> MISSING."
Write-Host "KHONG fallback C:\Users\thais\ADMIN — chi G:\Drive cua toi\PKDK_Thuankieu_Pipeline."
Write-Host ("Exit={0}" -f $code)
if ($code -ne 0) { exit $code }
exit 0
