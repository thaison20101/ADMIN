# ============================================================
# DIEN cac BN da co TTHC tren Medinet + PDF (INBOX/MISSING)
# - Pin TK1, force index moi, --force dien web
# - Nhieu vong rematch MISSING (CSV) budget 2500
# ASCII-only. May A G: only.
#
#   cd C:\Users\thais\ADMIN
#   git fetch origin
#   git reset --hard origin/cursor/hourly-flash-fix-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DIEN_CO_TTHC.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Branch = "cursor/hourly-flash-fix-df0f"
$env:MEDINET_SSL_VERIFY = "0"
$env:MEDINET_USER = "pkdkthuankieu"
$env:MEDINET_PASS = "Qlskcd@2026"
# Bo qua TK2
Remove-Item Env:MEDINET_ENABLE_TK2 -ErrorAction SilentlyContinue
Remove-Item Env:MEDINET_USER_2 -ErrorAction SilentlyContinue
Remove-Item Env:MEDINET_PASS_2 -ErrorAction SilentlyContinue
$env:PKDK_FORCE_INDEX = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

function Log([string]$m) { Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }

Write-Host "############################################################"
Write-Host "#  DIEN CO TTHC (INBOX + MISSING rematch, index moi)        #"
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
& $Python ".\pipeline\medinet_ssl.py"
if ($LASTEXITCODE -ne 0) { Log "DUNG: AUTH TK1 FAIL"; exit 2 }
& $Python ".\pipeline\probe_both_accounts.py"
if ($LASTEXITCODE -ne 0) { Log "DUNG: AUTH TK1 FAIL"; exit 2 }
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) { Log "DUNG: G: FAIL"; exit 2 }

Log "==== COUNTS TRUOC ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

Log "==== 1) INBOX + ERROR --force --repair (index moi) ===="
$t0 = Get-Date
& $Python -u ".\pipeline\hourly_sync.py" --bot inbox --force --repair --missing-budget 0
$code1 = $LASTEXITCODE
Log ("inbox exit=" + $code1 + " sec=" + [int]((Get-Date) - $t0).TotalSeconds)

$code2 = 0
for ($round = 1; $round -le 6; $round++) {
  Log ("==== 2) MISSING rematch vong $round/6 --force budget 2500 ====")
  $t1 = Get-Date
  & $Python -u ".\pipeline\hourly_sync.py" --bot missing --force --missing-budget 2500
  $code2 = $LASTEXITCODE
  Log ("missing vong $round exit=$code2 sec=" + [int]((Get-Date) - $t1).TotalSeconds)
  & $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }
  if ($code2 -ne 0) { break }
}

Log "==== Bat hourly tiep ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
try { Enable-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction SilentlyContinue | Out-Null } catch {}

Log "==== COUNTS SAU ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

$code = [Math]::Max([int]$code1, [int]$code2)
Write-Host "############################################################"
Write-Host (" DIEN CO TTHC xong exit=" + $code + " HEAD=" + $sha)
Write-Host " Bao cao: G:\\Drive cua toi\\BAO_CAO_GIO\\MOI_NHAT.txt"
Write-Host " Che do: CHI TK1 (bo qua TK2)."
Write-Host "############################################################"
exit $code
