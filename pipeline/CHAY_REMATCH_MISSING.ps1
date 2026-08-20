# ============================================================
# REMATCH MISSING: nhieu file MISSING da co TTHC tren web
# Rematch tu tracking CSV (KHONG list 10k file tren G:), 2500/vong
# ASCII-only. Chi may A — G:\Drive cua toi\PKDK_Thuankieu_Pipeline
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_REMATCH_MISSING.ps1
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
  param([switch]$Quick)
  $argsPy = @(".\pipeline\print_drive_dirs.py")
  if ($Quick) { $argsPy += "--quick" }
  $lines = @(& python @argsPy 2>$null)
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
Write-Host "#  REMATCH MISSING (TTHC da co tren web) — may A G: only   #"
Write-Host "############################################################"
Write-Host "Log Python in LIEN TUC. KHONG click cua so (Select-pause)."
Write-Host "Neu cua so cu dang im sau COUNTS before: Ctrl+C, git pull, chay lai."

if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git pull origin cursor/drive-hourly-pipeline-df0f
}
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"
& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san. Mo Google Drive Desktop. KHONG dung C:\Users\thais\ADMIN lam sync."
  exit 2
}

Write-Host "COUNTS 1 lan (list MISSING co the cham). Cac vong sau dung --quick."
$first = Get-Counts
Write-Host ("COUNTS start: {0}" -f $first.raw)
Write-Host "Mo Explorer MISSING/PROCESSED de theo doi so muc."

$code = 0
for ($round = 1; $round -le 8; $round++) {
  Write-Host ("----- REMATCH VONG {0}/8 -----" -f $round)
  & python ".\pipeline\assert_g_pipeline.py"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "DUNG: G: mat ket noi. Mo Drive roi chay lai. Exit=2"
    exit 2
  }
  $before = Get-Counts -Quick
  Write-Host ("COUNTS before (quick, missing=-1 skip list): {0}" -f $before.raw)
  Write-Host "Chay hourly_sync --missing-budget 2500 (CSV rematch, log live) ..."
  $code = Invoke-PythonLive @(".\pipeline\hourly_sync.py", "--missing-budget", "2500")
  $text = ($script:LastPyLines -join "`n")
  if ($text -match "ABORT:") {
    Write-Host "DUNG: ABORT (khong fallback ADMIN). Mo G: Drive roi chay lai."
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
  $after = Get-Counts -Quick
  $dProcessed = $after.processed - $before.processed
  $dError = $after.error - $before.error
  $dInbox = $after.inbox - $before.inbox
  Write-Host ("Vong {0}: imported={1} partial={2} queued={3}" -f $round, $imported, $partial, $queued)
  Write-Host ("COUNTS after (quick): {0}" -f $after.raw)
  Write-Host ("DELTA inbox={0} processed={1} error={2} (MISSING xem Explorer)" -f $dInbox, $dProcessed, $dError)
  Write-Host ("DONE_FULL={0} DONE_ANY={1}" -f $dProcessed, ($dProcessed + $dError))
  if ($round -ge 2 -and ($imported -le 0) -and ($partial -le 0) -and ($dProcessed -eq 0) -and ($dError -eq 0)) {
    Write-Host "Het tien do rematch (con lai trong MISSING = chua co TTHC that)."
    break
  }
}

$final = Get-Counts -Quick
Write-Host ""
Write-Host "XONG REMATCH. COUNTS quick: $($final.raw)"
Write-Host "MISSING con lai = chua khop TTHC (can admin nhap). Da khop se o PROCESSED/ERROR."
Write-Host "Xem Explorer: G:\Drive cua toi\PKDK_Thuankieu_Pipeline\MISSING"
if ($code -ne 0) { exit $code }
exit 0
