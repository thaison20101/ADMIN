# ============================================================
# LOC PDF duoi 18 tuoi -> G:\...\PKDK_Thuankieu_Pipeline\UNDER 18
# ASCII-only. Chi may A. Sau do user copy lai vao INBOX_CLS khi can.
#
#   cd C:\Users\thais\ADMIN
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_LOC_UNDER18.ps1
#   powershell -ExecutionPolicy Bypass -File .\pipeline\CHAY_LOC_UNDER18.ps1 -DryRun
# ============================================================

param(
  [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Repo) { $Repo = "C:\Users\thais\ADMIN" }
Set-Location $Repo

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"

Write-Host ""
Write-Host "############################################################"
Write-Host "#  LOC UNDER 18 -> PKDK_Thuankieu_Pipeline\UNDER 18        #"
Write-Host "############################################################"
Write-Host "CHI 1 cua so. Rule: nam_sinh >= (nam_nay-17) hoac mau M1/M2/M12."

if (Test-Path -LiteralPath (Join-Path $Repo ".git")) {
  git pull origin cursor/drive-hourly-pipeline-df0f
}
& python ".\pipeline\ensure_config.py"
& python ".\pipeline\assert_g_pipeline.py"
if ($LASTEXITCODE -ne 0) {
  Write-Host "DUNG: G: chua san."
  exit 2
}

$pyArgs = @(".\pipeline\move_under18.py", "--disk-scan")
if ($DryRun) { $pyArgs += "--dry-run" }
Write-Host ("Chay: python -u {0}" -f ($pyArgs -join " "))
& python -u @pyArgs
$code = $LASTEXITCODE
& python ".\pipeline\print_counts.py" | ForEach-Object { Write-Host $_ }
Write-Host "XONG. UNDER 18: mo Explorer G:\Drive cua toi\PKDK_Thuankieu_Pipeline\UNDER 18"
Write-Host "Muon xu ly: chuyen PDF sang INBOX_CLS roi chay CHAY_REMATCH_MISSING.ps1"
if ($code -ne 0) { exit $code }
exit 0
