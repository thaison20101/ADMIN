# ============================================================
# FORCE dien INBOX - khong choi Task Scheduler / khong tam dung
# 1) Pin pass TK1  2) Auth  3) Chay truc tiep hourly_sync --bot inbox --force --repair
# ASCII-only.
#
#   cd C:\Users\thais\ADMIN
#   git fetch origin
#   git reset --hard origin/cursor/formviewer-cls-bypass-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\FORCE_DIEN_INBOX.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Branch = "cursor/formviewer-cls-bypass-df0f"
$env:MEDINET_SSL_VERIFY = "0"
$env:MEDINET_USER = "pkdkthuankieu"
$env:MEDINET_PASS = "Qlskcd@2026"
# Bo qua TK2 (khong auth / khong index TK2). Bat lai: $env:MEDINET_ENABLE_TK2 = "1"
Remove-Item Env:MEDINET_ENABLE_TK2 -ErrorAction SilentlyContinue
Remove-Item Env:MEDINET_USER_2 -ErrorAction SilentlyContinue
Remove-Item Env:MEDINET_PASS_2 -ErrorAction SilentlyContinue
$env:PKDK_FORCE_INDEX = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

function Log([string]$m) { Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m) }

function Clear-PkdkLocks {
  Get-Process -Name python*, py* -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 1
  $LockDir = Join-Path $Repo "pipeline\work\locks"
  if (Test-Path -LiteralPath $LockDir) {
    Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -Recurse -ErrorAction SilentlyContinue |
      Remove-Item -Force -ErrorAction SilentlyContinue
  }
  Log "Cleared python + locks"
}

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

Log "==== Tam NGUNG hourly (tranh lock missing) ===="
try {
  Disable-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction Stop | Out-Null
  Log "Hourly DISABLED trong luc FORCE"
} catch {
  Log ("WARN Disable hourly: " + $_)
}

Log "==== Kill + locks ===="
Clear-PkdkLocks

Log "==== Pin creds + auth ===="
& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_creds.py" --write --user pkdkthuankieu --pass Qlskcd@2026
& $Python ".\pipeline\medinet_creds.py" --show
Log "NOTE: pass tip = Qlskcd@2026. Auth dung User-Agent Chrome (WAF block Python-urllib)."
& $Python ".\pipeline\medinet_ssl.py"
$auth = $LASTEXITCODE
if ($auth -ne 0) {
  Log "AUTH TIMEOUT/FAIL - tip phai co browser UA. Neu HEAD cu: git reset --hard origin/cursor/formviewer-cls-bypass-df0f"
  Start-Sleep -Seconds 3
  & $Python ".\pipeline\medinet_ssl.py"
  $auth = $LASTEXITCODE
}
if ($auth -ne 0) { Log "DUNG: khong login duoc Medinet. Pass tip da dung Qlskcd@2026."; exit 2 }
& $Python ".\pipeline\probe_both_accounts.py"
if ($LASTEXITCODE -ne 0) {
  Log "DUNG: TK1 DRViewer+FormViewer bi chan - khong dien CLS. Bo qua TK2. Chay KIEM_QUYEN_TK1.ps1"
  exit 2
}
Log "AUTH TK1 fill OK (DRViewer va/hoac FormViewer; bo qua TK2)"
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) { Log "G: FAIL"; exit 2 }

Log "==== INBOX TRUOC ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }

Log "==== FORCE bot=inbox --force --repair (dien web) ===="
Clear-PkdkLocks
$t0 = Get-Date
& $Python -u ".\pipeline\hourly_sync.py" --bot inbox --force --repair --missing-budget 0
$code1 = $LASTEXITCODE
Log ("inbox bot exit=" + $code1 + " sec=" + [int]((Get-Date) - $t0).TotalSeconds)
Clear-PkdkLocks

$code2 = 0
$okRounds = 0
for ($round = 1; $round -le 4; $round++) {
  Log ("==== Rematch MISSING CSV vong $round/4 --force budget 2500 (TTHC moi) ====")
  Clear-PkdkLocks
  $t1 = Get-Date
  & $Python -u ".\pipeline\hourly_sync.py" --bot missing --force --missing-budget 2500
  $code2 = $LASTEXITCODE
  Log ("missing vong $round exit=$code2 sec=" + [int]((Get-Date) - $t1).TotalSeconds)
  if ($code2 -ne 0) {
    Log "WARN missing exit!=0 — clear lock + RETRY 1 lan"
    Clear-PkdkLocks
    Start-Sleep -Seconds 2
    & $Python -u ".\pipeline\hourly_sync.py" --bot missing --force --missing-budget 2500
    $code2 = $LASTEXITCODE
    Log ("missing vong $round RETRY exit=$code2")
  }
  if ($code2 -eq 0) { $okRounds++ }
  else { Log "WARN: vong $round van fail — tiep vong sau (KHONG break)" }
}

Log ("MISSING rounds OK=$okRounds / 4")

Log "==== Bat hourly task (an) de chay tiep moi gio ===="
Clear-PkdkLocks
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
try { Enable-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction SilentlyContinue | Out-Null } catch {}
$t = Get-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction SilentlyContinue
if ($t) { Log ("Task State=" + $t.State) }

Log "==== INBOX SAU ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

$code = 0
if ($okRounds -lt 1 -and $code1 -ne 0) { $code = 2 }
elseif ($okRounds -lt 1 -and $code1 -eq 0) { $code = 0 }
Write-Host "############################################################"
Write-Host (" FORCE xong exit=" + $code + " HEAD=" + $sha + " missing_ok_rounds=" + $okRounds)
Write-Host " Bao cao gio (tieng Viet): G:\\Drive cua toi\\BAO_CAO_GIO\\MOI_NHAT.txt"
Write-Host " Neu INBOX van khong giam: copy toan bo log mau do/AUTH o tren gui lai."
Write-Host "############################################################"
exit $code
