# ============================================================
# KIEM TRA + IMPORT LAI TOAN BO (INBOX + ERROR)
#  - TTHC da nhap day du tren Medinet nhung PDF van ket INBOX
#  - Reset hang doi -> repair nhieu vong -> chuyen PROCESSED
#  - Khong bo sot WAITING_ADMIN / SKIP / IMPORTED con trong INBOX
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_KIEM_TRA_TOAN_BO.ps1
#
# Co the mat 30-90 phut (hang tram / nghin PDF). De cua so chay, KHONG click vao.
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

function Count-Pdf([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return 0 }
  return @(Get-ChildItem -LiteralPath $Path -Recurse -Filter *.pdf -ErrorAction SilentlyContinue).Count
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  KIEM TRA TOAN BO INBOX/ERROR + IMPORT LAI              #"
Write-Host "############################################################"
Write-Host ""

Write-Host "==== 1/6 git pull ===="
git pull origin cursor/drive-hourly-pipeline-df0f
if ($LASTEXITCODE -ne 0) { Write-Host "WARN: git pull failed - tiep tuc neu code da co" }

Write-Host "==== 2/6 config + pip ===="
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"

# Resolve Drive folders for before/after counts (print_drive_dirs - never ADMIN)
$cfgOut = & python ".\pipeline\print_drive_dirs.py"
$lines = @($cfgOut)
$SyncRoot = if ($lines.Count -ge 1) { $lines[0] } else { "G:\Drive cua toi\PKDK_Thuankieu_Pipeline" }
$Inbox = if ($lines.Count -ge 2) { $lines[1] } else { Join-Path $SyncRoot "INBOX_CLS" }
$ErrorDir = if ($lines.Count -ge 3) { $lines[2] } else { Join-Path $SyncRoot "ERROR" }
$Processed = if ($lines.Count -ge 4) { $lines[3] } else { Join-Path $SyncRoot "PROCESSED" }
if ($SyncRoot -match '(?i)^[CD]:\\' -or $SyncRoot -notmatch '(?i)^G:') {
  Write-Host "DUNG: sync khong phai G: ($SyncRoot). KHONG fallback ADMIN."
  exit 2
}
& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san. Mo Google Drive Desktop roi chay lai."
  exit 2
}

$nIn0 = Count-Pdf $Inbox
$nEr0 = Count-Pdf $ErrorDir
$nPr0 = Count-Pdf $Processed
Write-Host ("TRUOC: INBOX={0} ERROR={1} PROCESSED={2}" -f $nIn0, $nEr0, $nPr0)

Write-Host "==== 3/6 RESET toan bo PDF con trong INBOX/ERROR ===="
& python ".\pipeline\reset_inbox_queue.py"
$codeReset = $LASTEXITCODE

Write-Host "==== 4/6 IMPORT/REPAIR nhieu vong (toi da 12) ===="
$logDir = ".\pipeline\work\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$codeImp = 0
$maxRounds = 12
$totalImported = 0

for ($round = 1; $round -le $maxRounds; $round++) {
  Write-Host ""
  Write-Host ("----- VONG {0}/{1} -----" -f $round, $maxRounds)
  $out = & python ".\pipeline\hourly_sync.py" --repair 2>&1
  $codeImp = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $log = Join-Path $logDir ("kiem_tra_toan_bo-r{0}-{1}.log" -f $round, $stamp)
  try { $out | Out-File -FilePath $log -Encoding utf8 } catch {}

  $text = ($out | Out-String)
  $queued = 0
  $imported = 0
  $waiting = 0
  $tidy = 0
  if ($text -match "'queued':\s*(\d+)") { $queued = [int]$Matches[1] }
  if ($text -match "'queued_incomplete':\s*(\d+)") { $queued += [int]$Matches[1] }
  if ($text -match "'imported':\s*(\d+)") { $imported = [int]$Matches[1] }
  if ($text -match "'waiting_admin':\s*(\d+)") { $waiting = [int]$Matches[1] }
  if ($text -match "'skip_already_cls':\s*(\d+)") { $tidy += [int]$Matches[1] }
  $totalImported += $imported
  Write-Host ("Vong {0}: imported={1} queued={2} waiting_admin={3} log={4}" -f $round, $imported, $queued, $waiting, $log)

  if (($queued -le 0) -and ($imported -le 0)) {
    Write-Host "Het hang doi import - dung vong."
    break
  }
}

Write-Host "==== 5/6 RASOAT con thieu ===="
& python ".\pipeline\rasoat_toan_bo.py"
$codeAudit = $LASTEXITCODE

Write-Host "==== 6/6 Task hourly ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$codeTask = $LASTEXITCODE

$nIn1 = Count-Pdf $Inbox
$nEr1 = Count-Pdf $ErrorDir
$nPr1 = Count-Pdf $Processed

Write-Host ""
Write-Host "========== XONG =========="
Write-Host ("TRUOC: INBOX={0} ERROR={1} PROCESSED={2}" -f $nIn0, $nEr0, $nPr0)
Write-Host ("SAU  : INBOX={0} ERROR={1} PROCESSED={2}" -f $nIn1, $nEr1, $nPr1)
Write-Host ("Imported tong cac vong: {0}" -f $totalImported)
Write-Host "Con trong INBOX = dang cho TTHC that su chua khop, hoac PDF loi parse."
Write-Host "List chi tiet:"
Write-Host "  build for Supper Data\excel_preview\rasoat_tthc_chua_import.txt"
Write-Host "  build for Supper Data\excel_preview\rasoat_thieu_urobilinogen.txt"
Write-Host ("Exit reset={0} import={1} audit={2} task={3}" -f $codeReset, $codeImp, $codeAudit, $codeTask)
Write-Host "=========================="

if ($codeReset -ne 0) { exit $codeReset }
if ($codeImp -ne 0) { exit $codeImp }
exit 0
