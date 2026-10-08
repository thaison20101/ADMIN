# ============================================================
# FORCE dien INBOX - khong choi Task Scheduler / khong tam dung
# 1) Pin pass TK1  2) Auth  3) Chay truc tiep hourly_sync --bot inbox --force --repair
# ASCII-only.
#
#   cd C:\Users\thais\ADMIN
#   git fetch origin
#   git reset --hard origin/cursor/hourly-flash-fix-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\FORCE_DIEN_INBOX.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Branch = "cursor/hourly-flash-fix-df0f"
$env:MEDINET_SSL_VERIFY = "0"
$env:MEDINET_USER = "pkdkthuankieu"
$env:MEDINET_PASS = "Qlskcd@2026"
$env:MEDINET_USER_2 = "pkdk_Thuankieu"
$env:MEDINET_PASS_2 = "pkdk_Thuankieu#2026"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

function Log([string]$m) { Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }

Write-Host "############################################################"
Write-Host "#  FORCE DIEN INBOX (truc tiep, hourly ON sau do)           #"
Write-Host "############################################################"

Log "==== Git tip ===="
git fetch origin
git checkout $Branch
git reset --hard ("origin/" + $Branch)
$sha = (git rev-parse --short HEAD)
Log ("HEAD=" + $sha)

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python
Log ("Python=" + $Python)

Log "==== Kill + locks ===="
Get-Process -Name python*, py* -ErrorAction SilentlyContinue | ForEach-Object {
  Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
$LockDir = Join-Path $Repo "pipeline\work\locks"
if (Test-Path -LiteralPath $LockDir) {
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

Log "==== Pin creds + auth ===="
& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_creds.py" --write --user pkdkthuankieu --pass Qlskcd@2026
& $Python ".\pipeline\medinet_creds.py" --show
Log "NOTE: pass tip = Qlskcd@2026 (len 11). Timeout = mang toi Medinet, KHONG phai sai pass."
& $Python ".\pipeline\medinet_ssl.py"
$auth = $LASTEXITCODE
if ($auth -ne 0) {
  Log "AUTH TIMEOUT/FAIL - thu mo Chrome: https://quanlyskcd.medinet.org.vn"
  Log "Neu web cung khong vao duoc: mang/proxy. Neu web login OK: chay lai script (retry dai hon)."
  # Mot lan retry them sau 5s
  Start-Sleep -Seconds 5
  & $Python ".\pipeline\medinet_ssl.py"
  $auth = $LASTEXITCODE
}
if ($auth -ne 0) { Log "DUNG: khong login duoc Medinet (timeout/mang). Pass tip da dung Qlskcd@2026."; exit 2 }
& $Python ".\pipeline\probe_both_accounts.py"
if ($LASTEXITCODE -ne 0) { Log "AUTH FAIL 2TK"; exit 2 }
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) { Log "G: FAIL"; exit 2 }

Log "==== INBOX TRUOC ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }

Log "==== FORCE bot=inbox --force --repair (dien web) ===="
$t0 = Get-Date
& $Python -u ".\pipeline\hourly_sync.py" --bot inbox --force --repair --missing-budget 0
$code1 = $LASTEXITCODE
Log ("inbox bot exit=" + $code1 + " sec=" + [int]((Get-Date) - $t0).TotalSeconds)

Log "==== Rematch MISSING CSV (budget 2500) ===="
$t1 = Get-Date
& $Python -u ".\pipeline\hourly_sync.py" --bot missing --force --missing-budget 2500
$code2 = $LASTEXITCODE
Log ("missing bot exit=" + $code2 + " sec=" + [int]((Get-Date) - $t1).TotalSeconds)

Log "==== Bat hourly task (an) de chay tiep moi gio ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
try { Enable-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction SilentlyContinue | Out-Null } catch {}
$t = Get-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction SilentlyContinue
if ($t) { Log ("Task State=" + $t.State) }

Log "==== INBOX SAU ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

$code = [Math]::Max([int]$code1, [int]$code2)
Write-Host "############################################################"
Write-Host (" FORCE xong exit=" + $code + " HEAD=" + $sha)
Write-Host " Neu INBOX van khong giam: copy toan bo log mau do/AUTH o tren gui lai."
Write-Host "############################################################"
exit $code
