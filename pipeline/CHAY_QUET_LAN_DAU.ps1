# ============================================================
# QUET TOAN BO (1 lan) + BAT HOURLY
# ASCII-only so Windows PowerShell 5.1 can parse this file.
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_QUET_LAN_DAU.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "pkdk_Thuankieu#2026" }
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

function Count-Pdf([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return 0 }
  return @(Get-ChildItem -LiteralPath $Path -Recurse -Filter *.pdf -ErrorAction SilentlyContinue).Count
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  FULL SCAN (gom INBOX moi) + BAT HOURLY                  #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/4 git pull ===="
if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git fetch origin
  git checkout cursor/drive-hourly-pipeline-df0f
  git pull origin cursor/drive-hourly-pipeline-df0f
} else {
  Write-Host "Khong co .git - bo qua git pull."
}

Write-Host "==== 2/4 config + deps ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"
if (Test-Path ".\pipeline\test_match_strict.py") {
  & python ".\pipeline\test_match_strict.py"
}

$cfgOut = & python ".\pipeline\print_drive_dirs.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "ERROR: khong doc duoc config.local.json"
  exit 1
}
$lines = @($cfgOut)
$Inbox = [string]$lines[1]
$ErrorDir = [string]$lines[2]
$Processed = [string]$lines[3]
$Missing = [string]$lines[4]
New-Item -ItemType Directory -Force -Path $Missing | Out-Null

$nIn = Count-Pdf $Inbox
$nMiss = Count-Pdf $Missing
$nErr = Count-Pdf $ErrorDir
$nPr = Count-Pdf $Processed
Write-Host ("TRUOC: INBOX={0} MISSING={1} ERROR={2} PROCESSED={3}" -f $nIn, $nMiss, $nErr, $nPr)
Write-Host "Ky Medinet: 01/07/2026 -> hom nay"
Write-Host "Khop: HO TEN DAY DU + nam sinh + gioi tinh + SDT (neu PDF co)"
Write-Host "Full-scan xu ly CA file moi trong INBOX_CLS."

Write-Host "==== 3/4 FULL SCAN + REPAIR (INBOX + MISSING + ERROR + PROCESSED) ===="
Write-Host "Index Medinet theo cua so 14 ngay."
Write-Host "KHONG click vao cua so khi dang chay."
$code = 0
for ($round = 1; $round -le 4; $round++) {
  Write-Host ("----- VONG {0}/4 -----" -f $round)
  $out = & python ".\pipeline\hourly_sync.py" --full-scan --repair 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $text = ($out | Out-String)
  $statLine = $text | & python ".\pipeline\parse_cycle_stats.py"
  $parts = @($statLine -split "\s+")
  $imported = 0; $queued = 0; $partial = 0; $movedMiss = 0; $auditMiss = 0
  if ($parts.Count -ge 5) {
    $imported = [int]$parts[0]
    $queued = [int]$parts[1]
    $partial = [int]$parts[2]
    $movedMiss = [int]$parts[3]
    $auditMiss = [int]$parts[4]
  }
  Write-Host ("Vong {0}: imported={1} partial={2} missing={3} audit_missing={4} queued={5}" -f $round, $imported, $partial, $movedMiss, $auditMiss, $queued)
  if (($imported -le 0) -and ($partial -le 0) -and ($queued -le 0) -and ($movedMiss -le 0) -and ($auditMiss -le 0) -and $round -ge 2) { break }
}

Write-Host "==== 4/4 CAI / BAT LAI HOURLY PKDK_Hourly_Sync ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$codeTask = $LASTEXITCODE

$nIn2 = Count-Pdf $Inbox
$nMiss2 = Count-Pdf $Missing
$nErr2 = Count-Pdf $ErrorDir
$nPr2 = Count-Pdf $Processed
Write-Host ""
Write-Host "========== XONG =========="
Write-Host ("SAU: INBOX={0} MISSING={1} ERROR={2} PROCESSED={3}" -f $nIn2, $nMiss2, $nErr2, $nPr2)
Write-Host "Hourly tiep theo: chi INBOX_CLS + MISSING."
Write-Host ("Exit import={0} task={1}" -f $code, $codeTask)
Write-Host "=========================="
if ($codeTask -ne 0) { exit $codeTask }
if ($code -ne 0) { exit $code }
exit 0
