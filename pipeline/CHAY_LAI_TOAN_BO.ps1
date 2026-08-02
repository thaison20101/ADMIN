# ============================================================
# QUET LAI TOAN BO (nhieu vong cho het hang doi)
#
#   cd C:\Users\thais\ADMIN
#   git pull origin cursor/drive-hourly-pipeline-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_LAI_TOAN_BO.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

Write-Host "==== 1/4 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f
if ($LASTEXITCODE -ne 0) { Write-Host "WARN: git pull failed - tiep tuc" }

if (-not (Test-Path ".\pipeline\CHAY_LAI_TOAN_BO.ps1")) {
  Write-Host "ERROR: van chua co file script. Kiem tra nhanh:"
  Write-Host "  git branch --show-current"
  Write-Host "  git checkout cursor/drive-hourly-pipeline-df0f"
  Write-Host "  git pull origin cursor/drive-hourly-pipeline-df0f"
  exit 1
}

Write-Host "==== 2/4 config + pip ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"

Write-Host "==== 3/4 REPAIR NHIEU VONG (toi da 8) ===="
Write-Host "Moi vong toi da ~800 case. Neu con queued se chay vong tiep."
$logDir = ".\pipeline\work\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$code = 0
$maxRounds = 8

for ($round = 1; $round -le $maxRounds; $round++) {
  Write-Host ""
  Write-Host ("----- VONG {0} / {1} -----" -f $round, $maxRounds)
  $out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $log = Join-Path $logDir ("chay_lai_toan_bo-r{0}-{1}.log" -f $round, $stamp)
  try { $out | Out-File -FilePath $log -Encoding utf8 } catch {}
  Write-Host ("Vong {0} exit={1} log={2}" -f $round, $code, $log)

  $text = ($out | Out-String)
  $queued = 0
  $imported = 0
  if ($text -match "'queued':\s*(\d+)") { $queued = [int]$Matches[1] }
  if ($text -match "'imported':\s*(\d+)") { $imported = [int]$Matches[1] }
  Write-Host ("Vong {0}: imported={1} queued={2}" -f $round, $imported, $queued)

  if (($queued -le 0) -and ($imported -le 0)) {
    Write-Host "Khong con hang doi / khong import them - dung."
    break
  }
  if ($queued -le 0) {
    Write-Host "Hang doi het - dung."
    break
  }
}

Write-Host "==== 4/4 dam bao task moi 1 gio ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "Kiem tra BN 914619 QUACH XUAN HUONG: Ctrl+F5 - Urobilinogen=3.38"
Write-Host "PDF OK: ERROR -> PROCESSED"
Write-Host "=========================="
if ($code -ne 0) { exit $code }
