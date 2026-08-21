# ============================================================
# 1 LENH MAY A: TONG 2 CODE (LOC UNDER 18 + REMATCH) + DOI HOURLY
# ASCII-only. Chi may A - G:\Drive cua toi\PKDK_Thuankieu_Pipeline
#
# Buoc:
#   1) TAT hourly cu (PKDK_Hourly_Sync)
#   2) git pull code moi
#   3) Loc PDF duoi 18 -> UNDER 18
#   4) Rematch MISSING (M2/M3/M4/M11, CSV, 2500/vong)
#   5) Cai lai + BAT hourly cho code moi
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_TONG_HOP_VA_BAT_HOURLY.ps1
# ============================================================

param(
  [switch]$SkipRematch,
  [switch]$SkipUrea,
  [int]$RematchRounds = 8
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
Write-Host "#  TONG HOP: TAT hourly cu | LOC U18 | REMATCH | BAT moi  #"
Write-Host "############################################################"
Write-Host "CHI 1 CUA SO. KHONG click cua so (Select-pause)."
Write-Host "PDF: G:\Drive cua toi\PKDK_Thuankieu_Pipeline"
Write-Host "Log: C:\Users\thais\ADMIN\pipeline\work\build"

# ---- 1/5 TAT hourly cu ----
Write-Host ""
Write-Host "==== 1/5 TAT hourly cu ($TaskName) ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
$lockFile = Join-Path $Repo "pipeline\work\locks\auto_cycle.lock"
if (Test-Path -LiteralPath $lockFile) {
  Write-Host "Xoa lock cu (hourly da tat): $lockFile"
  Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
}

# ---- 2/5 git pull + config ----
Write-Host ""
Write-Host "==== 2/5 git pull code moi ($Branch) ===="
if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git fetch origin
  git checkout $Branch
  git pull origin $Branch
} else {
  Write-Host "WARN: khong co .git - dung code local hien tai."
}
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"
& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san. Mo Google Drive Desktop. KHONG bat hourly."
  exit 2
}

# Wipe index cache cu (M3+M4 only) 1 lan de rebuild M2/M11
$idx = Join-Path $Repo "pipeline\work\index_cache"
if (Test-Path -LiteralPath $idx) {
  Write-Host "Xoa index_cache cu de rebuild M2+M3+M4+M11 ..."
  Get-ChildItem -LiteralPath $idx -Filter "*.pkl" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

$beforeAll = Get-Counts
Write-Host ("COUNTS truoc: {0}" -f $beforeAll.raw)

# ---- 3/5 LOC UNDER 18 ----
Write-Host ""
Write-Host "==== 3/5 LOC UNDER 18 (INBOX+MISSING+ERROR -> UNDER 18) ===="
$codeU18 = Invoke-PythonLive @(".\pipeline\move_under18.py", "--disk-scan")
if ($codeU18 -ne 0) {
  Write-Host "DUNG: loc UNDER 18 loi. KHONG bat hourly. Exit=$codeU18"
  exit $codeU18
}
$afterU18 = Get-Counts
Write-Host ("COUNTS sau loc U18: {0}" -f $afterU18.raw)

# ---- 4/5 DRAIN INBOX (PDF moi) roi REMATCH MISSING ----
$code = 0
if ($SkipRematch) {
  Write-Host "==== 4/5 IMPORT/REMATCH: SKIP (-SkipRematch) ===="
} else {
  Write-Host ""
  Write-Host "==== 4a/5 QUET + IMPORT INBOX (INBOX_CLS + inbox) - PDF moi uu tien ===="
  Write-Host "Rule khop TTHC: ho + ten (token dau+cuoi, ten day du) + nam sinh."
  Write-Host "FULL labs -> PROCESSED | PARTIAL -> ERROR | chua TTHC -> MISSING."
  $inboxRounds = [Math]::Max(4, $RematchRounds)
  for ($round = 1; $round -le $inboxRounds; $round++) {
    Write-Host ("----- INBOX VONG {0}/{1} (missing-budget=0) -----" -f $round, $inboxRounds)
    & python ".\pipeline\assert_g_pipeline.py"
    if ($LASTEXITCODE -ne 0) {
      Write-Host "DUNG: G: mat ket noi. Mo Drive. KHONG bat hourly."
      exit 2
    }
    $before = Get-Counts
    Write-Host ("COUNTS before: {0}" -f $before.raw)
    # 0 = chi quet/import INBOX(+ERROR), khong burn budget vao MISSING
    $code = Invoke-PythonLive @(".\pipeline\hourly_sync.py", "--missing-budget", "0")
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
    $dInbox = $after.inbox - $before.inbox
    $dProcessed = $after.processed - $before.processed
    $dError = $after.error - $before.error
    $dMissing = $after.missing - $before.missing
    Write-Host ("INBOX vong {0}: imported={1} partial={2} queued={3}" -f $round, $imported, $partial, $queued)
    Write-Host ("COUNTS after : {0}" -f $after.raw)
    Write-Host ("DELTA inbox={0} missing={1} error={2} processed={3}" -f $dInbox, $dMissing, $dError, $dProcessed)
    if ($round -ge 2 -and ($imported -le 0) -and ($partial -le 0) -and ($dInbox -eq 0) -and ($dProcessed -eq 0) -and ($dError -eq 0)) {
      Write-Host "INBOX het tien do (PDF moi da xu ly xong vong nay)."
      break
    }
  }

  Write-Host ""
  Write-Host ("==== 4b/5 REMATCH MISSING (toi da {0} vong x 2500) ====" -f $RematchRounds)
  for ($round = 1; $round -le $RematchRounds; $round++) {
    Write-Host ("----- REMATCH VONG {0}/{1} -----" -f $round, $RematchRounds)
    & python ".\pipeline\assert_g_pipeline.py"
    if ($LASTEXITCODE -ne 0) {
      Write-Host "DUNG: G: mat ket noi. Mo Drive. KHONG bat hourly."
      exit 2
    }
    $before = Get-Counts
    Write-Host ("COUNTS before: {0}" -f $before.raw)
    $code = Invoke-PythonLive @(".\pipeline\hourly_sync.py", "--missing-budget", "2500")
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
    $dMissing = $after.missing - $before.missing
    $dProcessed = $after.processed - $before.processed
    $dError = $after.error - $before.error
    Write-Host ("Vong {0}: imported={1} partial={2} queued={3}" -f $round, $imported, $partial, $queued)
    Write-Host ("COUNTS after : {0}" -f $after.raw)
    Write-Host ("DELTA missing={0} error={1} processed={2}" -f $dMissing, $dError, $dProcessed)
    if ($round -ge 2 -and ($imported -le 0) -and ($partial -le 0) -and ($dProcessed -eq 0) -and ($dError -eq 0) -and ($dMissing -eq 0)) {
      Write-Host "Het tien do rematch."
      break
    }
  }
}

if (-not $SkipUrea) {
  Write-Host ""
  Write-Host "==== 4c/5 BO SUNG Ure (INBOX+ERROR+PROCESSED) ===="
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_BO_SUNG_THIEU.ps1"
  $bs = $LASTEXITCODE
  if ($bs -ne 0) {
    Write-Host "WARN: BO SUNG that bai Exit=$bs - van tiep tuc BAT hourly."
  }
}

# ---- 5/5 BAT hourly moi (re-register runner code moi) ----
Write-Host ""
Write-Host "==== 5/5 CAI LAI + BAT hourly cho code moi ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$inst = $LASTEXITCODE
if ($inst -ne 0) {
  Write-Host "WARN: install_hourly_task fail Exit=$inst - thu BAT_LAI..."
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}

try {
  Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Format-List TaskName, State
  Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue | Format-List NextRunTime, LastRunTime
} catch {}

$final = Get-Counts
Write-Host ""
Write-Host "========== XONG TONG HOP =========="
Write-Host ("COUNTS cuoi: {0}" -f $final.raw)
Write-Host "UNDER 18: G:\Drive cua toi\PKDK_Thuankieu_Pipeline\UNDER 18"
Write-Host "Muon xu ly tre: chuyen PDF UNDER 18 -> INBOX_CLS (hourly se nhat)."
Write-Host "Hourly moi: PKDK_Hourly_Sync (moi 1 gio, code branch $Branch)."
Write-Host ("Exit rematch={0}" -f $code)
if ($code -ne 0) { exit $code }
exit 0
