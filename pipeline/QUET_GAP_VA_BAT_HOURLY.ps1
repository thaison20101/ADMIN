# ============================================================
# QUET GAP: BN da co TTHC nhung chua dien + BAT hourly moi gio
# - TK1 only (bo qua TK2)
# - Tat hourly trong luc quet (tranh lock missing)
# - Rematch MISSING nhieu vong (PostData + FormViewer)
# - CHI chuyen folder khi CLS verify du
# ASCII-only.
#
#   cd C:\Users\thais\ADMIN
#   git fetch origin
#   git reset --hard origin/cursor/formviewer-cls-bypass-df0f
#   powershell -ExecutionPolicy Bypass -File .\pipeline\QUET_GAP_VA_BAT_HOURLY.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Branch = "cursor/formviewer-cls-bypass-df0f"
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

Log "==== Tam NGUNG hourly (tranh lock missing) ===="
try {
  Disable-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction Stop | Out-Null
  Log "Hourly DISABLED trong luc QUET_GAP"
} catch {
  Log ("WARN Disable hourly: " + $_)
}

Log "==== Kill + locks ===="
Clear-PkdkLocks

Log "==== Pin creds + auth TK1 ===="
& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_creds.py" --write --user pkdkthuankieu --pass Qlskcd@2026
& $Python ".\pipeline\medinet_creds.py" --show
& $Python ".\pipeline\medinet_ssl.py"
if ($LASTEXITCODE -ne 0) { Log "DUNG: AUTH TK1 FAIL"; exit 2 }
& $Python ".\pipeline\probe_both_accounts.py"
if ($LASTEXITCODE -ne 0) {
  Log "DUNG: TK1 login OK nhung khong dien duoc CLS (FormViewer/DRViewer)."
  Log "Bo qua TK2. Chay: KIEM_QUYEN_TK1.ps1"
  exit 2
}
Log "AUTH fill OK. Rematch MISSING (PostData) + dien FormViewer; chi chuyen khi CLS du."
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) { Log "DUNG: G: FAIL - mo Google Drive"; exit 2 }

Log "==== COUNTS TRUOC ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

Log "==== 1/3 INBOX+ERROR force+repair ===="
Clear-PkdkLocks
$t0 = Get-Date
& $Python -u ".\pipeline\hourly_sync.py" --bot inbox --force --repair --missing-budget 0
$code1 = $LASTEXITCODE
Log ("inbox exit=" + $code1 + " sec=" + [int]((Get-Date) - $t0).TotalSeconds)
Clear-PkdkLocks

$code2 = 0
$Rounds = 8
$Budget = 3000
$okRounds = 0
for ($round = 1; $round -le $Rounds; $round++) {
  Log ("==== 2/3 MISSING rematch vong $round/$Rounds --force budget $Budget ====")
  Clear-PkdkLocks
  $t1 = Get-Date
  & $Python -u ".\pipeline\hourly_sync.py" --bot missing --force --missing-budget $Budget
  $code2 = $LASTEXITCODE
  $sec = [int]((Get-Date) - $t1).TotalSeconds
  Log ("missing vong $round exit=$code2 sec=$sec")

  if ($code2 -ne 0) {
    Log "WARN missing exit!=0 — clear lock + RETRY 1 lan (thuong do lock)"
    Clear-PkdkLocks
    Start-Sleep -Seconds 2
    & $Python -u ".\pipeline\hourly_sync.py" --bot missing --force --missing-budget $Budget
    $code2 = $LASTEXITCODE
    Log ("missing vong $round RETRY exit=$code2")
  }

  & $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }
  & $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }

  if ($code2 -eq 0) {
    $okRounds++
  } else {
    Log "WARN: vong $round van fail — tiep vong sau (KHONG break ca rematch)"
  }
  # Neu missing disk da thap, co the dung som
  # (khong bat buoc — van chay het rounds de PostData bat TTHC moi)
}

Log ("MISSING rounds OK=$okRounds / $Rounds")

Log "==== 3/3 Cai + BAT hourly PKDK_Hourly_Sync ===="
Clear-PkdkLocks
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

# exit 0 neu it nhat 1 vong missing OK (hoac inbox OK); lock abort 1 vong khong giet ca script
$code = 0
if ($okRounds -lt 1 -and $code1 -ne 0) { $code = 2 }
elseif ($okRounds -lt 1) { $code = 2 }

Write-Host "############################################################"
Write-Host (" QUET GAP xong exit=" + $code + " HEAD=" + $sha + " missing_ok_rounds=" + $okRounds)
Write-Host " Hourly: PKDK_Hourly_Sync moi gio (an, wscript)"
Write-Host " CHI chuyen folder khi CLS verify du (co TTHC thoi = KEEP MISSING)."
Write-Host " CHI TK1 (bo qua TK2)."
Write-Host "############################################################"
exit $code
