# ============================================================
# KEO CODE MOI + TONG HOP (ASCII-only)
# Dung khi may A van SSL fail / hourly nhay / form chua dien
# (thuong do CHUA git pull commit moi).
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_KEO_CODE_VA_TONG_HOP.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$Branch = "cursor/hourly-flash-fix-df0f"
$env:MEDINET_SSL_VERIFY = "0"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

. (Join-Path $PSScriptRoot "Resolve-PkdkPython.ps1")
$Python = Resolve-PkdkPython
$env:PKDK_PYTHON = $Python

Write-Host "############################################################"
Write-Host "#  KEO CODE MOI ROI TONG HOP (SSL OFF + quet toan bo PDF)   #"
Write-Host "############################################################"
Write-Host ("Repo: " + $Repo)
Write-Host ("Python: " + $Python)
Write-Host ("Branch: " + $Branch)

Write-Host "==== 1) Tat hourly + kill python + clear locks ===="
& powershell -ExecutionPolicy Bypass -File ".\pipeline\TAM_NGUNG_HOURLY.ps1"
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$LockDir = Join-Path $Repo "pipeline\work\locks"
if (Test-Path -LiteralPath $LockDir) {
  Get-ChildItem -LiteralPath $LockDir -Filter "*.lock" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

Write-Host "==== 2) git fetch + reset --hard origin/$Branch ===="
if (-not (Test-Path -LiteralPath (Join-Path $Repo ".git"))) {
  Write-Host "DUNG: khong co .git"
  exit 2
}
git fetch origin
git checkout $Branch
git reset --hard ("origin/" + $Branch)
git clean -fd --exclude=pipeline/config.local.json --exclude=pipeline/work --exclude=tracking
$sha = (git rev-parse --short HEAD)
Write-Host ("OK: HEAD=" + $sha)

# Prove new SSL file is present
$sslFile = Join-Path $Repo "pipeline\medinet_ssl.py"
$sslText = Get-Content -LiteralPath $sslFile -Raw -ErrorAction SilentlyContinue
if (-not ($sslText -match "apply_ssl_monkeypatch")) {
  Write-Host "DUNG: medinet_ssl.py chua co monkeypatch - pull that bai?"
  exit 2
}
if (-not ($sslText -match "probe_auth")) {
  Write-Host "DUNG: medinet_ssl.py cu - can pull lai."
  exit 2
}
Write-Host "OK: medinet_ssl.py co monkeypatch + probe_auth"

Write-Host "==== 3) ensure_config + SSL probe ===="
& $Python ".\pipeline\ensure_config.py"
& $Python ".\pipeline\medinet_ssl.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: SSL/auth van FAIL sau pull. Gui log probe."
  exit 2
}

Write-Host "==== 4) CHAY_TONG_HOP_MOI -SkipPull (giu code vua reset) ===="
Write-Host "Ky vong: chay LAU, co FILLABLE_SCOPE PROCESSED/TK1/TK2, khong SSL."
& powershell -ExecutionPolicy Bypass -File ".\pipeline\CHAY_TONG_HOP_MOI.ps1" -SkipPull
$code = $LASTEXITCODE
Write-Host ("TONG_HOP exit=" + $code)
exit $code
