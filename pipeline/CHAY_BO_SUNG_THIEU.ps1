# ============================================================
# KIEM TRA LAI / BO SUNG FIELD TU PDF LEN WEB
# TOAN BO folder fillable: INBOX + ERROR + PROCESSED + UNDER18 + TK1 + TK2
# (MISSING = chua TTHC -> khong dien; rematch rieng)
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_BO_SUNG_THIEU.ps1
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_BO_SUNG_THIEU.ps1 -SkipPull
# ============================================================

param(
  [switch]$SkipPull,
  [int]$Rounds = 3
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python

$Branch = "cursor/hourly-flash-fix-df0f"

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

Write-Host ""
Write-Host "############################################################"
Write-Host "#  KIEM TRA LAI TOAN BO (rule dien MOI)                     #"
Write-Host "#  INBOX+ERROR+PROCESSED+UNDER18+TK1+TK2  (khong MISSING)  #"
Write-Host "############################################################"
Write-Host ("Python: " + $Python)
Write-Host ("Branch: " + $Branch)

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

Write-Host "==== 2/3 config + assert G: ===="
& $Python ".\pipeline\ensure_config.py"
& $Python -m pip install -q -r ".\pipeline\requirements.txt"
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san. Mo Google Drive Desktop roi chay lai."
  exit 2
}

Write-Host "==== 3/3 REPAIR TOAN FOLDER FILLABLE (2 bot) ===="
Write-Host "Rule dien MOI: hang ngang ten XN; dam/gach van dien; khong lay khoang tham chieu."
Write-Host "INBOX+ERROR | PROCESSED+UNDER18+TK1+TK2 - KHONG walk MISSING."
$code = 0
for ($round = 1; $round -le $Rounds; $round++) {
  Write-Host ("----- VONG {0}/{1} -----" -f $round, $Rounds)
  & $Python ".\pipeline\assert_g_pipeline.py"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "DUNG: G: mat ket noi giua vong. Mo Drive roi chay lai."
    exit 2
  }

  $argsInbox = @(
    "-u", ".\pipeline\hourly_sync.py",
    "--bot", "inbox", "--repair", "--missing-budget", "0"
  )
  $argsMiss = @(
    "-u", ".\pipeline\hourly_sync.py",
    "--bot", "missing", "--repair", "--missing-budget", "0"
  )
  Write-Host ("Bot INBOX:  --repair (INBOX+ERROR)")
  Write-Host ("Bot AUDIT:  --repair (PROCESSED+TK1+TK2+UNDER18)")
  $b1 = Start-Process -FilePath $Python -ArgumentList $argsInbox -WorkingDirectory $Repo -PassThru -NoNewWindow
  $b2 = Start-Process -FilePath $Python -ArgumentList $argsMiss -WorkingDirectory $Repo -PassThru -NoNewWindow
  Write-Host ("  PID inbox={0} audit={1}" -f $b1.Id, $b2.Id)
  Wait-Process -Id $b1.Id, $b2.Id -ErrorAction SilentlyContinue
  $c1 = $b1.ExitCode; if ($null -eq $c1) { $c1 = 0 }
  $c2 = $b2.ExitCode; if ($null -eq $c2) { $c2 = 0 }
  $code = [Math]::Max([int]$c1, [int]$c2)
  Write-Host ("Vong {0}: exit inbox={1} audit={2}" -f $round, $c1, $c2)
  & $Python ".\pipeline\print_counts.py" | Select-Object -Last 1 | ForEach-Object { Write-Host $_ }
  if ($code -ne 0 -and $round -ge 2) { break }
}

Write-Host ""
Write-Host "========== XONG KIEM TRA LAI / BO SUNG =========="
Write-Host "Da re-parse + so web toan folder fillable (rule dien moi)."
Write-Host "MISSING: chi rematch khi co TTHC (CHAY_REMATCH / TONG_HOP buoc 5)."
Write-Host "================================================="
if ($code -ne 0) { exit $code }
exit 0
