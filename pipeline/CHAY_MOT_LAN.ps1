# ============================================================
# CHAY 1 LAN — pull code + repair import + bat hourly
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_MOT_LAN.ps1
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

Write-Host "==== 1/5 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f
if ($LASTEXITCODE -ne 0) {
  Write-Host "WARN: git pull failed - tiep tuc neu code da co san"
}

Write-Host "==== 2/5 config.local.json ===="
& python ".\pipeline\ensure_config.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "ERROR: ensure_config.py failed"
  exit 1
}

Write-Host "==== 3/5 pip deps ===="
& python -m pip install -q -r ".\pipeline\requirements.txt"

Write-Host "==== 4/5 REPAIR + IMPORT (co the mat nhieu phut) ===="
Write-Host "Se: quet INBOX/PROCESSED, sua case thieu nuoc tieu (Am tinh -> Negative)"
$out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host $_ }

$logDir = ".\pipeline\work\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("chay_mot_lan-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
try { $out | Out-File -FilePath $log -Encoding utf8 } catch {}
Write-Host "Repair exit: $code  log: $log"

Write-Host "==== 5/5 cai Task Scheduler hourly ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "1) Mo Excel moi nhat trong build for Supper Data\excel_preview\"
Write-Host "2) Cot message khong con SET-no-urine-text; nuoc tieu = Negative"
Write-Host "3) Tren web: Ctrl+F5 form Kham can lam sang"
Write-Host "4) Sau nay: tha PDF vao INBOX_CLS + de laptop BAT"
Write-Host "Task: PKDK_Hourly_Sync"
Write-Host "=========================="

if ($code -ne 0) { exit $code }
