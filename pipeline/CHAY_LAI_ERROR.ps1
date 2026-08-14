# ============================================================
# CHI RETRY 5 PDF trong folder ERROR (vd PHAN THI BAO)
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_LAI_ERROR.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "pkdk_Thuankieu#2026" }

Write-Host ""
Write-Host "############################################################"
Write-Host "#  RETRY FOLDER ERROR (import lai + chuyen PROCESSED)    #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/3 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f

Write-Host "==== 2/3 reset hang doi INBOX+ERROR ===="
& python ".\pipeline\ensure_config.py"
& python ".\pipeline\reset_inbox_queue.py"

Write-Host "==== 3/3 repair 3 vong (uu tien ERROR) ===="
$code = 0
for ($round = 1; $round -le 3; $round++) {
  Write-Host ("----- VONG {0}/3 -----" -f $round)
  $out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $text = ($out | Out-String)
  $imported = 0
  if ($text -match "'imported':\s*(\d+)") { $imported = [int]$Matches[1] }
  if ($imported -le 0 -and $round -ge 2) { break }
}

$cfgOut = & python -c "import json;from pathlib import Path;c=json.loads(Path('pipeline/config.local.json').read_text(encoding='utf-8-sig'));s=c['drive']['local_sync_root'];print(s+'\\'+c['drive']['error_folder']);print(s+'\\'+c['drive']['processed_folder'])"
$err = @($cfgOut)[0]
$proc = @($cfgOut)[1]
Write-Host ""
Write-Host "========== XONG =========="
Write-Host ("ERROR con: {0}" -f @(Get-ChildItem -LiteralPath $err -Filter *.pdf -ErrorAction SilentlyContinue).Count)
Write-Host "Kiem tra PHAN THI BAO:"
Write-Host ("  Get-ChildItem '{0}' -Filter '*PHAN THI BAO*'" -f $err)
Write-Host ("  Get-ChildItem '{0}' -Filter '*PHAN THI BAO*'" -f $proc)
Write-Host "Web: Ctrl+F5 form CLS pid=481583 (mau + nuoc tieu)"
Write-Host "=========================="
if ($code -ne 0) { exit $code }
