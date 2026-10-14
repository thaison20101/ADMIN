# ============================================================
# QUET GAP: BN da co TTHC nhung chua dien + BAT hourly moi gio
# - TK1 only (bo qua TK2)
# - Force index moi, dien INBOX, rematch MISSING nhieu vong
# - Cai/bat Task Scheduler PKDK_Hourly_Sync
# ASCII-only.
#
#   cd C:\Users\thais\ADMIN
#   git fetch origin
#   git reset --hard origin/cursor/hourly-flash-fix-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\QUET_GAP_VA_BAT_HOURLY.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Branch = "cursor/hourly-flash-fix-df0f"
$env:MEDINET_SSL_VERIFY = "0"
$env:MEDINET_USER = "pkdkthuankieu"
$env:MEDINET_PASS = "Qlskcd@2026"
Remove-Item Env:MEDINET_ENABLE_TK2 -ErrorAction SilentlyContinue
Remove-Item Env:MEDINET_USER_2 -ErrorAction SilentlyContinue
Remove-Item Env:MEDINET_PASS_2 -ErrorAction SilentlyContinue
$env:PKDK_FORCE_INDEX = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

function Log([string]$m) { Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }

Write-Host "############################################################"
Write-Host "#  QUET GAP (TTHC da co) + BAT HOURLY MOI GIO               #"
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

Log "==== Pin creds + auth TK1 ===="
& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_creds.py" --write --user pkdkthuankieu --pass Qlskcd@2026
& $Python ".\pipeline\medinet_creds.py" --show
& $Python ".\pipeline\medinet_ssl.py"
if ($LASTEXITCODE -ne 0) { Log "DUNG: AUTH TK1 FAIL"; exit 2 }
& $Python ".\pipeline\probe_both_accounts.py"
if ($LASTEXITCODE -ne 0) { Log "DUNG: AUTH TK1 FAIL"; exit 2 }
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) { Log "DUNG: G: FAIL - mo Google Drive"; exit 2 }

Log "==== COUNTS TRUOC ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

Log "==== 1/3 INBOX+ERROR force+repair (index TTHC moi) ===="
$t0 = Get-Date
& $Python -u ".\pipeline\hourly_sync.py" --bot inbox --force --repair --missing-budget 0
$code1 = $LASTEXITCODE
Log ("inbox exit=" + $code1 + " sec=" + [int]((Get-Date) - $t0).TotalSeconds)

$code2 = 0
$Rounds = 8
$Budget = 3000
for ($round = 1; $round -le $Rounds; $round++) {
  Log ("==== 2/3 MISSING rematch vong $round/$Rounds --force budget $Budget ====")
  $t1 = Get-Date
  & $Python -u ".\pipeline\hourly_sync.py" --bot missing --force --missing-budget $Budget
  $code2 = $LASTEXITCODE
  Log ("missing vong $round exit=$code2 sec=" + [int]((Get-Date) - $t1).TotalSeconds)
  & $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }
  if ($code2 -ne 0) { break }
}

Log "==== 3/3 Cai + BAT hourly PKDK_Hourly_Sync ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
try { Enable-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction Stop | Out-Null } catch {
  Log ("WARN Enable-ScheduledTask: " + $_)
}
try {
  $info = Get-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction Stop
  $st = Get-ScheduledTaskInfo -TaskName "PKDK_Hourly_Sync" -ErrorAction SilentlyContinue
  Log ("Task State=" + $info.State + " NextRun=" + $(if ($st) { $st.NextRunTime } else { "?" }))
  if ($info.State -ne "Ready" -and $info.State -ne "Running") {
    Log "WARN: Task chua Ready - thu Enable lai"
    Enable-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction SilentlyContinue | Out-Null
  }
} catch {
  Log "DUNG: khong thay task PKDK_Hourly_Sync sau install"
  exit 2
}

Log "==== COUNTS SAU ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

$code = [Math]::Max([int]$code1, [int]$code2)
Write-Host "############################################################"
Write-Host (" QUET GAP xong exit=" + $code + " HEAD=" + $sha)
Write-Host " Hourly: PKDK_Hourly_Sync moi gio (an, wscript)"
Write-Host " Bao cao: G:\\Drive cua toi\\BAO_CAO_GIO\\MOI_NHAT.txt"
Write-Host " CHI TK1 (bo qua TK2)."
Write-Host "############################################################"
exit $code
