# ============================================================
# QUET TOAN BO (LAN DAU / BAT SO BN CU) + BAT HOURLY
#
# Thu tu:
#  1) git pull (rule TTHC moi)
#  2) UU TIEN: file MOI trong INBOX_CLS + MISSING (nhieu vong)
#  3) FULL SCAN: ERROR + PROCESSED (+ folder khac) rematch
#  4) Cai / bat lai hourly PKDK_Hourly_Sync
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_QUET_LAN_DAU.ps1
#
# PowerShell Admin. KHONG click vao cua so khi dang chay.
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

function Invoke-SyncRounds {
  param(
    [string]$Label,
    [string[]]$PyArgs,
    [int]$MaxRounds = 8
  )
  $code = 0
  for ($round = 1; $round -le $MaxRounds; $round++) {
    Write-Host ("----- {0} VONG {1}/{2} -----" -f $Label, $round, $MaxRounds)
    $out = & python ".\pipeline\hourly_sync.py" @PyArgs 2>&1
    $code = $LASTEXITCODE
    $out | ForEach-Object { Write-Host $_ }
    $text = ($out | Out-String)
    $imported = 0; $queued = 0; $partial = 0; $movedMiss = 0; $auditMiss = 0
    if ($text -match "'imported':\s*(\d+)") { $imported = [int]$Matches[1] }
    if ($text -match "'queued':\s*(\d+)") { $queued = [int]$Matches[1] }
    if ($text -match "'queued_incomplete':\s*(\d+)") { $queued += [int]$Matches[1] }
    if ($text -match "'imported_partial_to_error':\s*(\d+)") { $partial = [int]$Matches[1] }
    if ($text -match "'moved_missing':\s*(\d+)") { $movedMiss = [int]$Matches[1] }
    if ($text -match "'audit_moved_missing':\s*(\d+)") { $auditMiss = [int]$Matches[1] }
    Write-Host ("{0} vong {1}: imported={2} partial={3} missing={4} audit_missing={5} queued={6}" -f $Label, $round, $imported, $partial, $movedMiss, $auditMiss, $queued)
    if (($imported -le 0) -and ($partial -le 0) -and ($queued -le 0) -and ($movedMiss -le 0) -and ($auditMiss -le 0) -and $round -ge 2) { break }
  }
  return $code
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  INBOX MOI truoc -> FULL SCAN -> BAT HOURLY              #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/5 git pull ===="
if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git fetch origin
  git checkout cursor/drive-hourly-pipeline-df0f
  git pull origin cursor/drive-hourly-pipeline-df0f
} else {
  Write-Host "Khong co .git — bo qua git pull (dung CAP_NHAT_TU_GITHUB.ps1 neu can)."
}

Write-Host "==== 2/5 config + deps ===="
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
$SyncRoot = [string]$lines[0]
$Inbox = [string]$lines[1]
$ErrorDir = [string]$lines[2]
$Processed = [string]$lines[3]
$Missing = [string]$lines[4]
New-Item -ItemType Directory -Force -Path $Missing | Out-Null

Write-Host ("TRUOC: INBOX={0} MISSING={1} ERROR={2} PROCESSED={3}" -f (Count-Pdf $Inbox), (Count-Pdf $Missing), (Count-Pdf $ErrorDir), (Count-Pdf $Processed))
Write-Host "Ky Medinet: 01/07/2026 -> hom nay"
Write-Host "Khop: HO TEN DAY DU + nam sinh + gioi tinh + SDT (neu PDF co)"

Write-Host "==== 3/5 UU TIEN file MOI trong INBOX_CLS + MISSING ===="
Write-Host "Moi PDF vua tha vao INBOX se duoc dang ky + import truoc."
$codeInbox = Invoke-SyncRounds -Label "INBOX" -PyArgs @("--repair") -MaxRounds 8

Write-Host ("SAU INBOX: INBOX={0} MISSING={1} ERROR={2} PROCESSED={3}" -f (Count-Pdf $Inbox), (Count-Pdf $Missing), (Count-Pdf $ErrorDir), (Count-Pdf $Processed))

Write-Host "==== 4/5 FULL SCAN (ERROR + PROCESSED + rematch TTHC) ===="
Write-Host "Ep rematch rule moi; PDF khong khop -> MISSING. KHONG click cua so."
$codeFull = Invoke-SyncRounds -Label "FULL" -PyArgs @("--full-scan", "--repair") -MaxRounds 12
$code = $codeFull
if ($codeInbox -ne 0 -and $code -eq 0) { $code = $codeInbox }

Write-Host "==== 5/5 CAI / BAT LAI HOURLY PKDK_Hourly_Sync ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$codeTask = $LASTEXITCODE

Write-Host ""
Write-Host "========== XONG =========="
Write-Host ("SAU: INBOX={0} MISSING={1} ERROR={2} PROCESSED={3}" -f (Count-Pdf $Inbox), (Count-Pdf $Missing), (Count-Pdf $ErrorDir), (Count-Pdf $Processed))
Write-Host "INBOX     = file moi se duoc hourly xu ly tiep (moi 1 gio)"
Write-Host "MISSING   = chua co TTHC dung"
Write-Host "ERROR     = PDF chi 1 phan (da nhap phan co)"
Write-Host "PROCESSED = FULL + khop TTHC dung"
Write-Host ("Exit inbox={0} full={1} task={2}" -f $codeInbox, $codeFull, $codeTask)
Write-Host "=========================="
if ($codeTask -ne 0) { exit $codeTask }
if ($code -ne 0) { exit $code }
exit 0
