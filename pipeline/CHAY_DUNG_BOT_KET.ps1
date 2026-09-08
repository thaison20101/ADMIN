# ============================================================
# DUNG bot treo ca dem (ASCII-only)
# Full-scan cu rglob+hash MISSING tren G: Drive = treo.
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_DUNG_BOT_KET.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

Write-Host "############################################################"
Write-Host "#  DUNG BOT TREO — roi keo code moi (khong walk MISSING)    #"
Write-Host "############################################################"

Write-Host "==== 1) Tat hourly ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"

Write-Host "==== 2) Kill python (bot treo) ===="
Get-Process -Name python*, py* -ErrorAction SilentlyContinue |
  ForEach-Object {
    Write-Host ("  stop PID={0} {1}" -f $_.Id, $_.ProcessName)
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
  }
Start-Sleep -Seconds 2

Write-Host "==== 3) Clear locks ===="
$LockDir = Join-Path $Repo "pipeline\work\locks"
if (Test-Path -LiteralPath $LockDir) {
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
  Get-ChildItem -LiteralPath $LockDir -Filter "*.claim" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

Write-Host "==== 4) Tail log cu (xem co treo o dau) ===="
$LogDir = Join-Path $Repo "pipeline\work\logs"
Get-ChildItem -LiteralPath $LogDir -Filter "tonghop-full*.log" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 2 |
  ForEach-Object {
    Write-Host ("--- {0} ---" -f $_.FullName)
    Get-Content -LiteralPath $_.FullName -Tail 30 -ErrorAction SilentlyContinue
  }

Write-Host "==== 5) Pull tip (no MISSING walk) + TONG_HOP ===="
$Branch = "cursor/hourly-flash-fix-df0f"
$env:MEDINET_SSL_VERIFY = "0"
git fetch origin
git checkout $Branch
git reset --hard ("origin/" + $Branch)
$sha = (git rev-parse --short HEAD)
Write-Host ("HEAD=" + $sha)

Write-Host "Chay lai TONG_HOP (co heartbeat 60s). Neu TK1/TK2=0: Available offline truoc."
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_TONG_HOP_MOI.ps1" -SkipPull
exit $LASTEXITCODE
