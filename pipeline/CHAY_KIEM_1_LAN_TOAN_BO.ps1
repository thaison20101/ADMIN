# ============================================================
# KIEM 1 LAN TOAN BO PDF (KHONG cai hourly)
#
# Quet: INBOX_CLS + MISSING + ERROR + PROCESSED (+ folder khac)
# Rule TTHC: ho ten day du + nam sinh + gioi tinh + SDT (neu PDF co)
#  - Khong khop / khop sai (vd TRAN SANH ≠ TRAN NGOC SANH) → MISSING
#  - FULL labs → import → PROCESSED
#  - PARTIAL → import phan co → ERROR
#
# BN da nhap CLS SAI tren Medinet:
#  - Xoa CLS sai tren web (form CLS cua dung BN)
#  - De PDF o MISSING / INBOX; khi TTHC dung + PDF moi → import de len
#
#   cd C:\Users\Administrator\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_KIEM_1_LAN_TOAN_BO.ps1
#
# KHONG click vao cua so khi dang chay. Chi can 1 lan — khong bat Task Scheduler.
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
Write-Host "#  KIEM 1 LAN: INBOX + MISSING + ERROR + PROCESSED         #"
Write-Host "#  (KHONG cai hourly — chi chay 1 lan)                     #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/3 git pull (rule TTHC moi) ===="
git fetch origin
git checkout cursor/drive-hourly-pipeline-df0f
git pull origin cursor/drive-hourly-pipeline-df0f

Write-Host "==== 2/3 config + deps ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"
& python ".\pipeline\test_match_strict.py"

$cfgOut = & python -c @"
import json
from pathlib import Path
c=json.loads(Path('pipeline/config.local.json').read_text(encoding='utf-8-sig'))
s=c['drive']['local_sync_root']
d=c['drive']
print(s)
print(s+'\\'+d['inbox_folder'])
print(s+'\\'+d['error_folder'])
print(s+'\\'+d['processed_folder'])
print(s+'\\'+d.get('missing_folder','MISSING'))
"@
$lines = @($cfgOut)
$SyncRoot = $lines[0]
$Inbox = $lines[1]
$ErrorDir = $lines[2]
$Processed = $lines[3]
$Missing = $lines[4]
New-Item -ItemType Directory -Force -Path $Missing | Out-Null

Write-Host ("TRUOC: INBOX={0} MISSING={1} ERROR={2} PROCESSED={3}" -f (Count-Pdf $Inbox), (Count-Pdf $Missing), (Count-Pdf $ErrorDir), (Count-Pdf $Processed))
Write-Host "Ky Medinet: 01/07/2026 -> hom nay"
Write-Host "Khop: HO TEN DAY DU + nam sinh + gioi tinh + SDT (neu PDF co)"
Write-Host "     TRAN SANH != TRAN NGOC SANH / TRAN VAN SANH"

Write-Host "==== 3/3 FULL SCAN + REPAIR (nhieu vong, KHONG hourly) ===="
Write-Host "Ep rematch moi PDF (ke ca da IMPORTED trong PROCESSED)."
Write-Host "Khong khop TTHC -> chuyen MISSING. Co the mat LAU — dung click cua so."
$code = 0
for ($round = 1; $round -le 12; $round++) {
  Write-Host ("----- VONG {0}/12 -----" -f $round)
  $out = & python ".\pipeline\hourly_sync.py" --full-scan --repair 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $text = ($out | Out-String)
  $imported = 0
  $queued = 0
  $partial = 0
  $movedMiss = 0
  $auditMiss = 0
  if ($text -match "'imported':\s*(\d+)") { $imported = [int]$Matches[1] }
  if ($text -match "'queued':\s*(\d+)") { $queued = [int]$Matches[1] }
  if ($text -match "'queued_incomplete':\s*(\d+)") { $queued += [int]$Matches[1] }
  if ($text -match "'imported_partial_to_error':\s*(\d+)") { $partial = [int]$Matches[1] }
  if ($text -match "'moved_missing':\s*(\d+)") { $movedMiss = [int]$Matches[1] }
  if ($text -match "'audit_moved_missing':\s*(\d+)") { $auditMiss = [int]$Matches[1] }
  Write-Host ("Vong {0}: imported={1} partial={2} missing={3} audit_missing={4} queued={5}" -f $round, $imported, $partial, $movedMiss, $auditMiss, $queued)
  if (($imported -le 0) -and ($partial -le 0) -and ($queued -le 0) -and ($movedMiss -le 0) -and ($auditMiss -le 0) -and $round -ge 2) { break }
}

Write-Host ""
Write-Host "========== XONG (1 LAN — KHONG cai hourly) =========="
Write-Host ("SAU: INBOX={0} MISSING={1} ERROR={2} PROCESSED={3}" -f (Count-Pdf $Inbox), (Count-Pdf $Missing), (Count-Pdf $ErrorDir), (Count-Pdf $Processed))
Write-Host "MISSING   = PDF chua khop TTHC dung (bao bo phan nhap / doi PDF moi)"
Write-Host "ERROR     = co TTHC nhung PDF chi 1 phan (da nhap phan co)"
Write-Host "PROCESSED = FULL + da khop TTHC dung"
Write-Host ""
Write-Host "Neu BN bi nhap CLS SAI tren web:"
Write-Host "  1) Mo form CLS dung BN sai → xoa het ket qua CLS"
Write-Host "  2) De PDF o MISSING/INBOX; khi TTHC dung → chay lai script nay hoac tha PDF moi"
Write-Host "  3) He thong se import de len (web trong thi ghi lai)"
Write-Host "List MISSING: build for Supper Data\excel_preview\missing_can_tthc.txt"
Write-Host ("Exit={0}" -f $code)
Write-Host "===================================================="
if ($code -ne 0) { exit $code }
exit 0
