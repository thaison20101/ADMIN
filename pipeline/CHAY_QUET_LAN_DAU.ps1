# ============================================================
# QUET TOAN BO (LAN DAU / BAT SO BN CU) + BAT HOURLY
#
# Rule:
#  - Quet TOAN BO folder: INBOX + MISSING + ERROR + PROCESSED + folder khac
#  - FULL (mau+sinh hoa, bo Ure) -> PROCESSED
#  - PARTIAL / chi nuoc tieu -> nhap phan co -> ERROR
#  - Khong TTHC -> MISSING
#  - PROCESSED sai / khong khop TTHC (ten+nam sinh+ngay in KQ) -> MISSING
#  - Sau do hourly chi quet INBOX_CLS + MISSING
#  - Ky quet: 01/07/2026 -> hom nay
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

Write-Host ""
Write-Host "############################################################"
Write-Host "#  QUET TOAN BO (MOI FOLDER) + BAT SO BN CU + HOURLY       #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/4 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f

Write-Host "==== 2/4 config + deps ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"

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
Write-Host "Ky quet Medinet: 01/07/2026 -> hom nay (rolling)"
Write-Host "Khop: ten (ho+ten) + nam sinh + ngay in KQ (cho phep in truoc / kham sau)"

Write-Host "==== 3/4 FULL SCAN TOAN BO FOLDER + REPAIR (nhieu vong) ===="
Write-Host "Quet: INBOX + MISSING + ERROR + PROCESSED + moi folder khac"
Write-Host "FULL->PROCESSED | PARTIAL->ERROR | no TTHC->MISSING"
Write-Host "LUU Y: co the mat LAU (hang nghin PDF). KHONG click vao cua so."
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

Write-Host "==== 4/4 CAI / CAP NHAT HOURLY PKDK_Hourly_Sync ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$codeTask = $LASTEXITCODE

Write-Host ""
Write-Host "========== XONG =========="
Write-Host ("SAU: INBOX={0} MISSING={1} ERROR={2} PROCESSED={3}" -f (Count-Pdf $Inbox), (Count-Pdf $Missing), (Count-Pdf $ErrorDir), (Count-Pdf $Processed))
Write-Host "MISSING   = chua co TTHC (bao bo phan nhap) - list: build\excel_preview\missing_can_tthc.txt"
Write-Host "ERROR     = co TTHC nhung PDF chi 1 phan (da nhap phan co)"
Write-Host "PROCESSED = FULL mau + sinh hoa (tru Ure) + da khop TTHC dung"
Write-Host "Hourly tiep theo CHI quet INBOX_CLS + MISSING (tranh quet di quet lai)"
Write-Host "Ky quet: 01/07/2026 -> hom nay"
Write-Host ("Exit import={0} task={1}" -f $code, $codeTask)
Write-Host "=========================="
if ($codeTask -ne 0) { exit $codeTask }
if ($code -ne 0) { exit $code }
exit 0
