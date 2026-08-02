# ============================================================
# CHAY TOAN BO 1 LAN + BAT LICH MOI 1 GIO
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

Write-Host "==== 4/5 REPAIR + IMPORT TOAN BO (co the mat nhieu phut) ===="
Write-Host "Import PDF moi + ghi de form thieu (nuoc tieu Am tinh->Negative, Ure, ...)"
$out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host $_ }

$logDir = ".\pipeline\work\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("chay_mot_lan-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
try { $out | Out-File -FilePath $log -Encoding utf8 } catch {}
Write-Host "Repair exit: $code  log: $log"

Write-Host "==== 5/5 BAT TASK MOI 1 GIO + CHAY NGAY ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "Da chay repair 1 lan + cai PKDK_Hourly_Sync (moi 1 gio)."
Write-Host "Laptop can BAT + dang nhap Windows de Task Scheduler chay."
Write-Host "PDF moi: tha vao INBOX_CLS (Google Drive sync)."
Write-Host "Excel: build for Supper Data\excel_preview\CLS_auto_import_*.xlsx"
Write-Host "Kiem tra task:"
Write-Host "  Get-ScheduledTask -TaskName PKDK_Hourly_Sync"
Write-Host "=========================="

if ($code -ne 0) { exit $code }
