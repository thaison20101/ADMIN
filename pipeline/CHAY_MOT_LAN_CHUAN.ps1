# ============================================================
# 1 LENH MAY A: quet lai toan G theo rule dien moi + BAT hourly
# ASCII-only (Windows PowerShell 5.x)
#
# Rule dien moi (auto_cycle):
#   - Parse MCHC/RDW Ghi chu / token dinh
#   - Gap-only: PDF co ma web thieu/sai -> dien; du khop -> giu
#   - Duong mau bat ky -> SinhHoaMau_DuongMau; luc doi -> LucDoi
#   - LoaiKham dinh ky 5152; verify cung; CCCD+ten lech -> folder CCCD
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_MOT_LAN_CHUAN.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Branch = "cursor/hourly-flash-fix-df0f"
$env:MEDINET_SSL_VERIFY = "0"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python

$LogDir = Join-Path $Repo "pipeline\work\logs"
if (-not (Test-Path -LiteralPath $LogDir)) {
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$MasterLog = Join-Path $LogDir ("motlan-chuan-{0}.log" -f $stamp)
function Log([string]$m) {
  $line = ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m)
  Write-Host $line
  Add-Content -LiteralPath $MasterLog -Value $line -Encoding utf8
}

Log "############################################################"
Log "#  QUET LAI TOAN G (rule moi) + BAT HOURLY                  #"
Log "############################################################"
Log ("Repo=" + $Repo)
Log ("Python=" + $Python)
Log ("Log=" + $MasterLog)

Log "==== 1/6 Tat hourly + kill python treo ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
Get-Process -Name python*, py* -ErrorAction SilentlyContinue | ForEach-Object {
  Log ("  stop PID=" + $_.Id)
  Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
$LockDir = Join-Path $Repo "pipeline\work\locks"
if (Test-Path -LiteralPath $LockDir) {
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

Log "==== 2/6 Keo code moi ===="
git fetch origin
git checkout $Branch
git reset --hard ("origin/" + $Branch)
git clean -fd --exclude=pipeline/config.local.json --exclude=pipeline/work --exclude=tracking
$sha = (git rev-parse --short HEAD)
Log ("HEAD=" + $sha)

Log "==== 3/6 SSL + folder G + restore ledger ===="
& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_ssl.py"
if ($LASTEXITCODE -ne 0) {
  Log "DUNG: SSL/auth FAIL"
  exit 2
}
& $Python ".\pipeline\drive_paths.py"
& $Python ".\pipeline\restore_cases_snapshot.py"
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
  Log ("WARN print_disk_counts exit=" + $LASTEXITCODE + " (tiep tuc)")
}

Log "==== 4/6 FULL SCAN gap-only (toan G, 2 bot) ===="
# SkipPull: da reset hard o tren.
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_TONG_HOP_MOI.ps1" -SkipPull -FullRounds 2 -RematchRounds 6 -MissingBudget 4000 -MinRoundSeconds 120
$code = $LASTEXITCODE
Log ("TONG_HOP exit=" + $code)

Log "==== 5/6 Bo sung thieu fillable (gap-only) ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_BO_SUNG_THIEU.ps1" -SkipPull -Rounds 2
Log ("BO_SUNG exit=" + $LASTEXITCODE)

Log "==== 6/6 Tong ket + BAT hourly (cung rule moi) ===="
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
  Log ("WARN print_disk_counts exit=" + $LASTEXITCODE)
}

Log "Bat / cai lai task PKDK_Hourly_Sync (run_hourly = cung auto_cycle rule moi)..."
& powershell -ExecutionPolicy Bypass -File ".\pipeline\install_hourly_task.ps1"
$hourlyCode = $LASTEXITCODE
Log ("install_hourly_task exit=" + $hourlyCode)
if ($hourlyCode -ne 0) {
  Log "WARN: khong dang ky duoc Task Scheduler (can Run as Administrator)."
  Log "Chay tay: powershell -ExecutionPolicy Bypass -File .\pipeline\install_hourly_task.ps1"
  # Van thu Enable neu task da co
  try {
    Enable-ScheduledTask -TaskName "PKDK_Hourly_Sync" -ErrorAction Stop | Out-Null
    Log "OK: Enable-ScheduledTask PKDK_Hourly_Sync"
  } catch {
    Log ("WARN Enable hourly: " + $_.Exception.Message)
  }
}

Log "XONG. Da quet lai G + hourly dung rule dien moi."
Log "Hourly: INBOX_CLS moi + rematch MISSING/TK (khong full rglob G moi gio)."
Log ("Chi tiet: " + $MasterLog)
exit $code
