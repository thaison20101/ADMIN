# ============================================================
# CHAY LAI NHU TRUOC KHI TAM DUNG - hourly luon BAT
# ASCII-only. Coi nhu chua tung tam dung.
#
# TK1: pkdkthuankieu / Qlskcd@2026
# TK2: pkdk_Thuankieu / pkdk_Thuankieu#2026
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_LAI_NHU_TRUOC.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Branch = "cursor/hourly-flash-fix-df0f"
$TaskName = "PKDK_Hourly_Sync"
$env:MEDINET_SSL_VERIFY = "0"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

function Log([string]$m) {
  Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m)
}

Write-Host "############################################################"
Write-Host "#  CHAY LAI NHU TRUOC - hourly ON (khong tam dung)          #"
Write-Host "############################################################"
Write-Host "TK1 user=pkdkthuankieu pass=Qlskcd@2026"
Write-Host "TK2 user=pkdk_Thuankieu (khong doi)"
Write-Host ""

Log "==== 1/6 Keo tip ===="
git fetch origin
git checkout $Branch
git reset --hard ("origin/" + $Branch)
git clean -fd --exclude=pipeline/config.local.json --exclude=pipeline/work --exclude=tracking
$sha = (git rev-parse --short HEAD)
Log ("HEAD=" + $sha)

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python
Log ("Python=" + $Python)

# Verify creds in tip match expected
& $Python -c "from medinet_creds import MEDINET_ACCOUNTS as A; assert A[0]['user']=='pkdkthuankieu' and A[0]['password']=='Qlskcd@2026', A[0]; print('CREDS_OK', A[0]['user'], A[0]['password'][:4]+'***')"
if ($LASTEXITCODE -ne 0) {
  Log "DUNG: tip sai user/pass TK1"
  exit 2
}

Log "==== 2/6 Kill treo + xoa lock (bo trang thai tam dung) ===="
Get-Process -Name python*, py* -ErrorAction SilentlyContinue | ForEach-Object {
  Log ("  stop PID=" + $_.Id)
  Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
$LockDir = Join-Path $Repo "pipeline\work\locks"
if (Test-Path -LiteralPath $LockDir) {
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -Recurse -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
}

Log "==== 3/6 Config + auth 2 TK ===="
& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_ssl.py"
if ($LASTEXITCODE -ne 0) {
  Log "DUNG: AUTH TK1 FAIL - kiem pkdkthuankieu / Qlskcd@2026 tren web Medinet"
  exit 2
}
& $Python ".\pipeline\probe_both_accounts.py"
if ($LASTEXITCODE -ne 0) {
  Log "DUNG: AUTH 1/2 TK FAIL"
  exit 2
}
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Log "DUNG: G: chua san - mo Google Drive Desktop"
  exit 2
}
& $Python ".\pipeline\drive_paths.py"

Log "==== 4/6 Dem disk TRUOC ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }

Log "==== 5/6 Cai task HIDDEN + BAT (nhu truoc khi tam dung) ===="
# Never -NoStart: hourly must be ON
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
Log ("install exit=" + $LASTEXITCODE)
try {
  Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
  Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
} catch {
  schtasks.exe /Change /TN $TaskName /ENABLE | Out-Null
}
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($t) {
  Log ("Task State=" + $t.State)
  if ($t.State -eq "Disabled") {
    Log "FAIL: task van Disabled - chay PowerShell Run as Administrator"
    exit 2
  }
} else {
  Log "WARN: task chua thay - van chay run_hourly tay"
}

Log "==== 6/6 Chay run_hourly 1 lan (dien INBOX + rematch) ===="
$t0 = Get-Date
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\run_hourly.ps1"
$run = $LASTEXITCODE
$sec = [int]((Get-Date) - $t0).TotalSeconds
Log ("run_hourly exit=" + $run + " duration_s=" + $sec)

Log "==== Dem disk SAU ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

$markDir = Join-Path $Repo "pipeline\work\build\logs"
if (-not (Test-Path -LiteralPath $markDir)) { New-Item -ItemType Directory -Force -Path $markDir | Out-Null }
@(
  "state=HOURLY_ON"
  "mode=NHU_TRUOC_KHONG_TAM_DUNG"
  ("at=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
  ("head=" + $sha)
  ("run_exit=" + $run)
  ("duration_s=" + $sec)
  "tk1=pkdkthuankieu"
) | Set-Content -LiteralPath (Join-Path $markDir "HOURLY_PAUSE_STATE.txt") -Encoding utf8

Write-Host ""
Write-Host "############################################################"
Write-Host " XONG. Hourly DANG BAT (an). Coi nhu chua tung tam dung."
Write-Host " Neu duration_s < 20: abort G:/auth - doc log o tren."
Write-Host " Kiem: Get-ScheduledTask -TaskName PKDK_Hourly_Sync"
Write-Host "############################################################"
exit $run
