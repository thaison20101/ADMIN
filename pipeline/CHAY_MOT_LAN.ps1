# ============================================================
# CHAY 1 LAN DUY NHAT — keo code moi + sua IMPORTED ao + import + bat hourly
# Copy ca khoi lenh ben duoi vao PowerShell (khong can chay tung buoc).
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_MOT_LAN.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:MEDINET_USER = if ($env:MEDINET_USER) { $env:MEDINET_USER } else { "pkdkthuankieu" }
$env:MEDINET_PASS = if ($env:MEDINET_PASS) { $env:MEDINET_PASS } else { "P@ssw0rd" }
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

Write-Host "==== 1/5 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f
if ($LASTEXITCODE -ne 0) { Write-Host "WARN: git pull failed — tiep tuc neu code da co san" }

Write-Host "==== 2/5 config.local.json (date_to = today) ===="
if (-not (Test-Path ".\pipeline\config.local.json")) {
  Copy-Item ".\pipeline\config.example.json" ".\pipeline\config.local.json" -Force
}
python -c @"
import json
from pathlib import Path
p = Path('pipeline/config.local.json')
cfg = json.loads(p.read_text(encoding='utf-8-sig'))
cfg.setdefault('drive', {})
cfg['drive'].setdefault('local_sync_root', r'G:/Drive của tôi/PKDK_Thuankieu_Pipeline')
cfg['drive'].setdefault('build_root', r'G:/Drive của tôi/build for Supper Data')
cfg.setdefault('medinet', {})
cfg['medinet']['date_from'] = cfg['medinet'].get('date_from') or '01/07/2026'
cfg['medinet']['date_to'] = ''  # today
cfg.setdefault('import_rules', {})
cfg['import_rules']['enabled'] = True
cfg['import_rules']['auto_hourly'] = True
cfg['import_rules']['max_imports_per_run'] = 200
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
print('config OK', cfg['drive'].get('local_sync_root'), 'date_to=today')
"@

Write-Host "==== 3/5 pip deps ===="
python -m pip install -q -r .\pipeline\requirements.txt

Write-Host "==== 4/5 REPAIR + IMPORT (co the mat nhieu phut) ===="
Write-Host "Se: quet INBOX/PROCESSED, sua IMPORTED ao, import case web dang trong"
$out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
$code = $LASTEXITCODE
$out | ForEach-Object { Write-Host $_ }
$logDir = ".\pipeline\work\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("chay_mot_lan-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
try { $out | Out-File -FilePath $log -Encoding utf8 } catch {}
Write-Host "Repair exit: $code  log: $log"

Write-Host "==== 5/5 cai Task Scheduler hourly ===="
powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"

Write-Host ""
Write-Host "========== XONG =========="
Write-Host "1) Mo Excel moi nhat: build for Supper Data\excel_preview\CLS_auto_import_*.xlsx"
Write-Host "2) Cot import_status can thay IMPORTED nhieu, ERROR_IMPORT giam"
Write-Host "3) Tren web: mo BN -> Ctrl+F5 form Khám cận lâm sàng"
Write-Host "4) Sau nay chi can: thả PDF vao INBOX_CLS + de laptop BAT"
Write-Host "Task: PKDK_Hourly_Sync (moi 1 gio)"
Write-Host "=========================="
