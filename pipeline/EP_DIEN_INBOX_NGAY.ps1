# ============================================================
# EP DIEN INBOX NGAY - keo tip + auth + bat hourly + chay 1 lan
# In RO RO: dem INBOX truoc/sau, abort reason, State task.
# ASCII-only Windows PowerShell 5.1
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\EP_DIEN_INBOX_NGAY.ps1
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
Write-Host "#  EP DIEN INBOX NGAY                                       #"
Write-Host "############################################################"

Log "==== 0) Git pull tip (BAT BUOC - neu thieu file la do chua pull) ===="
git fetch origin 2>&1 | ForEach-Object { Log ("  git: " + $_) }
git checkout $Branch 2>&1 | ForEach-Object { Log ("  git: " + $_) }
git reset --hard ("origin/" + $Branch) 2>&1 | ForEach-Object { Log ("  git: " + $_) }
$sha = (git rev-parse --short HEAD)
Log ("HEAD=" + $sha)

$need = @(
  ".\pipeline\EP_DIEN_INBOX_NGAY.ps1",
  ".\pipeline\run_hourly.ps1",
  ".\pipeline\install_hourly_task.ps1",
  ".\pipeline\medinet_creds.py"
)
foreach ($f in $need) {
  if (-not (Test-Path -LiteralPath $f)) {
    Log ("FAIL thieu file: " + $f)
    Log "Git remote/branch sai hoac fetch fail. Kiem: git remote -v ; git branch -vv"
    exit 3
  }
}
Log "OK: cac file tip co mat"

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python
Log ("Python=" + $Python)

Log "==== 1) Tat process treo + xoa lock ===="
Get-Process -Name python*, py* -ErrorAction SilentlyContinue | ForEach-Object {
  Log ("  stop PID=" + $_.Id)
  Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
$LockDir = Join-Path $Repo "pipeline\work\locks"
if (Test-Path -LiteralPath $LockDir) {
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -Recurse -ErrorAction SilentlyContinue |
    ForEach-Object { Log ("  del lock " + $_.Name); Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
}

Log "==== 2) Config + SSL + AUTH 2 TK ===="
& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_ssl.py"
$auth = $LASTEXITCODE
Log ("medinet_ssl/auth exit=" + $auth)
if ($auth -ne 0) {
  Log "DUNG: AUTH FAIL TK1. TK1=pkdkthuankieu / Qlskcd@2026 - kiem mat khau Medinet tren web."
  exit 2
}
& $Python ".\pipeline\probe_both_accounts.py"
if ($LASTEXITCODE -ne 0) {
  Log "DUNG: auth 1 trong 2 TK FAIL"
  exit 2
}

Log "==== 3) Drive G: ===="
& $Python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Log "DUNG: G: chua san. Mo Google Drive Desktop + Available offline."
  exit 2
}
& $Python ".\pipeline\drive_paths.py"

Log "==== 4) Dem INBOX TRUOC ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

Log "==== 5) Cai + BAT task HIDDEN ===="
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
Log ("install exit=" + $LASTEXITCODE)
try {
  Enable-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null
  $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if ($t) {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Log ("Task State=" + $t.State + " LastRun=" + $info.LastRunTime + " Next=" + $info.NextRunTime)
  } else {
    Log "WARN: task chua co sau install"
  }
} catch {
  Log ("WARN task: " + $_.Exception.Message)
}

Log "==== 6) Chay run_hourly 1 lan (VISIBLE log) ===="
$t0 = Get-Date
& powershell -NoProfile -ExecutionPolicy Bypass -File ".\pipeline\run_hourly.ps1"
$run = $LASTEXITCODE
$sec = [int]((Get-Date) - $t0).TotalSeconds
Log ("run_hourly exit=" + $run + " duration_s=" + $sec)
if ($sec -lt 20) {
  Log "WARN: chay qua nhanh (<20s) - thuong abort G:/auth/lock, KHONG phai quet that."
}

Log "==== 7) Dem INBOX SAU ===="
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }

Log "==== 8) Heartbeat / abort ===="
$hb = Join-Path $Repo "pipeline\work\logs\LAST_HOURLY_OK.txt"
$hb2 = Join-Path $Repo "pipeline\work\build\logs\LAST_HOURLY_OK.txt"
foreach ($p in @($hb, $hb2)) {
  if (Test-Path -LiteralPath $p) {
    Log ("--- " + $p + " ---")
    Get-Content -LiteralPath $p -Encoding utf8 | ForEach-Object { Log $_ }
  }
}
$logs = Get-ChildItem -Path (Join-Path $Repo "pipeline\work") -Recurse -Filter "hourly-*.log" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 3
foreach ($l in $logs) {
  Log ("log: " + $l.FullName)
}
$errs = Get-ChildItem -Path (Join-Path $Repo "pipeline\work") -Recurse -Filter "hourly-*.err" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 4
foreach ($e in $errs) {
  Log ("--- ERR " + $e.Name + " ---")
  Get-Content -LiteralPath $e.FullName -Tail 25 -ErrorAction SilentlyContinue | ForEach-Object { Log $_ }
}

$markDir = Join-Path $Repo "pipeline\work\build\logs"
if (-not (Test-Path -LiteralPath $markDir)) { New-Item -ItemType Directory -Force -Path $markDir | Out-Null }
@(
  "state=HOURLY_ON"
  ("at=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
  ("head=" + $sha)
  ("run_exit=" + $run)
  ("duration_s=" + $sec)
) | Set-Content -LiteralPath (Join-Path $markDir "HOURLY_PAUSE_STATE.txt") -Encoding utf8

Write-Host ""
Write-Host "############################################################"
Write-Host " XONG EP DIEN. Doc disk_INBOX_CLS truoc/sau o tren."
Write-Host " Neu INBOX khong giam:"
Write-Host "   - AUTH_FAIL / G: abort / duration <20s -> sua do roi chay lai"
Write-Host "   - INBOX giam, MISSING tang -> PDF chua co TTHC (dung)"
Write-Host "   - State=Disabled -> task bi tat lai"
Write-Host "############################################################"
exit $run
