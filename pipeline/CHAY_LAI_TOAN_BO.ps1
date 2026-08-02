# ============================================================
# QUET LAI TOAN BO: ERROR + case thieu truong (Urobilinogen, Ure, ...)
# Import bo sung, roi chuyen PDF thanh cong sang PROCESSED.
#
#   cd C:\Users\thais\ADMIN
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

Write-Host "==== 2/4 config + pip ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"

Write-Host "==== 3/4 REPAIR TOAN BO (ERROR + thieu Urobilinogen/Ure/nuoc tieu) ===="
Write-Host "Co the mat nhieu phut (~290 PDF trong ERROR + case thieu truong)..."
$out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host $_ }

$logDir = ".\pipeline\work\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("chay_lai_toan_bo-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
try { $out | Out-File -FilePath $log -Encoding utf8 } catch {}
Write-Host "Exit: $code  log: $log"

Write-Host "==== 4/4 dam bao task moi 1 gio ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "Kiem tra BN QUACH XUAN HUONG (914619): Ctrl+F5 — Urobilinogen = 3.38"
Write-Host "PDF OK se chuyen ERROR -> PROCESSED"
Write-Host "Dem PROCESSED:"
Write-Host '  (Get-ChildItem "G:\Drive cua toi\PKDK_Thuankieu_Pipeline\PROCESSED" -Filter *.pdf -File).Count'
Write-Host "=========================="

if ($code -ne 0) { exit $code }
