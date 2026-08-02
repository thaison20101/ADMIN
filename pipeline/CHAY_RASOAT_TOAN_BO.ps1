# ============================================================
# 1 LENH: rasoat TOAN BO PDF (INBOX + ERROR + PROCESSED)
#  - thieu Urobilinogen tren web
#  - da co TTHC ma chua import CLS
#  roi REPAIR uro + IMPORT cac case con thieu
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_RASOAT_TOAN_BO.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }

Write-Host ""
Write-Host "############################################################"
Write-Host "#  RASOAT + REPAIR + IMPORT TOAN BO                       #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/5 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f

Write-Host "==== 2/5 config ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"

Write-Host "==== 3/5 RASOAT (INBOX+ERROR+PROCESSED) ===="
& python ".\pipeline\rasoat_toan_bo.py"
$codeAudit = $LASTEXITCODE

Write-Host "==== 4/5 REPAIR Urobilinogen (doi don vi dung + ghi web) ===="
& python ".\pipeline\repair_urobilinogen.py" --all
$codeUro = $LASTEXITCODE

Write-Host "==== 5/5 IMPORT case co TTHC / thieu CLS (nhieu vong) ===="
$maxRounds = 6
$codeImp = 0
for ($round = 1; $round -le $maxRounds; $round++) {
  Write-Host ("----- IMPORT VONG {0}/{1} -----" -f $round, $maxRounds)
  $out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
  $codeImp = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $text = ($out | Out-String)
  $queued = 0
  $imported = 0
  if ($text -match "'queued':\s*(\d+)") { $queued = [int]$Matches[1] }
  if ($text -match "'imported':\s*(\d+)") { $imported = [int]$Matches[1] }
  Write-Host ("Vong {0}: imported={1} queued={2}" -f $round, $imported, $queued)
  if (($queued -le 0) -and ($imported -le 0)) { break }
  if ($queued -le 0) { break }
}

Write-Host "==== RASOAT LAI sau repair/import ===="
& python ".\pipeline\rasoat_toan_bo.py"
$codeFinal = $LASTEXITCODE

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "Xem list:"
Write-Host "  build for Supper Data\excel_preview\rasoat_thieu_urobilinogen.txt"
Write-Host "  build for Supper Data\excel_preview\rasoat_tthc_chua_import.txt"
Write-Host ("Exit audit={0} uro={1} import={2} final={3}" -f $codeAudit, $codeUro, $codeImp, $codeFinal)
Write-Host "Muc tieu: Web THIEU Uro ~0 va Chua import CLS giam dan."
Write-Host "=========================="

if ($codeFinal -ne 0) { exit $codeFinal }
if ($codeUro -ne 0) { exit $codeUro }
exit 0
