# ============================================================
# 1 LENH DUY NHAT MAY A - chay xong roi di lam viec khac
# Quet toan bo G (da offline) + dien thieu + rematch MISSING
# + CCCD dung / ten sai -> folder CCCD + kham dinh ky
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
Log "#  CHAY 1 LAN CHUAN - quet toan G + dien du + CCCD folder  #"
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

Log "==== 3b/6 Force refill Quoc Chu (MCHC/RDW) ===="
& $Python ".\pipeline\refill_one_patient.py" | ForEach-Object { Log $_ }
Log ("refill_one_patient exit=" + $LASTEXITCODE)

Log "==== 4/6 FULL SCAN gap-only (toan G, 2 bot, heartbeat) ===="
# SkipPull: da reset hard o tren. MinRoundSeconds thap hon vi gap-only.
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_TONG_HOP_MOI.ps1" -SkipPull -FullRounds 2 -RematchRounds 6 -MissingBudget 4000 -MinRoundSeconds 120
$code = $LASTEXITCODE
Log ("TONG_HOP exit=" + $code)

Log "==== 5/6 Bo sung thieu fillable (gap-only) ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_BO_SUNG_THIEU.ps1" -SkipPull -Rounds 2
Log ("BO_SUNG exit=" + $LASTEXITCODE)

Log "==== 6/6 Tong ket ===="
& $Python ".\pipeline\print_counts.py" | ForEach-Object { Log $_ }
& $Python ".\pipeline\print_disk_counts.py" | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
  Log ("WARN print_disk_counts exit=" + $LASTEXITCODE)
}
Log "XONG. Co the tat may / di lam viec khac."
Log "Kiem tra: form Quoc Chu (MCHC/RDW/duong dung o/kham dinh ky) + folder CCCD tren G:."
Log ("Chi tiet: " + $MasterLog)
exit $code
