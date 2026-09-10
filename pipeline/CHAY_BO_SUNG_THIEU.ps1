# ============================================================
# KIEM TRA LAI / BO SUNG FIELD TU PDF LEN WEB
# TOAN BO folder fillable: INBOX + ERROR + PROCESSED + UNDER18 + TK1 + TK2
# (MISSING = chua TTHC -> khong dien; rematch rieng)
# Chay LAU khi archive lon. SSL OFF bat buoc.
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_BO_SUNG_THIEU.ps1
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_BO_SUNG_THIEU.ps1 -SkipPull
# ============================================================

param(
  [switch]$SkipPull,
  [int]$Rounds = 3,
  [int]$MinRoundSeconds = 180
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python
$env:MEDINET_SSL_VERIFY = "0"

$Branch = "cursor/hourly-flash-fix-df0f"
$LogDir = Join-Path $Repo "pipeline\work\logs"

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
if (-not $env:MEDINET_USER) { $env:MEDINET_USER = "pkdkthuankieu" }
if (-not $env:MEDINET_PASS) { $env:MEDINET_PASS = "P@ssw0rd" }
if (-not $env:MEDINET_USER_2) { $env:MEDINET_USER_2 = "pkdk_Thuankieu" }
if (-not $env:MEDINET_PASS_2) { $env:MEDINET_PASS_2 = "pkdk_Thuankieu#2026" }
try {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}

if (-not (Test-Path -LiteralPath $LogDir)) {
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

Write-Host ""
Write-Host "############################################################"
Write-Host "#  KIEM TRA LAI TOAN BO PDF (rule dien MOI)                 #"
Write-Host "#  INBOX+ERROR+PROCESSED+UNDER18+TK1+TK2  (khong MISSING)  #"
Write-Host "#  Chay LAU - khong xong trong vai phut neu archive lon     #"
Write-Host "############################################################"
Write-Host ("Python: " + $Python)
Write-Host ("Branch: " + $Branch)
Write-Host "MEDINET_SSL_VERIFY=0"

Write-Host "==== 1/3 git pull ===="
if (-not $SkipPull) {
  if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
    git fetch origin
    git checkout $Branch
    git pull origin $Branch
  }
} else {
  Write-Host "SkipPull: giu branch hien tai"
}

Write-Host "==== 2/3 config + assert G: + SSL ===="
& $Python ".\pipeline\ensure_config.py"
& $Python -m pip install -q -r ".\pipeline\requirements.txt"
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san."
  exit 2
}
& $Python ".\pipeline\medinet_ssl.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: SSL/auth FAIL - khong quet gia."
  exit 2
}

$countsLine = (& $Python ".\pipeline\print_counts.py" 2>$null | Select-Object -Last 1)
Write-Host ("COUNTS CSV: {0}" -f $countsLine)
$diskLines = @(& $Python ".\pipeline\print_disk_counts.py" 2>$null)
$diskLines | ForEach-Object { Write-Host $_ }
$arch = 0
if ($countsLine -match "processed=(\d+)") { $arch += [int]$Matches[1] }
if ($countsLine -match "tk1=(\d+)") { $arch += [int]$Matches[1] }
if ($countsLine -match "tk2=(\d+)") { $arch += [int]$Matches[1] }
if ($countsLine -match "under18=(\d+)") { $arch += [int]$Matches[1] }
$diskArch = 0
$diskWork = 0
foreach ($line in $diskLines) {
  if ($line -match "^ARCHIVE_DISK\t(\d+)$") { $diskArch = [int]$Matches[1] }
  if ($line -match "^FILLABLE_DISK\t(\d+)$") { $diskWork = [int]$Matches[1] }
}
$arch = [Math]::Max($arch, [Math]::Max($diskArch, $diskWork))
Write-Host ("Archive/work uoc tinh (max csv|disk)={0}" -f $arch)

Write-Host "==== 3/3 REPAIR TOAN FOLDER FILLABLE (2 bot) ===="
Write-Host "INBOX+ERROR | PROCESSED+UNDER18+TK1+TK2 - KHONG walk MISSING."
$code = 0
for ($round = 1; $round -le $Rounds; $round++) {
  Write-Host ("----- VONG {0}/{1} -----" -f $round, $Rounds)
  & $Python ".\pipeline\assert_g_pipeline.py"
  if ($LASTEXITCODE -ne 0) { exit 2 }
  & $Python ".\pipeline\medinet_ssl.py"
  if ($LASTEXITCODE -ne 0) { exit 2 }

  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $logInbox = Join-Path $LogDir ("bosung-inbox-{0}.log" -f $stamp)
  $logMiss = Join-Path $LogDir ("bosung-audit-{0}.log" -f $stamp)
  $argsInbox = @("-u", ".\pipeline\hourly_sync.py", "--bot", "inbox", "--repair", "--missing-budget", "0")
  $argsMiss = @("-u", ".\pipeline\hourly_sync.py", "--bot", "missing", "--repair", "--missing-budget", "0")
  $t0 = Get-Date
  $b1 = Start-Process -FilePath $Python -ArgumentList $argsInbox -WorkingDirectory $Repo `
    -PassThru -NoNewWindow -RedirectStandardOutput $logInbox -RedirectStandardError ($logInbox + ".err")
  $b2 = Start-Process -FilePath $Python -ArgumentList $argsMiss -WorkingDirectory $Repo `
    -PassThru -NoNewWindow -RedirectStandardOutput $logMiss -RedirectStandardError ($logMiss + ".err")
  Write-Host ("  PID inbox={0} audit={1}" -f $b1.Id, $b2.Id)
  Wait-Process -Id $b1.Id, $b2.Id -ErrorAction SilentlyContinue
  $sec = [int]((Get-Date) - $t0).TotalSeconds
  $c1 = $b1.ExitCode; if ($null -eq $c1) { $c1 = 0 }
  $c2 = $b2.ExitCode; if ($null -eq $c2) { $c2 = 0 }
  $code = [Math]::Max([int]$c1, [int]$c2)
  Write-Host ("Vong {0}: duration_s={1} exit inbox={2} audit={3}" -f $round, $sec, $c1, $c2)

  $blob = ""
  foreach ($p in @($logInbox, ($logInbox + ".err"), $logMiss, ($logMiss + ".err"))) {
    if (Test-Path -LiteralPath $p) { $blob += (Get-Content -LiteralPath $p -Raw -ErrorAction SilentlyContinue) }
  }
  if ($blob -match "CERTIFICATE_VERIFY_FAILED|SSLCertVerificationError|self-signed certificate") {
    Write-Host "DUNG: SSL trong log bot."
    Get-Content -LiteralPath ($logMiss + ".err") -Tail 15 -ErrorAction SilentlyContinue
    exit 2
  }
  if ($arch -ge 100 -and $sec -lt $MinRoundSeconds -and $code -eq 0) {
    Write-Host ("DUNG: vong qua NHANH ({0}s) voi archive/work~{1} - khong phai quet that." -f $sec, $arch)
    exit 2
  }
  $dien = ([regex]::Matches($blob, "DIEN OK")).Count
  Write-Host ("  DIEN OK lines~{0} log={1}" -f $dien, $logMiss)
  & $Python ".\pipeline\print_counts.py" | Select-Object -Last 1 | ForEach-Object { Write-Host $_ }
  if ($code -ne 0) {
    Write-Host "DUNG: bot exit != 0"
    exit $code
  }
}

Write-Host ""
Write-Host "========== XONG KIEM TRA LAI / BO SUNG =========="
Write-Host "Da re-parse + so web toan folder fillable (rule dien moi)."
Write-Host "================================================="
exit 0
