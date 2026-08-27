# ============================================================
# 1 LENH DUY NHAT MAY A - PKDK THUAN KIEU (ASCII-only)
#
# Chay 1 lan: FULL 2 bot -> rematch MISSING -> Urea -> BAT hourly
# Sau do hourly tu quet INBOX_CLS + MISSING nhu cu.
#
# 2 TK Medinet (hardcode trong medinet_creds.py + env duoi day):
#   pkdkthuankieu / P@ssw0rd
#   pkdk_Thuankieu / pkdk_Thuankieu#2026
#
# Gom tat ca:
#   - Tat hourly + xoa lock
#   - git pull code moi
#   - Dong bo folder G: + build for Supper Data
#   - FULL quet (2 bot song song: INBOX + MISSING, tranh trung)
#   - Rematch MISSING (2 bot)
#   - Bo sung Urea/field thieu
#   - Bat hourly ngay
#   - Cap nhat TIEN_DO -> G:\Drive cua toi\build for Supper Data
#
# Rule (dong bo run_hourly / auto_cycle):
#   Match: ho+ten DAY DU + nam/ngay sinh/SDT/CCCD (thieu OK neu khong conflict)
#   Unique ten khong param -> dien | trung ten >=2 -> UNDER 18
#   Dual-write CLS ca 2 TK khi ca 2 co TTHC
#   2TK+FULL -> PROCESSED/U18 | 1TK+FULL -> TK1/TK2
#   PARTIAL/mau khac -> ERROR | no TTHC -> MISSING
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_TONG_HOP_MOI.ps1
#
# Chi cap nhat theo doi (khong chay bot):
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_TONG_HOP_MOI.ps1 -ChiCapNhatTienDo
# ============================================================

param(
  [switch]$SkipPull,
  [switch]$ChiCapNhatTienDo,
  [int]$FullRounds = 2,
  [int]$RematchRounds = 4,
  [int]$MissingBudget = 2500
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
# 2 TK Medinet (cung hardcode trong pipeline/medinet_creds.py)
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }
if (-not $env:MEDINET_USER_2) { $env:MEDINET_USER_2 = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS_2) { $env:MEDINET_PASS_2 = "pkdk_Thuankieu#2026" }

$TaskName = "PKDK_Hourly_Sync"
$Branch = "cursor/drive-hourly-pipeline-df0f"
$FlagFull = Join-Path $Repo "pipeline\work\build\FIRST_FULL_SCAN_DONE.txt"
$LockDir = Join-Path $Repo "pipeline\work\locks"
$IdxCache = Join-Path $Repo "pipeline\work\index_cache"

function Get-Counts {
  $lines = @(& python ".\pipeline\print_counts.py" 2>$null)
  $counts = ($lines | Select-Object -Last 1)
  $parts = @($counts -split "\t")
  $o = @{ inbox = 0; missing = 0; error = 0; processed = 0; under18 = 0; raw = $counts }
  foreach ($p in $parts) {
    if ($p -match "^inbox=(\d+)$") { $o.inbox = [int]$Matches[1] }
    if ($p -match "^missing=(\d+)$") { $o.missing = [int]$Matches[1] }
    if ($p -match "^error=(\d+)$") { $o.error = [int]$Matches[1] }
    if ($p -match "^processed=(\d+)$") { $o.processed = [int]$Matches[1] }
    if ($p -match "^under18=(\d+)$") { $o.under18 = [int]$Matches[1] }
  }
  return $o
}

function Clear-Locks {
  if (-not (Test-Path -LiteralPath $LockDir)) { return }
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
  $claimDir = Join-Path $LockDir "claims"
  if (Test-Path -LiteralPath $claimDir) {
    Get-ChildItem -LiteralPath $claimDir -Filter "*.claim" -ErrorAction SilentlyContinue |
      Remove-Item -Force -ErrorAction SilentlyContinue
  }
}

function Assert-G {
  & python ".\pipeline\assert_g_pipeline.py"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "DUNG: G: chua san. Mo Google Drive Desktop. KHONG bat hourly."
    exit 2
  }
}

function Start-TwoBots {
  param(
    [string[]]$ExtraInbox = @(),
    [string[]]$ExtraMissing = @("--missing-budget", "$MissingBudget")
  )
  $argsInbox = @("-u", ".\pipeline\hourly_sync.py", "--bot", "inbox", "--missing-budget", "0") + $ExtraInbox
  $argsMiss = @("-u", ".\pipeline\hourly_sync.py", "--bot", "missing") + $ExtraMissing
  $b1 = Start-Process -FilePath "python" -ArgumentList $argsInbox -WorkingDirectory $Repo -PassThru -NoNewWindow
  $b2 = Start-Process -FilePath "python" -ArgumentList $argsMiss -WorkingDirectory $Repo -PassThru -NoNewWindow
  Write-Host ("  Bot INBOX PID={0} | Bot MISSING PID={1}" -f $b1.Id, $b2.Id)
  Wait-Process -Id $b1.Id, $b2.Id -ErrorAction SilentlyContinue
  $c1 = $b1.ExitCode; if ($null -eq $c1) { $c1 = 0 }
  $c2 = $b2.ExitCode; if ($null -eq $c2) { $c2 = 0 }
  return [Math]::Max($c1, $c2)
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  TONG HOP MAY A: 2 BOT + FULL + HOURLY + SUPER DATA      #"
Write-Host "############################################################"
Write-Host "PDF : G:\Drive cua toi\PKDK_Thuankieu_Pipeline\INBOX_CLS ..."
Write-Host "Theo doi: G:\Drive cua toi\build for Supper Data\TIEN_DO_THEO_DOI.txt"
Write-Host "KHONG click vao cua so PowerShell (Select-pause lam dung)."

if ($ChiCapNhatTienDo) {
  & python ".\pipeline\super_data_status.py" --publish
  & python ".\pipeline\print_counts.py" | ForEach-Object { Write-Host $_ }
  exit $LASTEXITCODE
}

# ---- 1 TAT hourly ----
Write-Host ""
Write-Host "==== 1/8 TAT hourly + xoa lock ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
Clear-Locks

# ---- 2 git pull ----
Write-Host ""
Write-Host "==== 2/8 git pull ($Branch) ===="
if (-not $SkipPull) {
  if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
    git fetch origin
    git checkout $Branch
    git pull origin $Branch
  }
}
& python ".\pipeline\ensure_config.py"
& python -m pip install -q -r ".\pipeline\requirements.txt"

# ---- 3 assert G + dong bo folder ----
Write-Host ""
Write-Host "==== 3/8 assert G: + dong bo folder ===="
Assert-G
& python ".\pipeline\drive_paths.py"
if (Test-Path -LiteralPath $IdxCache) {
  Get-ChildItem -LiteralPath $IdxCache -Filter "*.pkl" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}
if (Test-Path -LiteralPath $FlagFull) {
  Remove-Item -LiteralPath $FlagFull -Force -ErrorAction SilentlyContinue
}
Write-Host ("COUNTS truoc: {0}" -f (Get-Counts).raw)

# ---- 4 FULL SCAN 2 bot (nhieu vong) ----
Write-Host ""
Write-Host "==== 4/8 FULL SCAN + REPAIR (2 bot song song) ===="
Write-Host "Rule: ho+ten day du + nam/SDT/CCCD | dual-write 2 TK"
  Write-Host "Route: 2TK+FULL->PROCESSED/U18 | 1TK+FULL->TK1/TK2 | PARTIAL/OTHER->ERROR | noTTHC->MISSING | trung ten->UNDER18"
$code = 0
for ($r = 1; $r -le $FullRounds; $r++) {
  Write-Host ("----- FULL vong {0}/{1} -----" -f $r, $FullRounds)
  Assert-G
  $before = Get-Counts
  Write-Host ("COUNTS before: {0}" -f $before.raw)
  $code = Start-TwoBots -ExtraInbox @("--full-scan", "--repair") -ExtraMissing @(
    "--full-scan", "--repair", "--missing-budget", "$MissingBudget"
  )
  $after = Get-Counts
  Write-Host ("COUNTS after : {0}" -f $after.raw)
  if ($r -ge 2 -and ($after.inbox -eq $before.inbox) -and ($after.processed -eq $before.processed) -and ($after.error -eq $before.error)) {
    Write-Host "FULL het tien do."
    break
  }
}

# ---- 5 REMATCH MISSING 2 bot ----
Write-Host ""
Write-Host "==== 5/8 REMATCH MISSING (2 bot, CSV khong list 10k G:) ===="
for ($r = 1; $r -le $RematchRounds; $r++) {
  Write-Host ("----- REMATCH vong {0}/{1} -----" -f $r, $RematchRounds)
  Assert-G
  $before = Get-Counts
  $code = Start-TwoBots -ExtraMissing @("--missing-budget", "$MissingBudget")
  $after = Get-Counts
  $dP = $after.processed - $before.processed
  $dE = $after.error - $before.error
  $dM = $after.missing - $before.missing
  Write-Host ("DELTA processed={0} error={1} missing={2}" -f $dP, $dE, $dM)
  if ($r -ge 2 -and ($dP -eq 0) -and ($dE -eq 0) -and ($dM -eq 0)) { break }
}

# ---- 6 BO SUNG Urea ----
Write-Host ""
Write-Host "==== 6/8 BO SUNG Urea/field thieu ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_BO_SUNG_THIEU.ps1"
$bs = $LASTEXITCODE
if ($bs -ne 0) {
  Write-Host "WARN: bo sung Urea exit=$bs (van tiep tuc bat hourly)"
}

# ---- 7 danh dau full xong ----
Write-Host ""
Write-Host "==== 7/8 Danh dau FIRST_FULL_SCAN_DONE ===="
try {
  $fd = Split-Path -Parent $FlagFull
  if (-not (Test-Path -LiteralPath $fd)) {
    New-Item -ItemType Directory -Force -Path $fd | Out-Null
  }
  Set-Content -LiteralPath $FlagFull -Value ("done=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -Encoding utf8
  Write-Host "OK: lan sau hourly: INBOX disk + MISSING CSV + TK1/TK2 CSV rematch"
} catch {
  Write-Host ("WARN flag: " + $_)
}

# ---- 8 BAT hourly + cap nhat G ----
Write-Host ""
Write-Host "==== 8/8 BAT hourly + cap nhat Super Data ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
try {
  Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Write-Host "OK: Start-ScheduledTask (chay ngay 1 lan)"
} catch {
  & powershell -ExecutionPolicy Bypass -File ".\pipeline\BAT_LAI_HOURLY.ps1"
}
& python ".\pipeline\super_data_status.py" --publish

$final = Get-Counts
Write-Host ""
Write-Host "========== XONG TONG HOP =========="
Write-Host ("COUNTS: {0}" -f $final.raw)
Write-Host ""
Write-Host "Theo doi tren G:"
Write-Host "  G:\Drive cua toi\build for Supper Data\TIEN_DO_THEO_DOI.txt"
Write-Host "  G:\Drive cua toi\build for Supper Data\last_counts.txt"
Write-Host "  G:\Drive cua toi\build for Supper Data\logs\LAST_HOURLY_OK.txt"
Write-Host ""
Write-Host "Folder PDF:"
Write-Host "  INBOX_CLS = moi | MISSING = chua TTHC | ERROR = PARTIAL/mau khac"
Write-Host "  PROCESSED = FULL ca 2 TK | TK1/TK2 = FULL chi 1 TK"
Write-Host "  UNDER 18 = tre FULL / trung ten / loi PDF"
Write-Host ""
Write-Host "2 bot rieng (khong full): .\pipeline\CHAY_2_BOT_SONG_SONG.ps1"
if ($code -ne 0) { exit $code }
exit 0
