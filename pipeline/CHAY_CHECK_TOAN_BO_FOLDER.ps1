# ============================================================
# 1 LENH: CHECK TOAN BO FOLDER + BAT HOURLY MOI 1 GIO
# Rule:
#  - Nhap TAT CA field co tren PDF (tru Ure)
#  - PDF FULL (mau + sinh hoa) -> PROCESSED
#  - PDF chi nuoc tieu / thieu 1 phan -> van nhap phan co, roi ERROR
#  - Chua co TTHC -> giu INBOX
#  - Cuoi cung: cai/cap nhat Task Scheduler PKDK_Hourly_Sync
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_CHECK_TOAN_BO_FOLDER.ps1
#
# PowerShell Admin. KHONG click vao cua so khi dang chay.
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }

function Count-Pdf([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return 0 }
  return @(Get-ChildItem -LiteralPath $Path -Recurse -Filter *.pdf -ErrorAction SilentlyContinue).Count
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  CHECK TOAN BO FOLDER + IMPORT + HOURLY MOI 1 GIO      #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/5 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f

Write-Host "==== 2/5 config ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"

$cfgOut = & python -c "import json;from pathlib import Path;c=json.loads(Path('pipeline/config.local.json').read_text(encoding='utf-8-sig'));s=c['drive']['local_sync_root'];print(s);print(s+'\\'+c['drive']['inbox_folder']);print(s+'\\'+c['drive']['error_folder']);print(s+'\\'+c['drive']['processed_folder'])"
$lines = @($cfgOut)
$Inbox = $lines[1]
$ErrorDir = $lines[2]
$Processed = $lines[3]

Write-Host ("TRUOC: INBOX={0} ERROR={1} PROCESSED={2}" -f (Count-Pdf $Inbox), (Count-Pdf $ErrorDir), (Count-Pdf $Processed))

Write-Host "==== 3/5 RESET toan bo INBOX+ERROR+PROCESSED ===="
& python ".\pipeline\reset_all_folders.py" --include-processed

Write-Host "==== 4/5 REPAIR/IMPORT nhieu vong ===="
Write-Host "FULL -> PROCESSED | PARTIAL/URINE_ONLY -> ERROR (van nhap phan co) | no TTHC -> INBOX"
Write-Host "LUU Y: moi vong co the mat nhieu phut (index Medinet). KHONG click vao cua so."
$code = 0
for ($round = 1; $round -le 10; $round++) {
  Write-Host ("----- VONG {0}/10 -----" -f $round)
  $out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $text = ($out | Out-String)
  $imported = 0
  $queued = 0
  $partial = 0
  if ($text -match "'imported':\s*(\d+)") { $imported = [int]$Matches[1] }
  if ($text -match "'queued':\s*(\d+)") { $queued = [int]$Matches[1] }
  if ($text -match "'queued_incomplete':\s*(\d+)") { $queued += [int]$Matches[1] }
  if ($text -match "'imported_partial_to_error':\s*(\d+)") { $partial = [int]$Matches[1] }
  Write-Host ("Vong {0}: imported={1} partial_to_error={2} queued={3}" -f $round, $imported, $partial, $queued)
  if (($imported -le 0) -and ($partial -le 0) -and ($queued -le 0) -and $round -ge 2) { break }
}

Write-Host "==== 5/5 CAI / CAP NHAT HOURLY PKDK_Hourly_Sync ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$codeTask = $LASTEXITCODE
if ($codeTask -ne 0) {
  Write-Host "WARN: chua cai duoc hourly (can Run as administrator)."
  Write-Host "Chay lai: .\pipeline\install_hourly_task.ps1"
}

Write-Host ""
Write-Host "========== XONG =========="
Write-Host ("SAU: INBOX={0} ERROR={1} PROCESSED={2}" -f (Count-Pdf $Inbox), (Count-Pdf $ErrorDir), (Count-Pdf $Processed))
Write-Host "INBOX = chua co TTHC"
Write-Host "ERROR = chi nuoc tieu / thieu 1 phan (da nhap phan co tren PDF)"
Write-Host "PROCESSED = du mau + sinh hoa (tru Ure)"
Write-Host "Hourly: Get-ScheduledTask -TaskName PKDK_Hourly_Sync"
Write-Host ("Exit import={0} task={1}" -f $code, $codeTask)
Write-Host "=========================="
if ($codeTask -ne 0) { exit $codeTask }
if ($code -ne 0) { exit $code }
exit 0
