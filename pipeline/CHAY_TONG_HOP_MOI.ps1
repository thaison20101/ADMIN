# ============================================================
# 1 LENH DUY NHAT MAY A - PKDK THUAN KIEU (ASCII-only)
#
# Chay 1 lan: FULL 2 bot -> rematch MISSING -> kiem tra lai TOAN BO fillable
#   -> BAT hourly (nguyen tac QUET FILE cu)
# Rule DIEN: moi (hang ngang ten XN; dam/gach van dien; khong lay khoang tham chieu).
#
# 2 TK Medinet (hardcode trong medinet_creds.py + env duoi day):
#   pkdkthuankieu / P@ssw0rd
#   pkdk_Thuankieu / pkdk_Thuankieu#2026
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
  [int]$FullRounds = 3,
  [int]$RematchRounds = 4,
  [int]$MissingBudget = 2500
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
# 2 TK Medinet (cung hardcode trong pipeline/medinet_creds.py)
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }
if (-not $env:MEDINET_USER_2) { $env:MEDINET_USER_2 = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS_2) { $env:MEDINET_PASS_2 = "pkdk_Thuankieu#2026" }

$TaskName = "PKDK_Hourly_Sync"
$Branch = "cursor/hourly-flash-fix-df0f"
$FlagFull = Join-Path $Repo "pipeline\work\build\FIRST_FULL_SCAN_DONE.txt"
$LockDir = Join-Path $Repo "pipeline\work\locks"
$IdxCache = Join-Path $Repo "pipeline\work\index_cache"
$LocalHb = Join-Path $Repo "pipeline\work\logs\LAST_HOURLY_OK.txt"

function Get-Counts {
  $lines = @(& $Python ".\pipeline\print_counts.py" 2>$null)
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
  & $Python ".\pipeline\assert_g_pipeline.py"
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
  $b1 = Start-Process -FilePath $Python -ArgumentList $argsInbox -WorkingDirectory $Repo -PassThru -NoNewWindow
  $b2 = Start-Process -FilePath $Python -ArgumentList $argsMiss -WorkingDirectory $Repo -PassThru -NoNewWindow
  Write-Host ("  Bot INBOX PID={0} | Bot MISSING PID={1} | python={2}" -f $b1.Id, $b2.Id, $Python)
  Wait-Process -Id $b1.Id, $b2.Id -ErrorAction SilentlyContinue
  $c1 = $b1.ExitCode; if ($null -eq $c1) { $c1 = 0 }
  $c2 = $b2.ExitCode; if ($null -eq $c2) { $c2 = 0 }
  return [Math]::Max($c1, $c2)
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  TONG HOP MAY A: FULL RECHECK + HOURLY + SUPER DATA      #"
Write-Host "############################################################"
Write-Host ("Python: " + $Python)
Write-Host ("Branch: " + $Branch)
Write-Host "PDF : G:\Drive cua toi\PKDK_Thuankieu_Pipeline\INBOX_CLS ..."
Write-Host "Theo doi: G:\Drive cua toi\build for Supper Data\TIEN_DO_THEO_DOI.txt"
Write-Host "KHONG click vao cua so PowerShell (Select-pause lam dung)."

if ($ChiCapNhatTienDo) {
  & $Python ".\pipeline\super_data_status.py" --publish
  & $Python ".\pipeline\print_counts.py" | ForEach-Object { Write-Host $_ }
  exit $LASTEXITCODE
}

# ---- 1 TAT hourly ----
Write-Host ""
Write-Host "==== 1/8 TAT hourly + xoa lock ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
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
& $Python ".\pipeline\ensure_config.py"
& $Python -m pip install -q -r ".\pipeline\requirements.txt"

# ---- 3 assert G + dong bo folder ----
Write-Host ""
Write-Host "==== 3/8 assert G: + dong bo folder ===="
Assert-G
& $Python ".\pipeline\drive_paths.py"
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
Write-Host "==== 4/8 FULL SCAN + REPAIR TOAN BO (2 bot) ===="
Write-Host "Rule dien MOI | fillable: INBOX+ERROR+PROCESSED+UNDER18+TK1+TK2"
Write-Host "Route: 2TK+FULL->PROCESSED/U18 | 1TK+FULL->TK1/TK2 | PARTIAL->ERROR | noTTHC->MISSING"
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

# ---- 6 KIEM TRA LAI fillable (SkipPull: giu branch vua pull) ----
Write-Host ""
Write-Host "==== 6/8 KIEM TRA LAI TOAN BO FILLABLE (rule dien moi) ===="
Clear-Locks
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_BO_SUNG_THIEU.ps1" -SkipPull
$bs = $LASTEXITCODE
if ($bs -ne 0) {
  Write-Host "WARN: kiem tra lai exit=$bs (van tiep tuc bat hourly)"
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
  Write-Host "OK: lan sau hourly: INBOX disk + MISSING CSV (nguyen tac quet file cu)"
} catch {
  Write-Host ("WARN flag: " + $_)
}

# ---- 8 BAT hourly + cap nhat G ----
Write-Host ""
Write-Host "==== 8/8 BAT hourly + cap nhat Super Data ===="
Write-Host "Clear python/lock truoc khi Start task (tranh abort=another_instance)."
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Clear-Locks

& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
# install_hourly_task da Start 1 lan - KHONG Start trung

Write-Host "Doi heartbeat ~25s (phat hien nhay tat som)..."
Start-Sleep -Seconds 25
$hbPaths = @($LocalHb)
try {
  $br = Join-Path $env:TEMP "pkdk_build_root.txt"
  if (Test-Path -LiteralPath $br) {
    $build = (Get-Content -LiteralPath $br -Encoding UTF8 -Raw).Trim()
    $hbPaths += (Join-Path $build "logs\LAST_HOURLY_OK.txt")
  }
} catch {}
$sawHb = $false
foreach ($hp in $hbPaths) {
  if (Test-Path -LiteralPath $hp) {
    $sawHb = $true
    Write-Host ("--- HEARTBEAT " + $hp + " ---")
    Get-Content -LiteralPath $hp -Encoding UTF8
    $txt = Get-Content -LiteralPath $hp -Raw -Encoding UTF8
    if ($txt -match "duration_s=(\d+)") {
      $dur = [int]$Matches[1]
      if ($dur -ge 0 -and $dur -lt 15) {
        Write-Host "!! Hourly van NHAY (duration_s<$dur). Chay: .\pipeline\CHAY_KIEM_HOURLY.ps1"
      }
    }
    if ($txt -match "abort=([^\r\n]+)" -and $Matches[1].Trim() -ne "") {
      Write-Host ("!! abort=" + $Matches[1].Trim() + " - xem CHAY_KIEM_HOURLY.ps1")
    }
  }
}
if (-not $sawHb) {
  Write-Host "WARN: chua co LAST_HOURLY_OK - task co the van dang chay (OK neu State=Running)."
  try {
    $st = (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
    Write-Host ("Task State: " + $st)
  } catch {}
}

& $Python ".\pipeline\super_data_status.py" --publish

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
Write-Host "Nghiem thu: form VONG QUOC CHU phai co MCHC/RDW neu PDF co."
Write-Host "2 bot rieng (khong full): .\pipeline\CHAY_2_BOT_SONG_SONG.ps1"
if ($code -ne 0) { exit $code }
exit 0
