# ============================================================
# 1 LENH MAY A (DUY NHAT): chuan hoa pipeline + full lan dau + hourly
# ASCII-only. Chi G:\Drive cua toi\PKDK_Thuankieu_Pipeline
# Inbox dung: ...\INBOX_CLS (khong dung folder "inbox")
#
# Rule:
#   - Khop: du ho + ten + nam sinh (ngay kham 01/07/2026 -> hom nay)
#   - Import day du ke ca Urea + doi don vi dung
#   - FULL nguoi lon -> PROCESSED | FULL tre <18 -> UNDER 18 (form M2)
#   - PARTIAL (ke ca tre) -> ERROR | chua TTHC -> MISSING
#   - Lan dau: quet TOAN BO. Sau do hourly: chi INBOX_CLS + MISSING
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_TONG_HOP_VA_BAT_HOURLY.ps1
# ============================================================

param(
  [int]$FullRounds = 4,
  [int]$RematchRounds = 6
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "pkdk_Thuankieu#2026" }

$TaskName = "PKDK_Hourly_Sync"
$Branch = "cursor/drive-hourly-pipeline-df0f"
$FlagFull = Join-Path $Repo "pipeline\work\build\FIRST_FULL_SCAN_DONE.txt"

function Get-Counts {
  $lines = @(& python ".\pipeline\print_counts.py" 2>$null)
  $counts = ($lines | Select-Object -Last 1)
  $parts = @($counts -split "\t")
  $o = @{ inbox = 0; missing = 0; error = 0; processed = 0; under18 = 0; raw = $counts }
  try {
    foreach ($p in $parts) {
      if ($p -match "^inbox=(\d+)$") { $o.inbox = [int]$Matches[1] }
      if ($p -match "^missing=(\d+)$") { $o.missing = [int]$Matches[1] }
      if ($p -match "^error=(\d+)$") { $o.error = [int]$Matches[1] }
      if ($p -match "^processed=(\d+)$") { $o.processed = [int]$Matches[1] }
      if ($p -match "^under18=(\d+)$") { $o.under18 = [int]$Matches[1] }
    }
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
Write-Host "#  MAY A DUY NHAT: FULL lan dau + BAT hourly ngay          #"
Write-Host "############################################################"
Write-Host "INBOX: G:\Drive cua toi\PKDK_Thuankieu_Pipeline\INBOX_CLS"
Write-Host "Rule: ho+ten+nam sinh | Urea bat buoc neu PDF co | M2 cho tre"
Write-Host "CHI 1 CUA SO. KHONG click (Select-pause)."

# ---- 1 TAT hourly cu ----
Write-Host ""
Write-Host "==== 1/6 TAT hourly cu ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
$lockFile = Join-Path $Repo "pipeline\work\locks\auto_cycle.lock"
if (Test-Path -LiteralPath $lockFile) {
  Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
}

# ---- 2 git pull ----
Write-Host ""
Write-Host "==== 2/6 git pull ($Branch) ===="
if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git fetch origin
  git checkout $Branch
  git pull origin $Branch
}
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"
& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san. KHONG bat hourly."
  exit 2
}

# Wipe stale index (rebuild M2+M3+M4+M11)
$idx = Join-Path $Repo "pipeline\work\index_cache"
if (Test-Path -LiteralPath $idx) {
  Get-ChildItem -LiteralPath $idx -Filter "*.pkl" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

# Reset first-full flag so this run IS the first full sweep
if (Test-Path -LiteralPath $FlagFull) {
  Remove-Item -LiteralPath $FlagFull -Force -ErrorAction SilentlyContinue
}

Write-Host ("COUNTS truoc: {0}" -f (Get-Counts).raw)

# ---- 3 FULL SCAN + REPAIR (toan bo PDF, urea, route dung) ----
Write-Host ""
Write-Host "==== 3/6 FULL SCAN + REPAIR (toan bo folder tren G:) ===="
Write-Host "Inbox dung: INBOX_CLS | Tre FULL -> UNDER 18 | PARTIAL -> ERROR"
$code = 0
for ($round = 1; $round -le $FullRounds; $round++) {
  Write-Host ("----- FULL VONG {0}/{1} -----" -f $round, $FullRounds)
  & python ".\pipeline\assert_g_pipeline.py"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "DUNG: G: mat ket noi. KHONG bat hourly."
    exit 2
  }
  $before = Get-Counts
  Write-Host ("COUNTS before: {0}" -f $before.raw)
  $code = Invoke-PythonLive @(
    ".\pipeline\hourly_sync.py",
    "--full-scan",
    "--repair",
    "--missing-budget", "2500"
  )
  $text = ($script:LastPyLines -join "`n")
  if ($text -match "ABORT:") {
    Write-Host "DUNG: ABORT G:. KHONG bat hourly."
    exit 2
  }
  $statLine = $text | & python ".\pipeline\parse_cycle_stats.py"
  $parts = @($statLine -split "\s+")
  $imported = 0; $queued = 0; $partial = 0
  if ($parts.Count -ge 3) {
    $imported = [int]$parts[0]
    $queued = [int]$parts[1]
    $partial = [int]$parts[2]
  }
  $after = Get-Counts
  Write-Host ("FULL vong {0}: imported={1} partial={2} queued={3}" -f $round, $imported, $partial, $queued)
  Write-Host ("COUNTS after : {0}" -f $after.raw)
  if ($round -ge 2 -and ($imported -le 0) -and ($partial -le 0) -and ($queued -le 0)) {
    Write-Host "FULL het tien do."
    break
  }
}

# ---- 4 REMATCH MISSING con lai ----
Write-Host ""
Write-Host "==== 4/6 REMATCH MISSING (CSV, khong list 10k G:) ===="
for ($round = 1; $round -le $RematchRounds; $round++) {
  Write-Host ("----- REMATCH VONG {0}/{1} -----" -f $round, $RematchRounds)
  & python ".\pipeline\assert_g_pipeline.py"
  if ($LASTEXITCODE -ne 0) { exit 2 }
  $before = Get-Counts
  Write-Host ("COUNTS before: {0}" -f $before.raw)
  $code = Invoke-PythonLive @(".\pipeline\hourly_sync.py", "--missing-budget", "2500")
  $text = ($script:LastPyLines -join "`n")
  if ($text -match "ABORT:") { exit 2 }
  $after = Get-Counts
  $dMissing = $after.missing - $before.missing
  $dProcessed = $after.processed - $before.processed
  $dError = $after.error - $before.error
  $dU18 = $after.under18 - $before.under18
  Write-Host ("COUNTS after : {0}" -f $after.raw)
  Write-Host ("DELTA missing={0} error={1} processed={2} under18={3}" -f $dMissing, $dError, $dProcessed, $dU18)
  if ($round -ge 2 -and ($dMissing -eq 0) -and ($dProcessed -eq 0) -and ($dError -eq 0) -and ($dU18 -eq 0)) {
    break
  }
}

# ---- 5 BO SUNG Urea tren INBOX+ERROR+PROCESSED+UNDER18 ----
Write-Host ""
Write-Host "==== 5/6 BO SUNG Urea/field (repair) ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_BO_SUNG_THIEU.ps1"

# Mark first full done so hourly stays light
try {
  $FlagDir = Split-Path -Parent $FlagFull
  if (-not (Test-Path -LiteralPath $FlagDir)) {
    New-Item -ItemType Directory -Force -Path $FlagDir | Out-Null
  }
  Set-Content -LiteralPath $FlagFull -Value ("done=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -Encoding utf8
  Write-Host "OK: danh dau FIRST_FULL_SCAN_DONE (hourly sau chi INBOX_CLS+MISSING)"
} catch {
  Write-Host ("WARN flag: " + $_)
}

# ---- 6 BAT hourly NGAY (khong doi gio sau) ----
Write-Host ""
Write-Host "==== 6/6 CAI LAI + BAT hourly NGAY ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
if ($LASTEXITCODE -ne 0) {
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}
try {
  Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Write-Host "OK: Start-ScheduledTask (chay ngay 1 lan, mode nhe INBOX_CLS+MISSING)"
} catch {}
try {
  Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Format-List TaskName, State
  Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue | Format-List NextRunTime, LastRunTime
} catch {}

$final = Get-Counts
Write-Host ""
Write-Host "========== XONG =========="
Write-Host ("COUNTS: {0}" -f $final.raw)
Write-Host "INBOX_CLS = PDF moi | MISSING = cho TTHC | ERROR = thieu field PDF"
Write-Host "PROCESSED = FULL nguoi lon | UNDER 18 = FULL tre (form M2)"
Write-Host "Hourly: moi 1 gio + da Start ngay. Chi may A."
if ($code -ne 0) { exit $code }
exit 0
