# ============================================================
# BO SUNG field con thieu (vd Duong mau / HC) cho PDF da vao PROCESSED
# hoac con INBOX — dung --repair + extract Glucose multiline moi.
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_BO_SUNG_THIEU.ps1
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
Write-Host "#  BO SUNG FIELD THIEU (Glucose/HC/... ; bo qua Ure)     #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/3 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f

Write-Host "==== 2/3 reset INBOX/ERROR + repair ===="
& python ".\pipeline\ensure_config.py"
& python ".\pipeline\reset_inbox_queue.py"

Write-Host "==== 3/3 repair nhieu vong (dien field thieu, move PROCESSED khi du) ===="
$code = 0
for ($round = 1; $round -le 6; $round++) {
  Write-Host ("----- VONG {0}/6 -----" -f $round)
  $out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $text = ($out | Out-String)
  $imported = 0
  $incomplete = 0
  if ($text -match "'imported':\s*(\d+)") { $imported = [int]$Matches[1] }
  if ($text -match "'repair_incomplete':\s*(\d+)") { $incomplete = [int]$Matches[1] }
  Write-Host ("Vong {0}: imported={1} repair_incomplete={2}" -f $round, $imported, $incomplete)
  if (($imported -le 0) -and ($incomplete -le 0) -and $round -ge 2) { break }
}

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "Kiem tra TRINH THE NU: Duong mau tren web phai = 3,98 (Ure co the trong)."
Write-Host "Ctrl+F5 form CLS."
Write-Host "=========================="
if ($code -ne 0) { exit $code }
