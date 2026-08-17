# ============================================================
# BO SUNG TOAN BO FIELD TU PDF LEN WEB (binh thuong + bat thuong)
#
# - Doc LAI moi PDF trong toan bo pipeline (INBOX/MISSING/ERROR/PROCESSED/...)
# - Lay TAT CA truong co tren PDF (ca cot Ket qua lan Ghi chu bat thuong)
# - Dien len web; Ure bo qua neu PDF khong co
# - Ky quet: 01/07/2026 -> hom nay
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_BO_SUNG_THIEU.ps1
#
# KHONG click vao cua so khi dang chay.
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

Write-Host ""
Write-Host "############################################################"
Write-Host "#  BO SUNG FIELD TU PDF (ALL folders) - binh thuong+bat thuong #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/3 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f

Write-Host "==== 2/3 config ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"

Write-Host "==== 3/3 FULL SCAN + REPAIR (nhieu vong) ===="
Write-Host "Quet TOAN BO G:\Drive cua toi\PKDK_Thuankieu_Pipeline"
Write-Host "Dien moi truong PDF len web (MCV/MCH/MCHC/Hb/... ke ca Ghi chu bat thuong)"
Write-Host "Ure: chi dien neu PDF co; khong block."
$code = 0
for ($round = 1; $round -le 4; $round++) {
  Write-Host ("----- VONG {0}/4 -----" -f $round)
  $out = & python ".\pipeline\hourly_sync.py" --full-scan --repair 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $text = ($out | Out-String)
  $imported = 0
  $incomplete = 0
  $queued = 0
  if ($text -match "'imported':\s*(\d+)") { $imported = [int]$Matches[1] }
  if ($text -match "'repair_incomplete':\s*(\d+)") { $incomplete = [int]$Matches[1] }
  if ($text -match "'repair_empty':\s*(\d+)") { $incomplete += [int]$Matches[1] }
  if ($text -match "'queued':\s*(\d+)") { $queued = [int]$Matches[1] }
  if ($text -match "'queued_incomplete':\s*(\d+)") { $queued += [int]$Matches[1] }
  Write-Host ("Vong {0}: imported={1} repair={2} queued={3}" -f $round, $imported, $incomplete, $queued)
  if (($incomplete -le 0) -and ($queued -le 0) -and $round -ge 2) { break }
}

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "Vi du TRAN THI KIM OANH: MCV=76.7 MCH=22.4 MCHC=292 Hb=96.8 (tu PDF, ca bat thuong)."
Write-Host "Ctrl+F5 form CLS de xem lai."
Write-Host "=========================="
if ($code -ne 0) { exit $code }
exit 0
