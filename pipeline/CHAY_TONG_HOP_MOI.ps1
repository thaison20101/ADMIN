# ============================================================
# 1 LENH DUY NHAT MAY A - PKDK THUAN KIEU (ASCII-only)
#
# Chay 1 lan: FULL 2 bot -> rematch MISSING -> kiem tra lai TOAN BO fillable
#   -> BAT hourly (nguyen tac QUET FILE cu)
# Rule DIEN: moi (hang ngang ten XN; dam/gach van dien; khong lay khoang tham chieu).
# Quet TOAN BO PDF: INBOX+ERROR+PROCESSED+UNDER18+TK1+TK2 (chay LAU).
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_TONG_HOP_MOI.ps1
# ============================================================

param(
  [switch]$SkipPull,
  [switch]$ChiCapNhatTienDo,
  [int]$FullRounds = 3,
  [int]$RematchRounds = 4,
  [int]$MissingBudget = 2500,
  [int]$MinRoundSeconds = 180
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python
# May A: self-signed MITM - NEVER verify unless operator overrides
$env:MEDINET_SSL_VERIFY = "0"

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
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
$LogDir = Join-Path $Repo "pipeline\work\logs"
$script:FatalAbort = ""
$script:HadSsl = $false
$script:HadEarlyExit = $false
$script:TkEmpty = $false

function Ensure-LogDir {
  if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  }
}

function Get-Counts {
  $lines = @(& $Python ".\pipeline\print_counts.py" 2>$null)
  $counts = ($lines | Select-Object -Last 1)
  $parts = @($counts -split "\t")
  $o = @{ inbox = 0; missing = 0; error = 0; processed = 0; under18 = 0; tk1 = 0; tk2 = 0; raw = $counts }
  foreach ($p in $parts) {
    if ($p -match "^inbox=(\d+)$") { $o.inbox = [int]$Matches[1] }
    if ($p -match "^missing=(\d+)$") { $o.missing = [int]$Matches[1] }
    if ($p -match "^error=(\d+)$") { $o.error = [int]$Matches[1] }
    if ($p -match "^processed=(\d+)$") { $o.processed = [int]$Matches[1] }
    if ($p -match "^under18=(\d+)$") { $o.under18 = [int]$Matches[1] }
    if ($p -match "^tk1=(\d+)$") { $o.tk1 = [int]$Matches[1] }
    if ($p -match "^tk2=(\d+)$") { $o.tk2 = [int]$Matches[1] }
  }
  return $o
}

function Get-DiskInventory {
  $lines = @(& $Python ".\pipeline\print_disk_counts.py" 2>$null)
  $o = @{
    inbox = 0; missing = 0; error = 0; processed = 0; under18 = 0; tk1 = 0; tk2 = 0
    fillable = 0; archive = 0; work = 0; tk_empty = 0; raw = ($lines -join " | ")
  }
  foreach ($line in $lines) {
    if ($line -match "^DISK\t") {
      foreach ($p in ($line -split "\t")) {
        if ($p -match "^inbox=(\d+)$") { $o.inbox = [int]$Matches[1] }
        if ($p -match "^missing=(\d+)$") { $o.missing = [int]$Matches[1] }
        if ($p -match "^error=(\d+)$") { $o.error = [int]$Matches[1] }
        if ($p -match "^processed=(\d+)$") { $o.processed = [int]$Matches[1] }
        if ($p -match "^under18=(\d+)$") { $o.under18 = [int]$Matches[1] }
        if ($p -match "^tk1=(\d+)$") { $o.tk1 = [int]$Matches[1] }
        if ($p -match "^tk2=(\d+)$") { $o.tk2 = [int]$Matches[1] }
      }
    }
    if ($line -match "^FILLABLE_DISK\t(\d+)$") { $o.fillable = [int]$Matches[1] }
    if ($line -match "^ARCHIVE_DISK\t(\d+)$") { $o.archive = [int]$Matches[1] }
    if ($line -match "^WORK_DISK\t(\d+)$") { $o.work = [int]$Matches[1] }
    if ($line -match "^WARN_TK_EMPTY\t(\d+)$") { $o.tk_empty = [int]$Matches[1] }
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

function Assert-Ssl {
  Write-Host "==== SSL probe (phai OK truoc khi quet toan bo PDF) ===="
  & $Python ".\pipeline\medinet_ssl.py"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "DUNG: Medinet SSL/auth FAIL. KHONG danh FULL_DONE. KHONG bat hourly."
    Write-Host "  Fix: MEDINET_SSL_VERIFY=0 + git pull cursor/hourly-flash-fix-df0f"
    $script:FatalAbort = "ssl_verify"
    $script:HadSsl = $true
    exit 2
  }
  Write-Host "OK: SSL verify OFF + auth Medinet"
}

function Test-LogBlobSsl([string]$Blob) {
  if ($Blob -match "CERTIFICATE_VERIFY_FAILED|SSLCertVerificationError|self-signed certificate") {
    return $true
  }
  return $false
}

function Start-TwoBots {
  param(
    [string]$Tag = "bots",
    [string[]]$ExtraInbox = @(),
    [string[]]$ExtraMissing = @("--missing-budget", "$MissingBudget"),
    [int]$ExpectArchive = 0
  )
  Ensure-LogDir
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $logInbox = Join-Path $LogDir ("tonghop-{0}-inbox-{1}.log" -f $Tag, $stamp)
  $logMiss = Join-Path $LogDir ("tonghop-{0}-miss-{1}.log" -f $Tag, $stamp)
  $argsInbox = @("-u", ".\pipeline\hourly_sync.py", "--bot", "inbox", "--missing-budget", "0") + $ExtraInbox
  $argsMiss = @("-u", ".\pipeline\hourly_sync.py", "--bot", "missing") + $ExtraMissing
  $t0 = Get-Date
  $b1 = Start-Process -FilePath $Python -ArgumentList $argsInbox -WorkingDirectory $Repo `
    -PassThru -NoNewWindow -RedirectStandardOutput $logInbox -RedirectStandardError ($logInbox + ".err")
  $b2 = Start-Process -FilePath $Python -ArgumentList $argsMiss -WorkingDirectory $Repo `
    -PassThru -NoNewWindow -RedirectStandardOutput $logMiss -RedirectStandardError ($logMiss + ".err")
  Write-Host ("  Bot INBOX PID={0} | AUDIT/MISSING PID={1}" -f $b1.Id, $b2.Id)
  Write-Host ("  log_inbox={0}" -f $logInbox)
  Write-Host ("  log_audit={0}" -f $logMiss)
  Wait-Process -Id $b1.Id, $b2.Id -ErrorAction SilentlyContinue
  $sec = [int]((Get-Date) - $t0).TotalSeconds
  $c1 = $b1.ExitCode; if ($null -eq $c1) { $c1 = 0 }
  $c2 = $b2.ExitCode; if ($null -eq $c2) { $c2 = 0 }
  $code = [Math]::Max([int]$c1, [int]$c2)
  Write-Host ("  duration_s={0} exit inbox={1} audit={2}" -f $sec, $c1, $c2)

  $blob = ""
  foreach ($p in @($logInbox, ($logInbox + ".err"), $logMiss, ($logMiss + ".err"))) {
    if (Test-Path -LiteralPath $p) {
      $blob += (Get-Content -LiteralPath $p -Raw -ErrorAction SilentlyContinue)
    }
  }
  if (Test-LogBlobSsl $blob) {
    Write-Host "!! SSL trong log bot - DUNG. Khong coi la quet xong."
    $script:HadSsl = $true
    $script:FatalAbort = "ssl_verify"
    $code = 2
  }
  if ($ExpectArchive -ge 100 -and $sec -lt $MinRoundSeconds -and $code -eq 0) {
    Write-Host ("!! Vong qua NHANH duration_s={0} < {1}s trong khi work/archive~{2} PDF." -f $sec, $MinRoundSeconds, $ExpectArchive)
    Write-Host "   Day la dau hieu abort/skip - KHONG phai quet toan bo that."
    $script:HadEarlyExit = $true
    $script:FatalAbort = "too_fast"
    $code = 2
  }
  if ($blob -match "Re-queued from disk scan dirs: (\d+)") {
    Write-Host ("  requeued_disk={0}" -f $Matches[1])
  }
  if ($blob -match "FILLABLE_SCOPE") {
    Write-Host "  OK: FILLABLE_SCOPE co trong log"
  }
  $dien = ([regex]::Matches($blob, "DIEN OK")).Count
  $partial = ([regex]::Matches($blob, "DIEN PARTIAL")).Count
  Write-Host ("  DIEN OK lines~{0} PARTIAL~{1}" -f $dien, $partial)
  # Tail stderr if failed
  if ($code -ne 0) {
    foreach ($p in @(($logInbox + ".err"), ($logMiss + ".err"))) {
      if (Test-Path -LiteralPath $p) {
        Write-Host ("--- tail {0} ---" -f $p)
        Get-Content -LiteralPath $p -Tail 20 -ErrorAction SilentlyContinue
      }
    }
  }
  return $code
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  TONG HOP MAY A: QUET TOAN BO PDF + HOURLY               #"
Write-Host "############################################################"
Write-Host ("Python: " + $Python)
Write-Host ("Branch: " + $Branch)
Write-Host "MEDINET_SSL_VERIFY=0 (ep OFF)"
try {
  $sha = (git rev-parse --short HEAD 2>$null)
  Write-Host ("Git HEAD: " + $sha)
} catch {}
$sslCheck = Get-Content -LiteralPath (Join-Path $PSScriptRoot "medinet_ssl.py") -Raw -ErrorAction SilentlyContinue
if (-not ($sslCheck -match "apply_ssl_monkeypatch")) {
  Write-Host "DUNG: code cu (thieu SSL monkeypatch). Chay:"
  Write-Host "  powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_KEO_CODE_VA_TONG_HOP.ps1"
  exit 2
}
Write-Host "Quet TOAN BO: INBOX+ERROR+PROCESSED+UNDER18+TK1+TK2 - chay LAU"
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

# ---- 3 assert G + SSL ----
Write-Host ""
Write-Host "==== 3/8 assert G: + SSL + dong bo folder ===="
Assert-G
Assert-Ssl
& $Python ".\pipeline\drive_paths.py"
if (Test-Path -LiteralPath $IdxCache) {
  Get-ChildItem -LiteralPath $IdxCache -Filter "*.pkl" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}
if (Test-Path -LiteralPath $FlagFull) {
  Remove-Item -LiteralPath $FlagFull -Force -ErrorAction SilentlyContinue
  Write-Host "Da xoa FIRST_FULL_SCAN_DONE (se chi ghi lai khi quet that OK)"
}

Write-Host "==== Ledger: restore cases.csv neu trong ===="
& $Python ".\pipeline\restore_cases_snapshot.py"

$beforeAll = Get-Counts
$diskAll = Get-DiskInventory
Write-Host ("COUNTS CSV truoc: {0}" -f $beforeAll.raw)
Write-Host ("COUNTS DISK: {0}" -f $diskAll.raw)
$archiveCsv = [int]$beforeAll.processed + [int]$beforeAll.tk1 + [int]$beforeAll.tk2 + [int]$beforeAll.under18
$archiveEst = [Math]::Max($archiveCsv, [int]$diskAll.archive)
$workEst = [Math]::Max($archiveEst, [int]$diskAll.work)
if ([int]$diskAll.tk_empty -eq 1) {
  $script:TkEmpty = $true
  Write-Host "!! TK1+TK2 disk=0 — bat Available offline tren folder TK1/TK2 (Google Drive)."
  Write-Host "   Se KHONG ghi FIRST_FULL_SCAN_DONE neu TK van trong sau quet."
}
if ($archiveCsv -eq 0 -and $workEst -gt 0) {
  Write-Host "!! cases.csv = 0 nhung G: van co PDF — bot se dang ky lai tu disk (LAU)."
}
Write-Host ("Archive/work uoc tinh DISK={0} (csv_archive={1}) - vong full phai LAU" -f $workEst, $archiveCsv)

# ---- 4 FULL SCAN 2 bot ----
Write-Host ""
Write-Host "==== 4/8 FULL SCAN + REPAIR TOAN BO PDF (2 bot) ===="
Write-Host "BAT BUOC: INBOX + ERROR + PROCESSED + UNDER18 + TK1 + TK2"
$code = 0
for ($r = 1; $r -le $FullRounds; $r++) {
  Write-Host ("----- FULL vong {0}/{1} -----" -f $r, $FullRounds)
  Assert-G
  Assert-Ssl
  $before = Get-Counts
  $disk = Get-DiskInventory
  Write-Host ("COUNTS CSV before: {0}" -f $before.raw)
  Write-Host ("DISK before: archive={0} work={1} tk1={2} tk2={3}" -f $disk.archive, $disk.work, $disk.tk1, $disk.tk2)
  if ([int]$disk.tk_empty -eq 1) { $script:TkEmpty = $true }
  $archCsv = [int]$before.processed + [int]$before.tk1 + [int]$before.tk2 + [int]$before.under18
  $arch = [Math]::Max($archCsv, [Math]::Max([int]$disk.work, [int]$disk.archive))
  $code = Start-TwoBots -Tag ("full{0}" -f $r) -ExtraInbox @("--full-scan", "--repair") -ExtraMissing @(
    "--full-scan", "--repair", "--missing-budget", "$MissingBudget"
  ) -ExpectArchive $arch
  if ($code -ne 0) {
    Write-Host "DUNG buoc 4: bot fail/SSL/too_fast. KHONG danh FULL_DONE."
    break
  }
  $after = Get-Counts
  Write-Host ("COUNTS after : {0}" -f $after.raw)
  if ($r -ge 2 -and (-not $script:HadSsl) -and ($after.inbox -eq $before.inbox) -and ($after.processed -eq $before.processed) -and ($after.error -eq $before.error)) {
    Write-Host "FULL het tien do (DELTA=0, khong SSL)."
    break
  }
}

if ($script:HadSsl -or $code -ne 0) {
  Write-Host ""
  Write-Host "========== DUNG TONG HOP (chua xong that) =========="
  Write-Host ("abort={0} code={1}" -f $script:FatalAbort, $code)
  Write-Host "KHONG ghi FIRST_FULL_SCAN_DONE. KHONG bat hourly."
  Write-Host "Sua SSL/pull code roi chay lai CHAY_TONG_HOP_MOI.ps1"
  exit 2
}

# ---- 5 REMATCH MISSING ----
Write-Host ""
Write-Host "==== 5/8 REMATCH MISSING (2 bot, CSV) ===="
for ($r = 1; $r -le $RematchRounds; $r++) {
  Write-Host ("----- REMATCH vong {0}/{1} -----" -f $r, $RematchRounds)
  Assert-G
  Assert-Ssl
  $before = Get-Counts
  $code = Start-TwoBots -Tag ("rematch{0}" -f $r) -ExtraMissing @("--missing-budget", "$MissingBudget") -ExpectArchive 0
  if ($script:HadSsl -or (($code -eq 2) -and ($script:FatalAbort -eq "ssl_verify"))) {
    Write-Host "DUNG rematch do SSL."
    exit 2
  }
  $after = Get-Counts
  $dP = $after.processed - $before.processed
  $dE = $after.error - $before.error
  $dM = $after.missing - $before.missing
  Write-Host ("DELTA processed={0} error={1} missing={2}" -f $dP, $dE, $dM)
  if ($r -ge 2 -and ($dP -eq 0) -and ($dE -eq 0) -and ($dM -eq 0)) { break }
}

# ---- 6 KIEM TRA LAI fillable ----
Write-Host ""
Write-Host "==== 6/8 KIEM TRA LAI TOAN BO FILLABLE (PROCESSED+TK1+TK2) ===="
Clear-Locks
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_BO_SUNG_THIEU.ps1" -SkipPull
$bs = $LASTEXITCODE
if ($bs -ne 0) {
  Write-Host "DUNG: BO_SUNG exit=$bs - KHONG danh FULL_DONE / KHONG bat hourly."
  exit 2
}

# ---- 7 danh dau full xong (chi khi that su OK) ----
Write-Host ""
Write-Host "==== 7/8 Danh dau FIRST_FULL_SCAN_DONE ===="
if ($script:HadSsl -or $script:HadEarlyExit) {
  Write-Host "BO QUA: van con abort=$($script:FatalAbort) - khong ghi flag."
  exit 2
}
$diskFinal = Get-DiskInventory
if ([int]$diskFinal.tk_empty -eq 1 -or $script:TkEmpty) {
  Write-Host "BO QUA FULL_DONE: TK1+TK2 disk van =0 (archive chua Available offline)."
  Write-Host ("DISK final: {0}" -f $diskFinal.raw)
  Write-Host "Pin TK1/TK2 offline roi chay lai CHAY_TONG_HOP_MOI.ps1 -SkipPull"
  exit 2
}
if ([int]$diskFinal.archive -lt 1 -and [int]$diskFinal.fillable -lt 1) {
  Write-Host "BO QUA FULL_DONE: khong thay PDF fillable tren G:."
  exit 2
}
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

# ---- 8 BAT hourly ----
Write-Host ""
Write-Host "==== 8/8 BAT hourly + cap nhat Super Data ===="
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Clear-Locks

& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"

Write-Host "Doi heartbeat ~25s..."
Start-Sleep -Seconds 25
$hbPaths = @($LocalHb)
try {
  $br = Join-Path $env:TEMP "pkdk_build_root.txt"
  if (Test-Path -LiteralPath $br) {
    $build = (Get-Content -LiteralPath $br -Encoding UTF8 -Raw).Trim()
    $hbPaths += (Join-Path $build "logs\LAST_HOURLY_OK.txt")
  }
} catch {}
foreach ($hp in $hbPaths) {
  if (Test-Path -LiteralPath $hp) {
    Write-Host ("--- HEARTBEAT " + $hp + " ---")
    Get-Content -LiteralPath $hp -Encoding UTF8
  }
}

& $Python ".\pipeline\super_data_status.py" --publish

$final = Get-Counts
Write-Host ""
Write-Host "========== XONG TONG HOP (quet that OK) =========="
Write-Host ("COUNTS: {0}" -f $final.raw)
Write-Host "Nghiem thu: form VONG QUOC CHU phai co MCHC/RDW neu PDF co."
exit 0
